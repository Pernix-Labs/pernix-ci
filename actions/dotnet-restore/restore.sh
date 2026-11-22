#!/usr/bin/env bash
# dotnet-restore helper: resolve the project, then `dotnet restore` it.
# Inputs via env: INPUT_WORKING_DIRECTORY, INPUT_PROJECT, INPUT_LOCKED_MODE.
# Passes no MSBuild properties, so caller settings apply untouched (Req 1.11, 7.4).
set -euo pipefail

action_path="${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}"
# shellcheck source=/dev/null
source "$action_path/../_shared/lib.sh"

wd="${INPUT_WORKING_DIRECTORY:-.}"
locked="${INPUT_LOCKED_MODE:-false}"

case "$locked" in
  true | false) ;;
  *) error "locked-mode must be 'true' or 'false', got '$locked'." ;;
esac

if ! project="$(python3 -I "$action_path/../_shared/resolve_project.py" "$wd" "${INPUT_PROJECT:-}" 2>&1)"; then
  error "$project"
fi
set_output project "$project"

args=(restore "$project")
[[ "$locked" == true ]] && args+=(--locked-mode)

cd "$wd"
if ! dotnet "${args[@]}"; then
  if [[ "$locked" == true ]]; then
    error "dotnet restore failed for '$project' in '$wd'. With locked-mode, packages.lock.json must match the project: run 'dotnet restore' locally and commit the updated lock files."
  fi
  error "dotnet restore failed for '$project' in '$wd'. See the log above, and reproduce locally with 'dotnet restore $project'."
fi
