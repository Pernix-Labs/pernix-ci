#!/usr/bin/env bash
# image-retention: delete expired GHCR package versions.
# Env: PACKAGES (newline list), OWNER, MAX_AGE_DAYS, PRERELEASE_MAX_AGE_DAYS, KEEP_VERSIONS,
#      STABLE_TAG_PATTERN, PRERELEASE_TAG_PATTERN, DRY_RUN, REFERENCE_TIME, REGISTRY_TOKEN,
#      REGISTRY_USERNAME, GITHUB_REPOSITORY.
# Writes deleted-count/kept-count/deleted-versions to $GITHUB_OUTPUT.
# Subcommand: image-retention.sh remediation-message <org|user> <owner> <pkg> <repo>
set -euo pipefail

readonly DIGEST_RE='^sha256:[0-9a-f]{64}$'
readonly OWNER_RE='^[A-Za-z0-9]([A-Za-z0-9-]{0,38})$'
readonly PKG_RE='^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$'
readonly INT_RE='^[0-9]+$'
readonly TIME_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
readonly ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'

fail() {
  echo "::error::image-retention: $*"
  exit 1
}

# remediation_message <org|user> <owner> <pkg> <repo>: D14 text for a 403 at DELETE.
remediation_message() {
  local kind="$1" owner="$2" pkg="$3" repo="$4" seg enc
  case "$kind" in
    org) seg=orgs ;;
    user) seg=users ;;
    *) fail "remediation-message: owner kind must be 'org' or 'user', got '${kind}'" ;;
  esac
  enc="${pkg//\//%2F}"
  printf 'Cannot delete versions of %s: %s lacks Admin on the package. Open https://github.com/%s/%s/packages/container/%s/settings -> Manage Actions access -> grant %s Admin.\n' \
    "$pkg" "$repo" "$seg" "$owner" "$enc" "$repo"
}

if [[ "${1:-}" == remediation-message ]]; then
  [[ "$#" -eq 5 ]] || fail "usage: image-retention.sh remediation-message <org|user> <owner> <pkg> <repo>"
  remediation_message "$2" "$3" "$4" "$5"
  exit 0
fi
[[ "$#" -eq 0 ]] || fail "unknown subcommand '$1'"

PACKAGES="${PACKAGES:-}"
OWNER="${OWNER:-}"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-14}"
PRERELEASE_MAX_AGE_DAYS="${PRERELEASE_MAX_AGE_DAYS:-14}"
KEEP_VERSIONS="${KEEP_VERSIONS:-5}"
STABLE_TAG_PATTERN="${STABLE_TAG_PATTERN:-}"
PRERELEASE_TAG_PATTERN="${PRERELEASE_TAG_PATTERN:-}"
DRY_RUN="${DRY_RUN:-false}"
REFERENCE_TIME="${REFERENCE_TIME:-}"
REGISTRY_TOKEN="${REGISTRY_TOKEN:-}"
REGISTRY_USERNAME="${REGISTRY_USERNAME:-}"
REPOSITORY="${GITHUB_REPOSITORY:-}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

