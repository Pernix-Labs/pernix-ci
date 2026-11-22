#!/usr/bin/env bash
# dotnet-setup helper.
#   detect.sh            resolve the global.json path, output `global-json`.
#   detect.sh --resolve  output `dotnet-version`, set CLI env opt-outs.
# Inputs via env: INPUT_WORKING_DIRECTORY, INPUT_GLOBAL_JSON_FILE, INPUT_DOTNET_VERSION.
set -euo pipefail

# shellcheck source=/dev/null
source "${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}/../_shared/lib.sh"

wd="${INPUT_WORKING_DIRECTORY:-.}"
[[ -d "$wd" ]] || error "working-directory '$wd' does not exist."

detect() {
  local gj="${INPUT_GLOBAL_JSON_FILE:-}" versions
  versions="$(printf '%s' "${INPUT_DOTNET_VERSION:-}" | tr -d '[:space:]')"

  if [[ -n "$gj" ]]; then
    [[ -f "$gj" ]] || error "global-json-file '$gj' does not exist. Fix the path, or unset global-json-file and set dotnet-version."
  else
    gj="$wd/global.json"
    if [[ ! -f "$gj" ]]; then
      gj=""
      if [[ -z "$versions" ]]; then
        error "No SDK to install: '$wd/global.json' not found and dotnet-version is empty. Set global-json-file to the caller's global.json, or set dotnet-version (for example 10.0.x)."
      fi
    fi
  fi

  set_output global-json "$gj"
}

resolve() {
  local version
  if ! version="$(cd "$wd" && dotnet --version)"; then
    error "dotnet --version failed in '$wd'. Check that global.json in that directory matches an installed SDK."
  fi
  [[ -n "$version" ]] || error "dotnet --version printed nothing in '$wd'."
  [[ -n "${GITHUB_ENV:-}" ]] || error "GITHUB_ENV is not set."
  {
    echo "DOTNET_NOLOGO=1"
    echo "DOTNET_CLI_TELEMETRY_OPTOUT=1"
  } >>"$GITHUB_ENV"
  set_output dotnet-version "$version"
}

case "${1:-}" in
  "") detect ;;
  --resolve) resolve ;;
  *) error "detect.sh: unknown argument '$1'" ;;
esac
