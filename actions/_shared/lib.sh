#!/usr/bin/env bash
# Shared helpers for pernix-ci blocks. Source it, do not execute it:
#   source "${GITHUB_ACTION_PATH}/../_shared/lib.sh"

# error <msg>: emit a workflow error annotation and exit 1.
error() {
  printf '::error::%s\n' "$*"
  exit 1
}

# warn <msg>: emit a workflow warning annotation.
warn() {
  printf '::warning::%s\n' "$*"
}

# set_output <key> <value>: append a step output to GITHUB_OUTPUT using the
# heredoc delimiter form, so multi-line values are safe.
set_output() {
  if [[ $# -ne 2 ]]; then
    error "set_output: expected <key> <value>, got $# argument(s)"
  fi
  local key=$1 value=$2 delim
  if [[ -z "${GITHUB_OUTPUT:-}" ]]; then
    error "set_output: GITHUB_OUTPUT is not set"
  fi
  if [[ -z "$key" || "$key" == *$'\n'* ]]; then
    error "set_output: invalid key"
  fi
  while :; do
    delim="ghadelimiter_$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')"
    [[ "$value" != *"$delim"* ]] && break
  done
  printf '%s<<%s\n%s\n%s\n' "$key" "$delim" "$value" "$delim" >>"$GITHUB_OUTPUT"
}

# summary <file>: append the file's contents to GITHUB_STEP_SUMMARY.
summary() {
  if [[ $# -ne 1 ]]; then
    error "summary: expected <file>, got $# argument(s)"
  fi
  if [[ -z "${GITHUB_STEP_SUMMARY:-}" ]]; then
    error "summary: GITHUB_STEP_SUMMARY is not set"
  fi
  if [[ ! -f "$1" ]]; then
    error "summary: file not found: $1"
  fi
  cat -- "$1" >>"$GITHUB_STEP_SUMMARY"
}