# --- validate (before any network call) ---
packages=()
while IFS= read -r line || [[ -n "$line" ]]; do
  p="${line//$'\r'/}"
  p="${p#"${p%%[![:space:]]*}"}"
  p="${p%"${p##*[![:space:]]}"}"
  [[ -n "$p" ]] || continue
  [[ "$p" =~ $PKG_RE ]] || fail "input 'packages' contains an invalid package name: '${p}' (lowercase GHCR name without owner or tag)"
  dup=false
  for q in "${packages[@]+"${packages[@]}"}"; do
    [[ "$q" == "$p" ]] && dup=true
  done
  [[ "$dup" == true ]] || packages+=("$p")
done <<<"$PACKAGES"
[[ "${#packages[@]}" -gt 0 ]] || fail "input 'packages' is required (newline list of GHCR package names)"
[[ -n "$OWNER" ]] || fail "input 'owner' is required"
[[ "$OWNER" =~ $OWNER_RE ]] || fail "input 'owner' is not a valid GitHub owner name: '${OWNER}'"
[[ "$MAX_AGE_DAYS" =~ $INT_RE ]] || fail "input 'max-age-days' must be a non-negative integer, got '${MAX_AGE_DAYS}'"
[[ "$PRERELEASE_MAX_AGE_DAYS" =~ $INT_RE ]] || fail "input 'prerelease-max-age-days' must be a non-negative integer, got '${PRERELEASE_MAX_AGE_DAYS}'"
[[ "$KEEP_VERSIONS" =~ $INT_RE ]] || fail "input 'keep-versions' must be a non-negative integer, got '${KEEP_VERSIONS}'"
[[ -n "$STABLE_TAG_PATTERN" ]] || fail "input 'stable-tag-pattern' is required"
jq -en --arg p "$STABLE_TAG_PATTERN" '"x" | test($p) | true' >/dev/null 2>&1 ||
  fail "input 'stable-tag-pattern' is not a valid regex: '${STABLE_TAG_PATTERN}'"
[[ -n "$PRERELEASE_TAG_PATTERN" ]] || fail "input 'prerelease-tag-pattern' is required"
jq -en --arg p "$PRERELEASE_TAG_PATTERN" '"x" | test($p) | true' >/dev/null 2>&1 ||
  fail "input 'prerelease-tag-pattern' is not a valid regex: '${PRERELEASE_TAG_PATTERN}'"
case "$DRY_RUN" in
  true | false) ;;
  *) fail "input 'dry-run' must be 'true' or 'false', got '${DRY_RUN}'" ;;
esac
if [[ -n "$REFERENCE_TIME" ]]; then
  [[ "$REFERENCE_TIME" =~ $TIME_RE ]] || fail "input 'reference-time' must be ISO 8601 UTC 'YYYY-MM-DDTHH:MM:SSZ', got '${REFERENCE_TIME}'"
  REF_EPOCH="$(jq -rn --arg t "$REFERENCE_TIME" '$t | fromdateiso8601' 2>/dev/null)" ||
    fail "input 'reference-time' is not a valid date: '${REFERENCE_TIME}'"
else
  REF_EPOCH="$(date -u +%s)"
  REFERENCE_TIME="$(date -u -d "@${REF_EPOCH}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$REF_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
fi
[[ -n "$REGISTRY_TOKEN" ]] || fail "input 'registry-token' is required"
[[ -n "$REGISTRY_USERNAME" ]] || fail "input 'registry-username' is required"
[[ -n "$REPOSITORY" ]] || fail "GITHUB_REPOSITORY is not set"

export GH_TOKEN="$REGISTRY_TOKEN"
OWNER_LC="$(printf '%s' "$OWNER" | tr '[:upper:]' '[:lower:]')"

WORK="$(mktemp -d "${RUNNER_TEMP:-/tmp}/image-retention.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

DELETED="$WORK/deleted.json"
echo '[]' >"$DELETED"
KEPT=0
PLAN=""
PKG=""

# Shared classifier (R6.2): stable > prerelease > sha-only on metadata.container.tags.
# shellcheck disable=SC2016 # jq program, not shell expansion
readonly CLASSIFY='def cls($s; $p): (.metadata.container.tags // []) as $t
  | if any($t[]; test($s)) then "stable" elif any($t[]; test($p)) then "prerelease" else "sha-only" end;'

# Escape a value for a double-quoted curl config string.
curl_quote() {
  local v="${1//\\/\\\\}"
  printf '"%s"' "${v//\"/\\\"}"
}

# curl_once <config> <body-file> <curl args...>: prints HTTP status (000 on transport error).
# Credentials travel in <config> on stdin, never on the command line.
curl_once() {
  local config="$1" body="$2" code
  shift 2
  code="$(printf '%s\n' "$config" | curl -sS -K - -o "$body" -D "$WORK/headers" -w '%{http_code}' "$@")" || code="000"
  printf '%s' "${code:-000}"
}

# api_once <gh api args...>: GitHub API call via gh (GH_TOKEN), prints HTTP status, body in $WORK/api.body.
api_once() {
  gh api -i "$@" >"$WORK/api.out" 2>"$WORK/api.err" || true
  awk 'f{print} /^\r?$/{f=1}' "$WORK/api.out" >"$WORK/api.body"
  local code
  code="$(head -n1 "$WORK/api.out" | awk '{print $2}' | tr -d '\r')"
  printf '%s' "${code:-000}"
}

