#!/usr/bin/env bash
# nuget-deprecation-report entry point: resolve the project, list deprecated
# packages as JSON, and hand the result to report.py.
# Inputs via env: INPUT_WORKING_DIRECTORY, INPUT_PROJECT. Runner env: RUNNER_TEMP.
# --no-restore: the .NET 10 SDK otherwise restores implicitly, which would hide
# a missing dotnet-restore step. Passes no MSBuild properties.
set -euo pipefail

action_path="${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}"
action_path="$(cd "$action_path" && pwd)"
# shellcheck source=/dev/null
source "$action_path/../_shared/lib.sh"

wd="${INPUT_WORKING_DIRECTORY:-.}"
[[ -n "${RUNNER_TEMP:-}" ]] || error "nuget-deprecation-report: RUNNER_TEMP is not set"

if ! project="$(python3 -I "$action_path/../_shared/resolve_project.py" "$wd" "${INPUT_PROJECT:-}" 2>&1)"; then
  error "$project"
fi
PROJECT="$project"

json="$RUNNER_TEMP/deprecated.json"
stderr="$RUNNER_TEMP/deprecated.stderr"

cd "$wd"
rc=0
dotnet list "$PROJECT" package --deprecated --include-transitive --no-restore \
  --format json --output-version 1 >"$json" 2>"$stderr" || rc=$?

python3 -I "$action_path/report.py" "$json" "$rc" "$stderr" "$PROJECT"
