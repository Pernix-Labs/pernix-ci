#!/usr/bin/env bash
# dotnet-test step 1: detect the runner and TRX format, check Docker, then run
# `dotnet test --no-build` writing TRX into results-directory.
# Fails only on pre-run errors. Test failures are recorded in the exit-code
# output and enforced by enforce.sh after the summary and upload steps.
# Inputs via env: INPUT_WORKING_DIRECTORY, INPUT_PROJECT, INPUT_CONFIGURATION,
# INPUT_GLOBAL_JSON_FILE, INPUT_FILTER, INPUT_TEST_ARGS, INPUT_TRX_FORMAT,
# INPUT_RESULTS_DIRECTORY.
set -euo pipefail

action_path="${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}"
# shellcheck source=/dev/null
source "$action_path/../_shared/lib.sh"

# read_lines <text>: split text into array LINES, one element per line,
# trimming surrounding whitespace and dropping blank lines. No word-splitting.
read_lines() {
  local line
  LINES=()
  [[ -z "$1" ]] && return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] && LINES+=("$line")
  done <<<"$1"
  return 0
}

wd="${INPUT_WORKING_DIRECTORY:-.}"
configuration="${INPUT_CONFIGURATION:-Release}"
global_json="${INPUT_GLOBAL_JSON_FILE:-}"
[[ -n "$global_json" ]] || global_json="$wd/global.json"
results_directory="${INPUT_RESULTS_DIRECTORY:-}"
[[ -n "$results_directory" ]] || error "results-directory is empty; set it to a writable directory"
filter="${INPUT_FILTER:-}"

read_lines "${INPUT_TEST_ARGS:-}"
TEST_ARGS=(${LINES[@]+"${LINES[@]}"})

if ! project="$(python3 -I "$action_path/../_shared/resolve_project.py" "$wd" "${INPUT_PROJECT:-}" 2>&1)"; then
  error "$project"
fi

if ! runner="$(python3 -I "$action_path/select_runner.py" runner "$global_json" 2>&1)"; then
  error "$runner"
fi
set_output test-runner "$runner"

trx_format=""
if [[ "$runner" == mtp ]]; then
  if ! trx_format="$(python3 -I "$action_path/select_runner.py" trx-format "$wd" "${INPUT_TRX_FORMAT:-auto}" 2>&1)"; then
    error "$trx_format"
  fi
fi
set_output trx-format "$trx_format"

if ! timeout 30 docker info >/dev/null 2>&1; then
  error "Docker daemon unreachable; Testcontainers requires Docker on the runner"
fi

mkdir -p "$results_directory"
results_directory="$(cd "$results_directory" && pwd)"
set_output results-directory "$results_directory"

PROJECT="$project"
CFG="$configuration"
RD="$results_directory"

if [[ "$runner" == vstest ]]; then
  cmd=(dotnet test "$PROJECT" --configuration "$CFG" --no-build --results-directory "$RD" --logger "trx;LogFilePrefix=tr")
  [[ -n "$filter" ]] && cmd+=(--filter "$filter")
else
  read_lines "$filter"
  FILTER_ARGS=(${LINES[@]+"${LINES[@]}"})
  case "$PROJECT" in
    *.slnx | *.sln) target=--solution ;;
    *) target=--project ;;
  esac
  if [[ "$trx_format" == xunit ]]; then
    report=--report-xunit-trx
  else
    report=--report-trx
  fi
  cmd=(dotnet test "$target" "$PROJECT" --configuration "$CFG" --no-build --results-directory "$RD" "$report" --ignore-exit-code 8 ${FILTER_ARGS[@]+"${FILTER_ARGS[@]}"})
fi
cmd+=(${TEST_ARGS[@]+"${TEST_ARGS[@]}"})

cd "$wd"
printf 'Running:'
printf ' %q' "${cmd[@]}"
printf '\n'
code=0
"${cmd[@]}" || code=$?
set_output exit-code "$code"
if [[ "$code" -ne 0 ]]; then
  warn "dotnet test exited $code; the enforce step decides the verdict after the summary and upload"
fi