# with_retry <fn> <args...>: one retry after 5s on 429/5xx.
with_retry() {
  local code
  code="$("$@")"
  if [[ "$code" == 429 || "$code" =~ ^5[0-9][0-9]$ ]]; then
    echo "::warning::image-retention: HTTP ${code}, retrying once in 5s" >&2
    sleep 5
    code="$("$@")"
  fi
  printf '%s' "$code"
}

write_outputs() {
  local delim
  delim="EOF_$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  {
    echo "deleted-count=$(jq 'length' "$DELETED")"
    echo "kept-count=${KEPT}"
    echo "deleted-versions<<${delim}"
    jq -c '.' "$DELETED"
    echo "${delim}"
  } >>"$GITHUB_OUTPUT"
}

# write_summary: per-package table of the current $PLAN into $GITHUB_STEP_SUMMARY.
write_summary() {
  [[ -n "${GITHUB_STEP_SUMMARY:-}" && -n "$PLAN" && -s "$PLAN" ]] || return 0
  {
    echo "### image-retention: \`${OWNER}/${PKG}\`$([[ "$DRY_RUN" == true ]] && echo ' (dry-run)')"
    echo
    echo "Reference time \`${REFERENCE_TIME}\`, keep-versions ${KEEP_VERSIONS}, prerelease-max-age-days ${PRERELEASE_MAX_AGE_DAYS}, max-age-days ${MAX_AGE_DAYS}."
    echo
    echo "| Result | Class | Tags | Age (days) | Reason | Version id |"
    echo "|---|---|---|---|---|---|"
    jq -r '.[] | "| \(.result) | \(.class) | \(if (.tags | length) == 0 then "(untagged)" else (.tags | map("`\(.)`") | join(" ")) end) | \(.age_days) | \(.reason) | \(.id) |"' "$PLAN"
    echo
  } >>"$GITHUB_STEP_SUMMARY"
}

print_deleted() {
  echo "image-retention: versions deleted so far: $(jq 'length' "$DELETED")"
  jq -r '.[] | "  \(.package) id=\(.id) tags=\(.tags | join(","))"' "$DELETED"
}

# abort <message>: stop mid-run, report deleted-so-far, write outputs and summary, fail (R6.9).
abort() {
  echo "::error::image-retention: $1"
  print_deleted
  write_summary
  write_outputs
  exit 1
}

# set_field <id> <jq assignment>: update one record of $PLAN.
set_field() {
  jq --argjson id "$1" "map(if .id == \$id then $2 else . end)" "$PLAN" >"$PLAN.tmp" && mv "$PLAN.tmp" "$PLAN"
}

# --- owner rule ---
code="$(with_retry api_once "users/${OWNER}")"
[[ "$code" == 200 ]] || fail "owner lookup GET /users/${OWNER} returned HTTP ${code}: $(head -c 300 "$WORK/api.err")"
if [[ "$(jq -r '.type // empty' "$WORK/api.body")" == Organization ]]; then
  OWNER_KIND=org
  BASE="orgs/${OWNER}"
else
  OWNER_KIND=user
  BASE="users/${OWNER}"
fi
echo "image-retention: owner ${OWNER} is ${OWNER_KIND}, reference time ${REFERENCE_TIME}, dry-run=${DRY_RUN}"

