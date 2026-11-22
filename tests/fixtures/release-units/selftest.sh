#!/usr/bin/env bash
# Helpers for test-release-units.yml (Req 8.2).
#
#   selftest.sh init <fixture-dir> <repo-dir>   copy fixture, git init, initial commit
#   selftest.sh change <repo-dir> <path>        append a line to <path>, commit
#   selftest.sh assert <unit>...                assert last-touch-sha per unit
#
# init/change write `sha=<commit>` to GITHUB_OUTPUT.
# assert env: CUR (units JSON of this run), PREV (units JSON of the previous
# run), SHA (commit of this case). Named units must have last-touch-sha = SHA,
# all others must keep the PREV value. No names = no unit moves.
set -euo pipefail

fail() {
  echo "::error::$*"
  exit 1
}

commit() {
  git -C "$1" -c user.name=selftest -c user.email=selftest@example.invalid \
    commit -q -m "$2"
  echo "sha=$(git -C "$1" rev-parse HEAD)" >>"$GITHUB_OUTPUT"
}

cmd="${1:-}"
shift || true
case "$cmd" in
  init)
    [[ $# -eq 2 ]] || fail "usage: selftest.sh init <fixture-dir> <repo-dir>"
    rm -rf "$2"
    cp -R "$1" "$2"
    git -C "$2" init -q -b main
    git -C "$2" add -A
    commit "$2" "fixture"
    ;;
  change)
    [[ $# -eq 2 ]] || fail "usage: selftest.sh change <repo-dir> <path>"
    mkdir -p "$(dirname "$1/$2")"
    case "$2" in
      *.cs) line="// selftest change" ;;
      *.props | *.targets | *.csproj) line="<!-- selftest change -->" ;;
      *) line="# selftest change" ;;
    esac
    echo "$line" >>"$1/$2"
    git -C "$1" add -- "$2"
    commit "$1" "change $2"
    ;;
  assert)
    [[ -n "${CUR:-}" && -n "${PREV:-}" && -n "${SHA:-}" ]] || fail "assert needs CUR, PREV, SHA"
    cur_names="$(jq -r '[.[].name] | sort | join(" ")' <<<"$CUR")"
    prev_names="$(jq -r '[.[].name] | sort | join(" ")' <<<"$PREV")"
    [[ "$cur_names" == "$prev_names" ]] || fail "unit set changed: '$prev_names' -> '$cur_names'"
    status=0
    for name in $cur_names; do
      got="$(jq -r --arg n "$name" '.[] | select(.name == $n) | ."last-touch-sha"' <<<"$CUR")"
      before="$(jq -r --arg n "$name" '.[] | select(.name == $n) | ."last-touch-sha"' <<<"$PREV")"
      want="$before"
      for moved in "$@"; do
        [[ "$moved" == "$name" ]] && want="$SHA"
      done
      if [[ "$got" == "$want" ]]; then
        echo "ok: $name last-touch-sha $got"
      else
        echo "::error::$name: expected last-touch-sha $want, got $got"
        status=1
      fi
    done
    exit "$status"
    ;;
  *) fail "usage: selftest.sh init|change|assert ..." ;;
esac
