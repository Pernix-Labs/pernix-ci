#!/usr/bin/env bash
# dotnet-build helper: resolve the project, reject forbidden build-args, then
# `dotnet build` it in Release with --no-restore.
# Inputs via env: INPUT_WORKING_DIRECTORY, INPUT_PROJECT, INPUT_CONFIGURATION,
# INPUT_BUILD_ARGS (newline list, one argument per line).
# Passes no MSBuild properties of its own, so caller settings apply (Req 8.2, 1.11).
set -euo pipefail

action_path="${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}"
# shellcheck source=/dev/null
source "$action_path/../_shared/lib.sh"

wd="${INPUT_WORKING_DIRECTORY:-.}"
configuration="${INPUT_CONFIGURATION:-Release}"

BUILD_ARGS=()
if [[ -n "${INPUT_BUILD_ARGS:-}" ]]; then
  mapfile -t lines <<<"$INPUT_BUILD_ARGS"
  for line in "${lines[@]}"; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] && BUILD_ARGS+=("$line")
  done
fi

if ! check_out="$(python3 -I "$action_path/check_args.py" "${BUILD_ARGS[@]}" 2>&1)"; then
  while IFS= read -r msg; do
    printf '::error::%s\n' "$msg"
  done <<<"$check_out"
  error "dotnet-build rejected build-args before building. Remove the arguments named above."
fi

if ! project="$(python3 -I "$action_path/../_shared/resolve_project.py" "$wd" "${INPUT_PROJECT:-}" 2>&1)"; then
  error "$project"
fi
set_output project "$project"

PROJECT="$project"
CONFIGURATION="$configuration"

cd "$wd"
if ! dotnet build "$PROJECT" --configuration "$CONFIGURATION" --no-restore "${BUILD_ARGS[@]}"; then
  error "dotnet build failed for '$PROJECT' in '$wd'. See the log above. Warnings fail the build when the caller sets TreatWarningsAsErrors."
fi