for PKG in "${packages[@]}"; do
  PLAN="$WORK/plan.json"
  : >"$PLAN"
  enc="$(jq -rn --arg n "$PKG" '$n|@uri')"
  api_path="${BASE}/packages/container/${enc}"

  # --- list all versions (paginated) ---
  if ! gh api --paginate "${api_path}/versions?per_page=100" >"$WORK/pages.json" 2>"$WORK/list.err"; then
    abort "listing versions of ${PKG} failed: $(head -c 300 "$WORK/list.err")"
  fi

  # --- classify and mark (R6.2-R6.5) ---
  jq -s \
    --arg pkg "$PKG" --arg s "$STABLE_TAG_PATTERN" --arg p "$PRERELEASE_TAG_PATTERN" \
    --argjson ref "$REF_EPOCH" --argjson keep "$KEEP_VERSIONS" \
    --argjson pmax "$PRERELEASE_MAX_AGE_DAYS" --argjson smax "$MAX_AGE_DAYS" \
    "${CLASSIFY}"'
    add // []
    | map({package: $pkg, id, digest: .name, created_at,
           tags: (.metadata.container.tags // []), class: cls($s; $p),
           epoch: (.created_at | fromdateiso8601)})
    | sort_by([-.epoch, -.id])
    | ([.[] | select(.class == "stable") | .id] | to_entries | map({key: (.value | tostring), value: .key}) | from_entries) as $rank
    | map(.age_days = ((($ref - .epoch) / 86400) | floor)
      | if .class == "stable" then
          .reason = "keep-n" | .action = (if $rank[.id | tostring] < $keep then "keep" else "delete" end)
        else
          .reason = "age"
          | .action = (if ($ref - .epoch) > ((if .class == "prerelease" then $pmax else $smax end) * 86400) then "delete" else "keep" end)
        end)' "$WORK/pages.json" >"$PLAN"
  total="$(jq 'length' "$PLAN")"

  # --- child protection (R6.6): children of retained indexes are never deleted ---
  if [[ "$(jq '[.[] | select(.action == "delete")] | length' "$PLAN")" -gt 0 ]]; then
    repo_path="${OWNER_LC}/${PKG}"
    code="$(with_retry curl_once "user = $(curl_quote "${REGISTRY_USERNAME}:${REGISTRY_TOKEN}")" "$WORK/token.json" \
      "https://ghcr.io/token?service=ghcr.io&scope=repository:${repo_path}:pull")"
    [[ "$code" == 200 ]] || abort "token exchange (pull) for ${repo_path} returned HTTP ${code}"
    bearer="$(jq -r '.token // empty' "$WORK/token.json" 2>/dev/null || true)"
    rm -f "$WORK/token.json"
    [[ -n "$bearer" ]] || abort "token exchange for ${repo_path} returned no token"
    echo "::add-mask::${bearer}"
    auth="header = $(curl_quote "Authorization: Bearer ${bearer}")"

    : >"$WORK/inspected"
    while :; do
      pending="$(jq -r '.[] | select(.action == "keep") | .digest' "$PLAN" | grep -vxF -f "$WORK/inspected" || true)"
      [[ -n "$pending" ]] || break
      while IFS= read -r parent; do
        echo "$parent" >>"$WORK/inspected"
        [[ "$parent" =~ $DIGEST_RE ]] || abort "version of ${PKG} has non-digest name '${parent}'"
        code="$(with_retry curl_once "$auth" "$WORK/manifest" -H "Accept: ${ACCEPT}" "https://ghcr.io/v2/${repo_path}/manifests/${parent}")"
        [[ "$code" == 200 ]] || abort "GET manifest ${repo_path}@${parent} returned HTTP ${code}"
        while IFS= read -r child; do
          [[ -n "$child" ]] || continue
          jq -e --arg d "$child" 'any(.[]; .digest == $d and .action == "delete")' "$PLAN" >/dev/null || continue
          id="$(jq -r --arg d "$child" '.[] | select(.digest == $d) | .id' "$PLAN" | head -n1)"
          set_field "$id" ".action = \"keep\" | .reason = \"child-of:${parent}\""
          echo "image-retention: ${PKG} ${child} kept, child of retained ${parent}"
        done < <(jq -r '(.manifests // [])[] | .digest // empty' "$WORK/manifest" 2>/dev/null || true)
      done <<<"$pending"
    done
  fi

  # --- last-version guard: the API rejects deleting a package's last version ---
  if [[ "$total" -gt 0 && "$(jq '[.[] | select(.action == "delete")] | length' "$PLAN")" -eq "$total" ]]; then
    id="$(jq -r '.[0].id' "$PLAN")"
    set_field "$id" '.action = "keep" | .reason = "last-version"'
    echo "::notice::image-retention: every version of ${PKG} expired; keeping newest version ${id} (GitHub rejects deleting a package's last version)"
  fi

  # Initial result column: planned outcome.
  if [[ "$DRY_RUN" == true ]]; then
    jq 'map(.result = (if .action == "delete" then "would delete" else "keep" end))' "$PLAN" >"$PLAN.tmp"
  else
    jq 'map(.result = (if .action == "delete" then "pending" else "keep" end))' "$PLAN" >"$PLAN.tmp"
  fi
  mv "$PLAN.tmp" "$PLAN"

  planned="$(jq '[.[] | select(.action == "delete")] | length' "$PLAN")"
  echo "image-retention: ${PKG}: ${total} version(s), ${planned} planned for deletion"
  jq -r '.[] | "  \(.action) \(.class) id=\(.id) age=\(.age_days)d reason=\(.reason) tags=\(.tags | join(","))"' "$PLAN"

  if [[ "$DRY_RUN" == true ]]; then
    jq --slurpfile plan "$PLAN" '. + [$plan[0][] | select(.action == "delete") | {package, id, tags}]' "$DELETED" >"$DELETED.tmp"
    mv "$DELETED.tmp" "$DELETED"
    KEPT=$((KEPT + total - planned))
    write_summary
    continue
  fi

  # --- delete: re-GET and re-classify each version first (race with concurrent promote) ---
  pkg_kept=$((total - planned))
  while IFS= read -r id; do
    [[ -n "$id" ]] || continue
    want="$(jq -r --argjson id "$id" '.[] | select(.id == $id) | .class' "$PLAN")"
    code="$(with_retry api_once "${api_path}/versions/${id}")"
    case "$code" in
      200) ;;
      404)
        echo "::notice::image-retention: ${PKG} version ${id} no longer exists, skipping"
        set_field "$id" '.result = "gone"'
        continue
        ;;
      *)
        KEPT=$((KEPT + pkg_kept))
        abort "GET ${PKG} version ${id} returned HTTP ${code}: $(head -c 300 "$WORK/api.err")"
        ;;
    esac
    now="$(jq -r --arg s "$STABLE_TAG_PATTERN" --arg p "$PRERELEASE_TAG_PATTERN" "${CLASSIFY}"' cls($s; $p)' "$WORK/api.body" 2>/dev/null || true)"
    if [[ -z "$now" ]]; then
      KEPT=$((KEPT + pkg_kept))
      abort "GET ${PKG} version ${id} returned an unparseable body"
    fi
    if [[ "$now" != "$want" ]]; then
      tags="$(jq -c '.metadata.container.tags // []' "$WORK/api.body")"
      echo "::notice::image-retention: ${PKG} version ${id} reclassified ${want} -> ${now} (tags ${tags}) since listing, skipping"
      set_field "$id" ".result = \"skipped (now ${now})\" | .tags = ${tags}"
      pkg_kept=$((pkg_kept + 1))
      continue
    fi
    code="$(with_retry api_once -X DELETE "${api_path}/versions/${id}")"
    case "$code" in
      204 | 200) ;;
      403)
        KEPT=$((KEPT + pkg_kept))
        set_field "$id" '.result = "failed (403)"'
        abort "$(remediation_message "$OWNER_KIND" "$OWNER" "$PKG" "$REPOSITORY")"
        ;;
      *)
        KEPT=$((KEPT + pkg_kept))
        set_field "$id" ".result = \"failed (${code})\""
        abort "DELETE ${PKG} version ${id} returned HTTP ${code}: $(head -c 300 "$WORK/api.err")"
        ;;
    esac
    set_field "$id" '.result = "deleted"'
    jq --slurpfile plan "$PLAN" --argjson id "$id" '. + [$plan[0][] | select(.id == $id) | {package, id, tags}]' "$DELETED" >"$DELETED.tmp"
    mv "$DELETED.tmp" "$DELETED"
    echo "image-retention: deleted ${PKG} version ${id}"
  done < <(jq -r '.[] | select(.action == "delete") | .id' "$PLAN")
  KEPT=$((KEPT + pkg_kept))
  write_summary
done

write_outputs
echo "image-retention: deleted-count=$(jq 'length' "$DELETED") kept-count=${KEPT}$([[ "$DRY_RUN" == true ]] && echo ' (dry-run: planned)')"
