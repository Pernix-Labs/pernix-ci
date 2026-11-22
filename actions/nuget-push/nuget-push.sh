#!/usr/bin/env bash
# nuget-push: resolve .nupkg files, then dotnet nuget push them to nuget.org
# (Trusted Publishing key from NuGet/login) or, in dry-run, to a local folder feed.
# Usage: nuget-push.sh resolve|push
# Never enable `set -x`: the push step holds a short-lived API key.
set -euo pipefail

readonly NUGET_ORG_SOURCE="https://api.nuget.org/v3/index.json"

PACKAGES="${PACKAGES:-}"
USER_NAME="${USER_NAME:-}"
SKIP_DUPLICATE="${SKIP_DUPLICATE:-true}"
DRY_RUN="${DRY_RUN:-false}"
LOCAL_FEED_DIR="${LOCAL_FEED_DIR:-}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

fail() {
  echo "::error::nuget-push: $*"
  exit 1
}

check_bool() {
  [[ "$2" == "true" || "$2" == "false" ]] || fail "input '$1' must be 'true' or 'false', got '$2'"
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

# Expand each line of PACKAGES as a glob (globstar, nullglob), keep existing
# .nupkg files only (.snupkg excluded), dedupe, print absolute paths.
resolve_packages() {
  local line match abs
  local -a matches
  local -A seen=()
  # IFS empty: unquoted $line glob-expands without word splitting, so paths may hold spaces.
  local IFS=''
  shopt -s globstar nullglob
  while IFS= read -r line; do
    line="$(trim "$line")"
    [[ -z "$line" ]] && continue
    # shellcheck disable=SC2206
    matches=($line)
    for match in "${matches[@]}"; do
      [[ -f "$match" && "$match" == *.nupkg ]] || continue
      abs="$(cd "$(dirname "$match")" && pwd -P)/$(basename "$match")"
      [[ -n "${seen[$abs]:-}" ]] && continue
      seen[$abs]=1
      printf '%s\n' "$abs"
    done
  done <<<"$PACKAGES"
  shopt -u globstar nullglob
}

cmd_resolve() {
  check_bool skip-duplicate "$SKIP_DUPLICATE"
  check_bool dry-run "$DRY_RUN"
  [[ -n "$(trim "$PACKAGES")" ]] || fail "input 'packages' is required (glob or newline list of .nupkg paths)"
  if [[ "$DRY_RUN" != "true" && -z "$(trim "$USER_NAME")" ]]; then
    fail "input 'user' (nuget.org profile name) is required unless dry-run=true"
  fi

  local -a pkgs=()
  local p
  while IFS= read -r p; do
    [[ -n "$p" ]] && pkgs+=("$p")
  done < <(resolve_packages)
  ((${#pkgs[@]} > 0)) || fail "input 'packages' matched zero .nupkg files: '${PACKAGES}'"

  for p in "${pkgs[@]}"; do
    echo "resolved ${p}"
  done
  {
    echo "packages<<NUGET_PUSH_EOF"
    printf '%s\n' "${pkgs[@]}"
    echo "NUGET_PUSH_EOF"
  } >>"$GITHUB_OUTPUT"
}

cmd_push() {
  check_bool skip-duplicate "$SKIP_DUPLICATE"
  check_bool dry-run "$DRY_RUN"

  local -a pkgs=()
  local p
  while IFS= read -r p; do
    p="$(trim "$p")"
    [[ -n "$p" ]] && pkgs+=("$p")
  done <<<"${RESOLVED_PACKAGES:-}"
  ((${#pkgs[@]} > 0)) || fail "no resolved packages to push"

  local -a args
  if [[ "$DRY_RUN" == "true" ]]; then
    local feed="${LOCAL_FEED_DIR:-${RUNNER_TEMP:?RUNNER_TEMP not set}/nuget-local-feed}"
    [[ "$feed" != *://* ]] || fail "input 'local-feed-dir' must be a local directory, got '${feed}'"
    mkdir -p "$feed"
    feed="$(cd "$feed" && pwd -P)"
    echo "dry-run: pushing to local folder feed ${feed} (nuget.org not contacted)"
    args=(--source "$feed")
  else
    [[ -n "${NUGET_API_KEY:-}" ]] || fail "NuGet/login returned no API key; check the nuget.org Trusted Publishing policy"
    echo "::add-mask::${NUGET_API_KEY}"
    args=(--source "$NUGET_ORG_SOURCE" --api-key "$NUGET_API_KEY")
  fi
  [[ "$SKIP_DUPLICATE" == "true" ]] && args+=(--skip-duplicate)

  local count=0
  for p in "${pkgs[@]}"; do
    [[ -f "$p" ]] || fail "package not found: '${p}'"
    echo "::group::dotnet nuget push $(basename "$p")"
    dotnet nuget push "$p" "${args[@]}" ||
      { echo "::endgroup::"; fail "dotnet nuget push failed for '${p}'"; }
    echo "::endgroup::"
    count=$((count + 1))
  done

  echo "pushed-count=${count}" >>"$GITHUB_OUTPUT"
  echo "pushed ${count} package(s)"
}

case "${1:-}" in
  resolve) cmd_resolve ;;
  push) cmd_push ;;
  *) fail "usage: nuget-push.sh resolve|push" ;;
esac
