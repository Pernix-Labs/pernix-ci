#!/usr/bin/env bash
# Fails when a block outside the P4 allow-list references actions/_shared.
# actions/_shared is P4-internal. P5 blocks must stay free of P4 files.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

allowed=(
  secret-scan
  nuget-vulnerability-gate
  nuget-deprecation-report
  dotnet-setup
  dotnet-restore
  dotnet-build
  dotnet-test
)

is_allowed() {
  local dir="$1" a
  [[ "$dir" == "_shared" ]] && return 0
  for a in "${allowed[@]}"; do
    [[ "$dir" == "$a" ]] && return 0
  done
  return 1
}

status=0
[[ -d actions ]] || exit 0

for path in actions/*/; do
  dir="$(basename "$path")"
  is_allowed "$dir" && continue
  while IFS= read -r -d '' file; do
    if grep -q -F '_shared' "$file"; then
      echo "::error file=${file}::${file} references actions/_shared, which is internal to P4 blocks"
      status=1
    fi
  done < <(find "$path" -type f -print0)
done

exit "$status"
