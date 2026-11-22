#!/usr/bin/env bash
# dotnet-unit-solution: write .pernix-ci-units/<name>.slnx holding exactly the
# listed projects, via `dotnet new sln --format slnx` + `dotnet sln add`.
#
# Inputs (env): INPUT_PROJECTS, INPUT_NAME, INPUT_WORKING_DIRECTORY.
# Runner env:   GITHUB_OUTPUT.
set -euo pipefail

OUT_DIR=.pernix-ci-units
MIN_SDK=9.0.200

fail() {
  echo "::error::dotnet-unit-solution: $*"
  exit 1
}

wd="${INPUT_WORKING_DIRECTORY:-.}"
name="${INPUT_NAME:-}"

[[ -n "${GITHUB_OUTPUT:-}" ]] || fail "GITHUB_OUTPUT is not set"
[[ -d "$wd" ]] || fail "working-directory '$wd' does not exist"
[[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "name '$name' must match ^[a-z0-9][a-z0-9-]*\$"

projects=()
while IFS= read -r line; do
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -n "$line" ]] && projects+=("$line")
done <<<"${INPUT_PROJECTS:-}"
((${#projects[@]} > 0)) || fail "projects is empty"

cd "$wd"

missing=()
for p in "${projects[@]}"; do
  [[ "$p" != /* ]] || fail "project '$p' must be relative to working-directory"
  [[ -f "$p" ]] || missing+=("$p")
done
((${#missing[@]} == 0)) || fail "project file(s) not found in '$wd': ${missing[*]}"

solution="$OUT_DIR/$name.slnx"
[[ ! -e "$solution" ]] || fail "'$solution' already exists in '$wd'. Each unit solution is written once per job."

sdk="$(dotnet --version)" || fail "dotnet --version failed in '$wd'. Run dotnet-setup first."
lowest="$(printf '%s\n%s\n' "$MIN_SDK" "${sdk%%-*}" | sort -t. -k1,1n -k2,2n -k3,3n | head -n1)"
[[ "$lowest" == "$MIN_SDK" ]] || fail "SDK $sdk cannot write .slnx. SDK >= $MIN_SDK is required."

dotnet new sln --format slnx --name "$name" --output "$OUT_DIR" ||
  fail "dotnet new sln failed for '$solution'"
dotnet sln "$solution" add "${projects[@]}" ||
  fail "dotnet sln add failed for '$solution'"

echo "dotnet-unit-solution: wrote $solution with ${#projects[@]} project(s)"
printf 'solution=%s\n' "$solution" >>"$GITHUB_OUTPUT"
