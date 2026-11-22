#!/usr/bin/env bash
# image-scan: Trivy vuln + secret scan of a pushed GHCR image ref.
#
# Usage:
#   image-scan.sh scan      # validate, install pinned Trivy, scan, strip secrets, SARIF, counts, summary, outputs
#   image-scan.sh enforce   # fail when the scan result is 'fail'
#
# All inputs arrive via environment variables (see action.yml). Never `set -x`.
# `scan` never exits non-zero for findings. Only `enforce` fails on findings,
# so reports and the optional SARIF upload always happen first.
set -euo pipefail

TRIVY_VERSION="0.76.2"
TRIVY_SHA256_LINUX_64BIT="bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf"
TRIVY_SHA256_LINUX_ARM64="ab9d51f86e6a5fb936f605faff6b593ac51bc378fff4d3e8b9d58358b9c367c3"
TRIVY_DB_REPOSITORIES="ghcr.io/aquasecurity/trivy-db,public.ecr.aws/aquasecurity/trivy-db"

IMAGE_REF_RE='^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}|@sha256:[0-9a-f]{64})$'
SEVERITIES="UNKNOWN LOW MEDIUM HIGH CRITICAL"
TOP_N=20

fail() {
  echo "::error::$*"
  exit 1
}

require() {
  local name="$1" value="$2"
  [[ -n "$value" ]] || fail "input '${name}' is required"
}

set_output() {
  printf '%s=%s\n' "$1" "$2" >>"$GITHUB_OUTPUT"
}

bool_input() {
  local name="$1" value="$2"
  case "$value" in
    true | false) ;;
    *) fail "input '${name}' must be 'true' or 'false', got '${value}'" ;;
  esac
}

# Normalize a comma-separated severity list to upper case, validate each entry.
# Sets FAIL_SEVS (no subshell, so `fail` exits the script and its ::error:: reaches the log).
normalize_severities() {
  local raw="$1" out="" s
  local -a items
  IFS=',' read -r -a items <<<"${raw^^}"
  for s in "${items[@]}"; do
    s="${s//[[:space:]]/}"
    [[ -z "$s" ]] && continue
    [[ " ${SEVERITIES} " == *" ${s} "* ]] ||
      fail "input 'fail-severities' must be a comma-separated list of ${SEVERITIES// /,}, got '${raw}'"
    out+="${out:+,}${s}"
  done
  [[ -n "$out" ]] || fail "input 'fail-severities' must name at least one severity, got '${raw}'"
  FAIL_SEVS="$out"
}

install_trivy() {
  local dest="$1" asset sha
  case "$(uname -m)" in
    x86_64 | amd64)
      asset="trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
      sha="$TRIVY_SHA256_LINUX_64BIT"
      ;;
    aarch64 | arm64)
      asset="trivy_${TRIVY_VERSION}_Linux-ARM64.tar.gz"
      sha="$TRIVY_SHA256_LINUX_ARM64"
      ;;
    *) fail "unsupported runner architecture '$(uname -m)' for Trivy" ;;
  esac

  mkdir -p "$dest"
  local tarball="${dest}/${asset}"
  curl -fsSL --retry 3 --retry-delay 5 -o "$tarball" \
    "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/${asset}" ||
    fail "failed to download Trivy ${TRIVY_VERSION} (${asset})"
  printf '%s  %s\n' "$sha" "$tarball" | sha256sum --check --quiet - ||
    fail "Trivy ${TRIVY_VERSION} checksum mismatch for ${asset}"
  tar -xzf "$tarball" -C "$dest" trivy
  rm -f "$tarball"
  "${dest}/trivy" --version >/dev/null || fail "installed Trivy binary does not run"
}

# Escape a value for a markdown table cell.
md_cell() {
  local v="${1//|/\\|}"
  v="${v//$'\n'/ }"
  printf '%s' "$v"
}

