#!/usr/bin/env bash
# dotnet-test step 4: fail the block after the summary and upload steps ran.
# Fails when the test step did not finish, dotnet test exited non-zero, any
# test failed, no TRX was written, or total-count < min-tests (0 disables).
# Inputs via env: TEST_OUTCOME, EXIT_CODE, FAILED_COUNT, TOTAL_COUNT,
# TRX_COUNT, INPUT_MIN_TESTS, RESULTS_DIRECTORY.
set -euo pipefail

action_path="${GITHUB_ACTION_PATH:-$(dirname "${BASH_SOURCE[0]}")}"
# shellcheck source=/dev/null
source "$action_path/../_shared/lib.sh"

is_uint() { [[ "$1" =~ ^[0-9]+$ ]]; }

min_tests="${INPUT_MIN_TESTS:-1}"
is_uint "$min_tests" || error "min-tests '$min_tests' is not a non-negative integer"

if [[ "${TEST_OUTCOME:-}" != success ]]; then
  error "dotnet-test did not run the tests (test step outcome '${TEST_OUTCOME:-unknown}'). See the error above."
fi

exit_code="${EXIT_CODE:-}"
failed="${FAILED_COUNT:-}"
total="${TOTAL_COUNT:-}"
trx="${TRX_COUNT:-}"
if ! is_uint "$exit_code"; then
  error "dotnet test exit code missing; the test step did not complete"
fi
if ! is_uint "$failed" || ! is_uint "$total" || ! is_uint "$trx"; then
  error "TRX summary missing or unparseable; see the summary step log"
fi

if (( failed > 0 )); then
  error "$failed test(s) failed. See the job summary for the failed tests table."
fi
if (( exit_code != 0 )); then
  error "test host exited $exit_code with 0 failed tests, see log"
fi
if (( trx == 0 )); then
  error "no TRX files in '${RESULTS_DIRECTORY:-}'; tests did not report results. Check discovery and the filter."
fi
if (( min_tests > 0 && total < min_tests )); then
  error "$total test(s) discovered, below min-tests $min_tests. Check the filter and discovery, or lower min-tests (0 disables)."
fi

echo "dotnet-test passed: $total test(s) discovered, 0 failed."
