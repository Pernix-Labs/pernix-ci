#!/usr/bin/env bash
# Scripted repo for release-tag tests.
#
#   selftest.sh init <dir>
#
# Creates <dir>/origin.git (bare) and <dir>/repo (clone). `main` holds
# commits c1, c2. Tags: annotated `svc/v1.2.3` on c1, lightweight
# `lib/v1.0.0-rc.1` on c2, annotated `svc/v9.9.9` on an orphan-branch commit
# that is not reachable from main. All pushed to origin, then fetched.
# Writes c1, c2, orphan shas to GITHUB_OUTPUT when set, else stdout.
set -euo pipefail

[[ "${1:-}" == "init" && -n "${2:-}" ]] || {
  echo "usage: selftest.sh init <dir>" >&2
  exit 2
}
dir="$2"
[[ ! -e "$dir/repo" && ! -e "$dir/origin.git" ]] || {
  echo "selftest.sh: $dir already holds repo or origin.git" >&2
  exit 1
}
mkdir -p "$dir"

export GIT_AUTHOR_NAME=selftest GIT_AUTHOR_EMAIL=selftest@example.invalid
export GIT_COMMITTER_NAME=selftest GIT_COMMITTER_EMAIL=selftest@example.invalid
g() { git -C "$dir/repo" -c init.defaultBranch=main -c commit.gpgsign=false -c tag.gpgsign=false "$@"; }

git -c init.defaultBranch=main init -q --bare "$dir/origin.git"
git -c init.defaultBranch=main init -q "$dir/repo"
g remote add origin "$dir/origin.git"

echo one >"$dir/repo/file.txt"
g add file.txt
g commit -q -m c1
c1="$(g rev-parse HEAD)"
g tag -a -m "svc 1.2.3" svc/v1.2.3

echo two >"$dir/repo/file.txt"
g commit -q -am c2
c2="$(g rev-parse HEAD)"
g tag lib/v1.0.0-rc.1

g checkout -q --orphan side
echo side >"$dir/repo/file.txt"
g add file.txt
g commit -q -m orphan
orphan="$(g rev-parse HEAD)"
g tag -a -m "svc 9.9.9" svc/v9.9.9
g checkout -q main
g branch -q -D side

g push -q origin main --tags
g fetch -q origin

out="${GITHUB_OUTPUT:-/dev/stdout}"
{
  echo "c1=$c1"
  echo "c2=$c2"
  echo "orphan=$orphan"
} >>"$out"
