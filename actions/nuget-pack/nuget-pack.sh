#!/usr/bin/env bash
# nuget-pack: dotnet pack each project at the input version only.
set -euo pipefail

PROJECTS="${PROJECTS:-}"
VERSION="${VERSION:-}"
OUTPUT_DIR="${OUTPUT_DIR:-artifacts/nuget}"
CONFIGURATION="${CONFIGURATION:-Release}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

# Official SemVer 2.0 regex (https://semver.org), no leading "v".
readonly SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-((0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?(\+([0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*))?$'

fail() {
  echo "::error::nuget-pack: $*"
  exit 1
}

[[ -n "$VERSION" ]] || fail "input 'version' is required"
[[ "$VERSION" =~ $SEMVER_RE ]] || fail "input 'version' is not SemVer 2.0 (no leading 'v'): '${VERSION}'"
[[ -n "$CONFIGURATION" ]] || fail "input 'configuration' must not be empty"
[[ -n "$OUTPUT_DIR" ]] || fail "input 'output-dir' must not be empty"

projects=()
while IFS= read -r line; do
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  [[ -f "$line" ]] || fail "project not found: '${line}'"
  projects+=("$line")
done <<<"$PROJECTS"
((${#projects[@]} > 0)) || fail "input 'projects' is required (newline list of .csproj paths)"

mkdir -p "$OUTPUT_DIR"
OUT="$(cd "$OUTPUT_DIR" && pwd -P)"

shopt -s nullglob
existing=("$OUT"/*.nupkg)
shopt -u nullglob
((${#existing[@]} == 0)) || fail "output-dir '${OUT}' already contains .nupkg files (D8): ${existing[*]}"

for proj in "${projects[@]}"; do
  echo "::group::dotnet pack ${proj}"
  dotnet pack "$proj" \
    -c "$CONFIGURATION" \
    -o "$OUT" \
    "-p:Version=${VERSION}" \
    "-p:PackageVersion=${VERSION}" \
    -p:ContinuousIntegrationBuild=true ||
    { echo "::endgroup::"; fail "dotnet pack failed for '${proj}'"; }
  echo "::endgroup::"
done

shopt -s nullglob
packages=("$OUT"/*.nupkg)
shopt -u nullglob
((${#packages[@]} > 0)) || fail "no .nupkg produced in '${OUT}'"

for pkg in "${packages[@]}"; do
  nuspec="$(unzip -p "$pkg" '*.nuspec')" || fail "cannot read .nuspec from '${pkg}'"
  actual="$(sed -n 's:.*<version>\([^<]*\)</version>.*:\1:p' <<<"$nuspec" | head -n1)"
  [[ "$actual" == "$VERSION" ]] || fail "package '${pkg}' has version '${actual}', expected '${VERSION}'"
  echo "packed ${pkg} (${actual})"
done

{
  echo "packages<<NUGET_PACK_EOF"
  printf '%s\n' "${packages[@]}"
  echo "NUGET_PACK_EOF"
  echo "package-count=${#packages[@]}"
  echo "output-dir=${OUT}"
} >>"$GITHUB_OUTPUT"
