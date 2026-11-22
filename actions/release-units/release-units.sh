#!/usr/bin/env bash
# release-units entry point. Installs pinned yq, converts the matrix file to
# JSON, and hands it to release_units.py.
#
# Inputs (env): INPUT_UNITS_FILE, INPUT_WORKING_DIRECTORY, INPUT_SOLUTION,
#               INPUT_UNIT, INPUT_OWNER, INPUT_IMAGE_NAME_PREFIX.
# Runner env:   RUNNER_TEMP, GITHUB_OUTPUT, GITHUB_STEP_SUMMARY.
set -euo pipefail

YQ_VERSION=4.54.3
YQ_SHA256_LINUX_AMD64=129534601871538efe0ba4c5e62a34fb1d5f469bcb975c4fddeb467d82974973
YQ_SHA256_LINUX_ARM64=89f69310b61b68d1245065a1241d1fc843f7a36cd6103ffd77ad987613bd1b67
YQ_SHA256_DARWIN_ARM64=a2aebb93b5bdcb61bb76f630e42a0ef6a3ee10842a6516cd7b9e4080786ec593

fail() {
  echo "::error::release-units: $*"
  exit 1
}

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wd="${INPUT_WORKING_DIRECTORY:-.}"
units_file="${INPUT_UNITS_FILE:-.github/release-units.yml}"

[[ -n "${RUNNER_TEMP:-}" ]] || fail "RUNNER_TEMP is not set"
[[ -d "$wd" ]] || fail "working-directory '$wd' does not exist"
[[ "$units_file" != /* ]] || fail "units-file must be relative to working-directory, got '$units_file'"
units_path="$wd/$units_file"
[[ -f "$units_path" ]] || {
  echo "::error file=$units_path::release-units: units file '$units_file' not found in working-directory '$wd'"
  exit 1
}

sha256_ok() {
  local expected="$1" file="$2"
  if command -v sha256sum >/dev/null; then
    printf '%s  %s\n' "$expected" "$file" | sha256sum --check --status -
  else
    printf '%s  %s\n' "$expected" "$file" | shasum -a 256 --check --status -
  fi
}

install_yq() {
  local asset sha
  case "$(uname -s)/$(uname -m)" in
    Linux/x86_64 | Linux/amd64) asset=yq_linux_amd64 sha=$YQ_SHA256_LINUX_AMD64 ;;
    Linux/aarch64 | Linux/arm64) asset=yq_linux_arm64 sha=$YQ_SHA256_LINUX_ARM64 ;;
    Darwin/arm64) asset=yq_darwin_arm64 sha=$YQ_SHA256_DARWIN_ARM64 ;;
    *) fail "unsupported runner platform '$(uname -s)/$(uname -m)' for yq" ;;
  esac
  local dir="$RUNNER_TEMP/yq-$YQ_VERSION"
  yq="$dir/$asset"
  if [[ -f "$yq" ]] && sha256_ok "$sha" "$yq"; then
    return
  fi
  mkdir -p "$dir"
  curl -fsSL --retry 3 --retry-delay 5 -o "$yq" \
    "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${asset}" ||
    fail "download of yq $YQ_VERSION ($asset) failed"
  sha256_ok "$sha" "$yq" || {
    rm -f "$yq"
    fail "yq $YQ_VERSION checksum mismatch, expected SHA-256 $sha"
  }
  chmod 0755 "$yq"
}

install_yq

json="$(mktemp "$RUNNER_TEMP/release-units.XXXXXX")"
trap 'rm -f "$json"' EXIT
if ! "$yq" -o=json '.' "$units_path" >"$json" 2>"$json.err"; then
  echo "::error file=$units_path::release-units: invalid YAML in '$units_file': $(tr '\n' ' ' <"$json.err")"
  rm -f "$json.err"
  exit 1
fi
rm -f "$json.err"

python3 -I "$here/release_units.py" "$json"
