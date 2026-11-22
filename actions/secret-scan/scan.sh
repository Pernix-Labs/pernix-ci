#!/usr/bin/env bash
# secret-scan entry point. Resolves the commit range for the triggering event,
# runs gitleaks with redaction, and hands the JSON report to report.py.
#
# Inputs (env): INPUT_SCAN_MODE, INPUT_CONFIG_PATH, INPUT_WORKING_DIRECTORY.
# Runner env:   GITHUB_EVENT_NAME, GITHUB_EVENT_PATH, GITHUB_SHA, RUNNER_TEMP.
set -euo pipefail

GITLEAKS_VERSION=8.30.1
GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# lib.sh is linted on its own. lint.yml runs shellcheck without -x.
# shellcheck source=/dev/null
source "$here/../_shared/lib.sh"

FETCH_HINT="set actions/checkout fetch-depth: 0"
ZERO_SHA=0000000000000000000000000000000000000000

mode="${INPUT_SCAN_MODE:-auto}"
config="${INPUT_CONFIG_PATH:-}"
wd="${INPUT_WORKING_DIRECTORY:-.}"

[[ -n "${RUNNER_TEMP:-}" ]] || error "secret-scan: RUNNER_TEMP is not set"

case "$mode" in
  auto | full-history) ;;
  *) error "secret-scan: invalid scan-mode '$mode'. Use auto or full-history." ;;
esac

[[ -d "$wd" ]] || error "secret-scan: working-directory '$wd' does not exist"
if [[ "$(git -C "$wd" rev-parse --is-inside-work-tree 2>/dev/null)" != "true" ]]; then
  error "secret-scan: working-directory '$wd' is not a git repository. Run actions/checkout first."
fi

if [[ -n "$config" ]]; then
  [[ "$config" == /* ]] || config="$wd/$config"
  [[ -f "$config" ]] || error "secret-scan: config-path '$INPUT_CONFIG_PATH' not found (resolved to '$config')"
fi

# event_field <dotted.key>: print a string field from the event payload, or empty.
event_field() {
  python3 -I -c '
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split("."):
    value = value.get(key) if isinstance(value, dict) else None
print(value if isinstance(value, str) else "")
' "$GITHUB_EVENT_PATH" "$1"
}

has_commit() {
  git -C "$wd" cat-file -e "$1^{commit}" 2>/dev/null
}

shallow="$(git -C "$wd" rev-parse --is-shallow-repository)"

# Range resolution. log_opts empty = all history. endpoints = commits that must
# exist locally for the range to be complete.
log_opts=""
scope="full history"
endpoints=()

set_range() {
  local base=$1 head=$2
  [[ -n "$base" && -n "$head" ]] || error "secret-scan: event payload lacks range endpoints for ${GITHUB_EVENT_NAME}"
  log_opts="$base..$head"
  scope="range $base..$head"
  endpoints=("$base" "$head")
}

set_reachable() {
  log_opts="$1"
  scope="history of $1"
  endpoints=("$1")
}

event="${GITHUB_EVENT_NAME:-}"
if [[ "$mode" == "auto" && -n "$event" && -z "${GITHUB_EVENT_PATH:-}" ]]; then
  error "secret-scan: GITHUB_EVENT_PATH is not set"
fi

if [[ "$mode" == "auto" ]]; then
  case "$event" in
    pull_request | pull_request_target)
      set_range "$(event_field pull_request.base.sha)" "$(event_field pull_request.head.sha)"
      ;;
    merge_group)
      set_range "$(event_field merge_group.base_sha)" "$(event_field merge_group.head_sha)"
      ;;
    push)
      [[ -n "${GITHUB_SHA:-}" ]] || error "secret-scan: GITHUB_SHA is not set"
      before="$(event_field before)"
      if [[ -z "$before" || "$before" == "$ZERO_SHA" ]]; then
        set_reachable "$GITHUB_SHA"
      elif has_commit "$before"; then
        set_range "$before" "$GITHUB_SHA"
      elif [[ "$shallow" != "true" ]]; then
        # Force-push: old tip is unreachable. Scan a superset.
        set_reachable "$GITHUB_SHA"
      else
        set_range "$before" "$GITHUB_SHA"
      fi
      ;;
  esac
fi

# Shallow guard (Req 3.4): never scan a truncated history and pass.
if [[ "$shallow" == "true" ]]; then
  if [[ ${#endpoints[@]} -lt 2 ]]; then
    error "secret-scan: repository is shallow, $scope is incomplete. $FETCH_HINT"
  fi
  for sha in "${endpoints[@]}"; do
    has_commit "$sha" || error "secret-scan: commit $sha is missing from the shallow clone. $FETCH_HINT"
  done
  if ! git -C "$wd" merge-base "${endpoints[0]}" "${endpoints[1]}" >/dev/null 2>&1; then
    error "secret-scan: shallow clone cuts $scope. $FETCH_HINT"
  fi
else
  for sha in "${endpoints[@]}"; do
    has_commit "$sha" || error "secret-scan: commit $sha not found in '$wd'. Check the checkout ref."
  done
fi

# Install gitleaks (pinned version + SHA-256).
tarball="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
install_dir="$RUNNER_TEMP/gitleaks-$GITLEAKS_VERSION"
mkdir -p "$install_dir"
curl -fsSL --retry 3 -o "$install_dir/$tarball" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/$tarball" ||
  error "secret-scan: download of gitleaks $GITLEAKS_VERSION failed"
if ! echo "$GITLEAKS_SHA256  $install_dir/$tarball" | sha256sum -c --status -; then
  error "secret-scan: gitleaks $GITLEAKS_VERSION checksum mismatch, expected SHA-256 $GITLEAKS_SHA256"
fi
tar -xzf "$install_dir/$tarball" -C "$install_dir" gitleaks
gitleaks="$install_dir/gitleaks"

report="$RUNNER_TEMP/gitleaks.json"
rm -f "$report"

args=(git --redact --no-banner --exit-code 0
  --report-format json --report-path "$report"
  --gitleaks-ignore-path "$wd")
[[ -n "$log_opts" ]] && args+=(--log-opts "$log_opts")
[[ -n "$config" ]] && args+=(--config "$config")
args+=("$wd")

echo "secret-scan: gitleaks $GITLEAKS_VERSION, mode $mode, scanning $scope"
if ! "$gitleaks" "${args[@]}"; then
  error "secret-scan: gitleaks exited with an error, see log above"
fi

python3 -I "$here/report.py" "$report" "$scope"
