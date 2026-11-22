# dotnet-test

Runs the caller's built .NET tests on VSTest or Microsoft.Testing.Platform (MTP), writes TRX files, writes a job summary from them, uploads them as an artifact, and fails on test failures or too few tests. Run it after `dotnet-setup`, `dotnet-restore`, and `dotnet-build` with the same `configuration`.

The block runs four steps:

1. Detect the runner and TRX format, check Docker, and run `dotnet test --no-build`. This step fails only on pre-run errors. Test failures are recorded and enforced in step 4.
2. Parse every `*.trx` in `results-directory` and write the job summary and count outputs. Runs even when step 1 fails.
3. Upload `<results-directory>/**/*.trx` as artifact `artifact-name` with `actions/upload-artifact` (SHA-pinned) when `upload-results` is `true`. Runs even when step 1 fails. A run with no TRX files warns.
4. Fail the block when a rule below is broken.

When `project` is empty, the block looks at the top level of `working-directory` and picks exactly one `*.slnx`, else exactly one `*.sln`, else exactly one `*.csproj`.

## Inputs

| Name | Default | Description |
|---|---|---|
| `working-directory` | `.` | Directory that holds the solution or project. |
| `project` | auto-detect | Solution or project path, relative to `working-directory`. |
| `configuration` | `Release` | Value passed to `--configuration`. Must match the build. |
| `global-json-file` | `<working-directory>/global.json` | `global.json` used for runner detection. |
| `filter` | empty | VSTest: one `--filter` expression, passed as a single value. MTP: filter arguments, one per line, for example `--filter-class` and `Pernix.*` on separate lines. |
| `test-args` | empty | Extra `dotnet test` arguments, one per line, appended last. |
| `trx-format` | `auto` | MTP only. `mtp` passes `--report-trx`, `xunit` passes `--report-xunit-trx`, `auto` detects it. |
| `min-tests` | `1` | Minimum discovered tests summed over all TRX files in the run. `0` disables the check. |
| `results-directory` | `${{ runner.temp }}/test-results` | Directory for TRX files. |
| `upload-results` | `true` | Upload TRX files as a workflow artifact. |
| `artifact-name` | `test-results` | Artifact name. Must be unique per job and matrix leg. |

`filter` lines and `test-args` lines are trimmed, blank lines are dropped, and lines are never split on spaces or shell-expanded.

## Outputs

| Name | Description |
|---|---|
| `test-runner` | `vstest` or `mtp`. |
| `trx-format` | `mtp` or `xunit` in MTP mode. Empty in VSTest mode. |
| `passed-count` | Passed tests, summed over all TRX files. |
| `failed-count` | Failed, errored, timed-out, and aborted tests, summed over all TRX files. |
| `skipped-count` | Discovered tests that neither passed nor failed (`total - passed - failed`), for example skipped or explicit-only tests. |
| `total-count` | Discovered tests, summed over all TRX files. |
| `results-directory` | Absolute directory that holds the TRX files. |

## Permissions

```yaml
permissions:
  contents: read
```

## Runner detection

The block reads `test.runner` from `global-json-file`. Comments and trailing commas are allowed. When the value is `Microsoft.Testing.Platform` (any case), the block runs in MTP mode. A missing file, a missing key, or any other value selects VSTest mode.

VSTest mode runs:

```sh
dotnet test <project> --configuration <configuration> --no-build \
  --results-directory <results-directory> --logger "trx;LogFilePrefix=tr" \
  [--filter <filter>] <test-args...>
```

MTP mode runs (`--solution` for `.slnx` and `.sln`, `--project` for `.csproj`):

```sh
dotnet test --solution <project> --configuration <configuration> --no-build \
  --results-directory <results-directory> <--report-trx|--report-xunit-trx> \
  --ignore-exit-code 8 <filter lines...> <test-args...>
```

## TRX format

MTP mode needs a TRX reporter. With `trx-format: auto`, the block reads every `project.assets.json` under an `obj` directory below `working-directory`. Projects whose libraries include `Microsoft.Testing.Platform` are the MTP test projects.

1. All of them reference `Microsoft.Testing.Extensions.TrxReport`: `mtp`, which passes `--report-trx`.
2. Else all of them reference xunit.v3 (`xunit.v3.core`, or `xunit.v3.core.mtp-v1`/`-v2` in xunit.v3 4.x): `xunit`, which passes `--report-xunit-trx`. No extra package is needed.
3. Else the block fails. Reference `Microsoft.Testing.Extensions.TrxReport`, use xunit.v3, or set `trx-format`.

No MTP test project found fails the block with "restore first". Set `trx-format` when the intermediate output path is outside `working-directory`.

## Pass rules

The block fails when any of these hold. The error names the rule.

1. Any test failed, errored, timed out, or aborted. The job summary lists failed tests with their messages.
2. `dotnet test` exited non-zero with zero failed tests. The error reads "test host exited <code>, see log".
3. No TRX file was written.
4. `total-count` is below `min-tests`.

## Zero-test rule

A single project with zero tests never fails the block. MTP mode passes `--ignore-exit-code 8`, and VSTest tolerates empty projects. This allows projects whose tests are all `[Fact(Explicit = true)]` or skipped by default.

`min-tests` applies to the whole run. The default `1` fails a run in which no test was discovered, which catches a filter that matches nothing or broken discovery. Set `min-tests: 0` for a run that is allowed to discover nothing.

## Docker

The block runs `docker info` (30 second timeout) before the tests in both modes and fails when the Docker daemon is unreachable, because Testcontainers needs Docker on the runner. `ubuntu-latest` runners have Docker. The block sets no Testcontainers environment variables. Set them on the step or job when needed.

## Artifact name

`actions/upload-artifact` rejects a second artifact with the same name in one workflow run. When the block runs in several jobs or matrix legs, give each a unique `artifact-name`, for example `test-results-${{ matrix.os }}`.

## Checkout

The block does not check out code. Run `actions/checkout` first. No special options are needed.

## Examples

VSTest:

```yaml
steps:
  - uses: actions/checkout@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-build@<sha> # vX.Y.Z
  - id: test
    uses: Pernix-Labs/pernix-ci/actions/dotnet-test@<sha> # vX.Y.Z
    with:
      filter: Category!=Slow
  - run: echo "${{ steps.test.outputs.passed-count }} of ${{ steps.test.outputs.total-count }} passed"
```

MTP (`global.json` sets `"test": { "runner": "Microsoft.Testing.Platform" }`), in a matrix:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        suite: [unit, integration]
    steps:
      - uses: actions/checkout@<sha> # vX.Y.Z
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-build@<sha> # vX.Y.Z
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-test@<sha> # vX.Y.Z
        with:
          filter: |
            --filter-trait
            Suite=${{ matrix.suite }}
          test-args: |
            --no-progress
          artifact-name: test-results-${{ matrix.suite }}
```
