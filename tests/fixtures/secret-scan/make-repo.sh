#!/usr/bin/env bash
# make-repo.sh <dir> [--allowlist]
#
# Builds a throwaway git repo at <dir> whose first commit adds config.env with
# a fake GitHub token (ghp_ + 36 random alphanumerics generated at runtime, so
# no secret-shaped literal lives in this repo).
#
# --allowlist also commits a .gitleaksignore holding that finding's
# fingerprint (<commit>:<file>:<rule>:<line>), so gitleaks reports nothing.
set -euo pipefail

usage() {
  echo "usage: make-repo.sh <dir> [--allowlist]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 2 ]] || usage
dir=$1
allowlist=false
if [[ $# -eq 2 ]]; then
  [[ "$2" == "--allowlist" ]] || usage
  allowlist=true
fi

if [[ -e "$dir" ]] && [[ -n "$(ls -A "$dir")" ]]; then
  echo "make-repo.sh: $dir exists and is not empty" >&2
  exit 1
fi
mkdir -p "$dir"

g() {
  git -C "$dir" -c user.name=secret-scan-fixture -c user.email=fixture@example.invalid \
    -c commit.gpgsign=false "$@"
}

g init -q -b main

suffix="$(python3 -I -c 'import secrets, string
alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(36)))')"
printf 'GITHUB_TOKEN=ghp_%s\n' "$suffix" >"$dir/config.env"
g add config.env
g commit -q -m "add config"

if [[ "$allowlist" == "true" ]]; then
  commit="$(g rev-parse HEAD)"
  printf '%s:config.env:github-pat:1\n' "$commit" >"$dir/.gitleaksignore"
  g add .gitleaksignore
  g commit -q -m "allowlist fixture token"
fi

echo "make-repo.sh: created $dir (allowlist=$allowlist)"