write_summary() {
  local json="$1" summary="$2" image_ref="$3" fail_sevs="$4" result="$5"
  local critical="$6" high="$7" medium="$8" low="$9" unknown="${10}" secrets="${11}"

  {
    echo "### image-scan: ${result^^}"
    echo ""
    echo "Image: \`${image_ref}\`"
    echo ""
    echo "Fails on: vulnerability severity in \`${fail_sevs}\`, or any secret."
    echo ""
    echo "| Severity | Count |"
    echo "|---|---|"
    echo "| CRITICAL | ${critical} |"
    echo "| HIGH | ${high} |"
    echo "| MEDIUM | ${medium} |"
    echo "| LOW | ${low} |"
    echo "| UNKNOWN | ${unknown} |"
    echo ""
    echo "Secrets: ${secrets}"

    if ((critical + high + medium + low + unknown > 0)); then
      echo ""
      echo "#### Top vulnerabilities"
      echo ""
      echo "| ID | Package | Severity | Installed | Fixed |"
      echo "|---|---|---|---|---|"
      local id pkg sev installed fixed
      while IFS=$'\t' read -r id pkg sev installed fixed; do
        printf '| %s | %s | %s | %s | %s |\n' "$(md_cell "$id")" "$(md_cell "$pkg")" "$(md_cell "$sev")" \
          "$(md_cell "$installed")" "$(md_cell "${fixed:--}")"
      done < <(jq -r --argjson n "$TOP_N" '
        def rank: {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}[.] // 4;
        [.Results[]?.Vulnerabilities[]?]
        | sort_by((.Severity | rank), .VulnerabilityID)
        | .[:$n][]
        | [.VulnerabilityID, .PkgName, .Severity, (.InstalledVersion // ""), (.FixedVersion // "")]
        | @tsv' "$json")
    fi

    if ((secrets > 0)); then
      echo ""
      echo "#### Secrets (rule ID and file path only)"
      echo ""
      echo "| Rule ID | File |"
      echo "|---|---|"
      local rule target
      while IFS=$'\t' read -r rule target; do
        printf '| %s | %s |\n' "$(md_cell "$rule")" "$(md_cell "$target")"
      done < <(jq -r --argjson n "$TOP_N" '
        [.Results[]? | .Target as $t | .Secrets[]? | [.RuleID, $t]]
        | .[:$n][] | @tsv' "$json")
    fi
  } >"$summary"

  cat "$summary" >>"${GITHUB_STEP_SUMMARY:-/dev/null}"
}

cmd_scan() {
  local image_ref="${IMAGE_REF:-}" fail_severities="${FAIL_SEVERITIES:-}"
  local ignore_file="${IGNORE_FILE:-}" ignore_unfixed="${IGNORE_UNFIXED:-}"
  local upload_sarif="${UPLOAD_SARIF:-}" sarif_category="${SARIF_CATEGORY:-}"
  local registry_token="${REGISTRY_TOKEN:-}" registry_username="${REGISTRY_USERNAME:-}"
  local runner_temp="${RUNNER_TEMP:-}"

  # --- validate (no side effects before this block completes) ---
  require image-ref "$image_ref"
  [[ "$image_ref" =~ $IMAGE_REF_RE ]] ||
    fail "input 'image-ref' must be a lowercase ghcr.io image with :tag or @sha256:<digest> (e.g. ghcr.io/pernix-labs/foo:sha-<sha>), got '${image_ref}'"

  require fail-severities "$fail_severities"
  normalize_severities "$fail_severities"
  local fail_sevs="$FAIL_SEVS"

  if [[ -n "$ignore_file" ]]; then
    [[ -f "$ignore_file" ]] || fail "input 'ignore-file' must be an existing file, got '${ignore_file}'"
  fi
  bool_input ignore-unfixed "$ignore_unfixed"
  bool_input upload-sarif "$upload_sarif"
  require sarif-category "$sarif_category"
  require registry-token "$registry_token"
  require registry-username "$registry_username"
  require RUNNER_TEMP "$runner_temp"

  # --- install ---
  local work="${runner_temp}/image-scan"
  rm -rf "$work"
  mkdir -p "$work"
  install_trivy "${runner_temp}/image-scan-trivy"
  local trivy="${runner_temp}/image-scan-trivy/trivy"

  # --- scan (single Trivy run, never fails on findings) ---
  local raw_json="${work}/raw.json" json="${work}/results.json"
  local sarif="${work}/results.sarif" summary="${work}/summary.md"
  local -a args=(
    image
    --image-src remote
    --scanners "vuln,secret"
    --format json
    --exit-code 0
    --no-progress
    --db-repository "$TRIVY_DB_REPOSITORIES"
    --output "$raw_json"
  )
  [[ -n "$ignore_file" ]] && args+=(--ignorefile "$ignore_file")
  [[ "$ignore_unfixed" == "true" ]] && args+=(--ignore-unfixed)
  args+=("$image_ref")

  echo "Scanning ${image_ref} with Trivy ${TRIVY_VERSION}"
  local rc=0
  TRIVY_USERNAME="$registry_username" TRIVY_PASSWORD="$registry_token" "$trivy" "${args[@]}" || rc=$?
  if ((rc != 0)); then
    rm -f "$raw_json"
    fail "Trivy failed (exit ${rc}) scanning ${image_ref}: vulnerability DB download, registry auth, or image pull error"
  fi
  [[ -s "$raw_json" ]] || fail "Trivy produced no report for ${image_ref}"

  # --- strip secret material: keep rule ID, title, severity, file path ---
  jq 'del(.Results[]?.Secrets[]?.Match, .Results[]?.Secrets[]?.Code, .Results[]?.Secrets[]?.Layer.CreatedBy)' \
    "$raw_json" >"$json"
  rm -f "$raw_json"

  "$trivy" convert --format sarif --output "$sarif" "$json" ||
    fail "Trivy failed to convert the report to SARIF"

  # --- counts ---
  local counts critical high medium low unknown secrets
  counts="$(jq -r '
    [.Results[]?.Vulnerabilities[]?.Severity] as $s
    | [
        ($s | map(select(. == "CRITICAL")) | length),
        ($s | map(select(. == "HIGH")) | length),
        ($s | map(select(. == "MEDIUM")) | length),
        ($s | map(select(. == "LOW")) | length),
        ($s | map(select(. != "CRITICAL" and . != "HIGH" and . != "MEDIUM" and . != "LOW")) | length),
        ([.Results[]?.Secrets[]?] | length)
      ] | @tsv' "$json")"
  IFS=$'\t' read -r critical high medium low unknown secrets <<<"$counts"

  # --- fail rule: any secret, or any vuln severity in fail-severities ---
  local result="pass" over=0 sev n
  for sev in ${fail_sevs//,/ }; do
    case "$sev" in
      CRITICAL) n="$critical" ;;
      HIGH) n="$high" ;;
      MEDIUM) n="$medium" ;;
      LOW) n="$low" ;;
      UNKNOWN) n="$unknown" ;;
    esac
    over=$((over + n))
  done
  if ((secrets > 0 || over > 0)); then
    result="fail"
  fi

  write_summary "$json" "$summary" "$image_ref" "$fail_sevs" "$result" \
    "$critical" "$high" "$medium" "$low" "$unknown" "$secrets"
  rm -f "$json"

  set_output critical-count "$critical"
  set_output high-count "$high"
  set_output medium-count "$medium"
  set_output low-count "$low"
  set_output secret-count "$secrets"
  set_output sarif-file "$sarif"
  set_output result "$result"
  set_output fail-severities "$fail_sevs"

  echo "Result ${result}: critical=${critical} high=${high} medium=${medium} low=${low} unknown=${unknown} secrets=${secrets}"
}

cmd_enforce() {
  local result="${RESULT:-}" image_ref="${IMAGE_REF:-}" fail_sevs="${FAIL_SEVERITIES:-}"
  case "$result" in
    pass)
      echo "image-scan passed for ${image_ref}"
      ;;
    fail)
      fail "image-scan failed for ${image_ref}: secrets=${SECRET_COUNT:-?}, critical=${CRITICAL_COUNT:-?}, high=${HIGH_COUNT:-?}, medium=${MEDIUM_COUNT:-?}, low=${LOW_COUNT:-?} (fails on any secret or severity in ${fail_sevs})"
      ;;
    *) fail "image-scan produced no result for ${image_ref}" ;;
  esac
}

main() {
  case "${1:-}" in
    scan) cmd_scan ;;
    enforce) cmd_enforce ;;
    *) fail "usage: image-scan.sh scan|enforce" ;;
  esac
}

main "$@"
