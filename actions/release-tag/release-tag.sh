#!/usr/bin/env bash
# release-tag entry point. Hands the inputs to release_tag.py.
#
# Inputs (env): INPUT_TAG, INPUT_UNIT_NAMES, INPUT_DEFAULT_BRANCH,
#               INPUT_COMMIT, INPUT_WORKING_DIRECTORY.
# Runner env:   GITHUB_OUTPUT, GITHUB_STEP_SUMMARY.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v python3 >/dev/null || {
  echo "::error::release-tag: python3 not found on the runner"
  exit 1
}

python3 -I "$here/release_tag.py"
