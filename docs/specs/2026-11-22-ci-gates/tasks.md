---
status: approved
createdAt: 2026-11-22T19:18:04Z
updatedAt: 2026-11-22T20:02:31Z
approvedAt: 2026-11-22T19:21:15Z
completedAt: 2026-11-22T20:02:31Z
---

# Tasks: CI gates (P4)

**Spec ID:** 2026-11-22-ci-gates
**Requirements:** [requirements.md](./requirements.md)
**Design:** [design.md](./design.md)

<!--
DAG grammar: see orca-spec-workflow templates/tasks.md. Checkboxes = plan notation, never ticked.
Runtime state lives in orca task-list + journal.md.

Common rules for every task (binding, from requirements Req 1 + design "Block rules"):
- Read docs/specs/2026-11-22-ci-gates/requirements.md + design.md sections named in task.
- Composite action, `shell: bash` per run step, `run:` = one command calling script via "${{ github.action_path }}/…".
- Inputs reach scripts only via step `env:` (R-injection). Never `${{ inputs.* }}` inside `run:` text.
- `.sh`: `#!/usr/bin/env bash` + `set -euo pipefail`, shellcheck-clean. `.py`: python3 stdlib only, invoked `python3 -I`.
- Multi-arg inputs: newline list → `mapfile`, no word-splitting, no eval (R-args).
- Fail closed (R-failclosed). Summaries via _shared md.py limits (R-summary). No added `-p:` switches (R-noprops).
- Third-party actions: full 40-char SHA + `# vX.Y.Z` comment; resolve SHA with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (deref annotated tags).
- Binaries: pinned version + SHA-256 constant, `sha256sum -c` before exec.
- Never echo secrets. Block permissions: `contents: read` max.
- Self-test workflow: `on: pull_request` + `push: branches: [main]`, top-level `permissions: contents: read`, `uses: ./actions/<block>`, negative cases via `continue-on-error: true` + outcome assert step, runs `python3 -I -m unittest discover -s tests/unit/<block>` and `-s tests/unit/_shared`.
- Create only listed files. Do not touch other blocks, P5 paths, requirements.md, design.md.
-->

- [ ] 1 Shared helpers `actions/_shared` + unit tests
  - Files: actions/_shared/lib.sh, actions/_shared/resolve_project.py, actions/_shared/globaljson.py, actions/_shared/md.py, tests/unit/_shared/test_resolve_project.py, tests/unit/_shared/test_globaljson.py, tests/unit/_shared/test_md.py
  - Verify: shellcheck actions/_shared/lib.sh clean; `python3 -I -m unittest discover -s tests/unit/_shared` passes
  - Purpose: shared bash/python helpers reached by P4 blocks at `${{ github.action_path }}/../_shared/` (design "Repo layout", "`actions/_shared`").
  - `lib.sh` (sourced): `error <msg>` → `::error::<msg>` + exit 1; `warn <msg>` → `::warning::`; `set_output <key> <value>` writes `GITHUB_OUTPUT` (heredoc delimiter form, random delimiter, multi-line safe); `summary <file>` appends to `GITHUB_STEP_SUMMARY`.
  - `resolve_project.py <working-directory> [project]`: `project` non-empty → must exist relative to `working-directory`, print path; empty → top level of `working-directory`: exactly one `*.slnx` → it; else exactly one `*.sln`; else exactly one `*.csproj`; else exit 1 with message listing candidates and naming `project` input.
  - `globaljson.py <path> <dotted.key>`: strip `//` + `/* */` comments outside strings, strip trailing commas, `json.loads`, print value (empty if absent). Missing file → print empty, exit 0. Parse error → stderr message naming file, exit 1. Importable function too.
  - `md.py`: `cell(s, max=500)` escapes `|`, replaces newlines with `<br>`, truncates with `…`; `table(headers, rows, limit=200)` returns markdown and appends "N more rows omitted" when over limit. Importable module.
  - Unit tests: slnx/sln/csproj precedence, ambiguity, explicit project missing; JSONC comments inside/outside strings, trailing commas, nested key `test.runner`, parse error; escaping, truncation, row limit.

- [ ] 2 Repo foundations: lint workflow, `_shared` guard, root README
  - Files: .github/workflows/lint.yml, .github/scripts/check-shared-usage.sh, README.md
  - Verify: actionlint .github/workflows/lint.yml clean; shellcheck .github/scripts/check-shared-usage.sh clean; guard script exits 0 on current tree and exits 1 on a temp `actions/p5-dummy/action.yml` referencing `_shared` (remove temp after)
  - Purpose: Req 10, Req 11, design "`lint.yml`", "Root `README.md`", approver note (P5 blocks must not depend on `actions/_shared`).
  - `lint.yml`: `on: pull_request` + `push: branches: [main]`, `permissions: contents: read`. Steps: `actions/checkout` (SHA-pinned) → download shellcheck + actionlint release binaries (linux x86_64, pinned versions, SHA-256 constants, `sha256sum -c`, into `$RUNNER_TEMP/bin`, add to `GITHUB_PATH`) → `actionlint -color` → `git ls-files -z '*.sh' | xargs -0 -r shellcheck` → `.github/scripts/check-shared-usage.sh`.
  - `check-shared-usage.sh`: allow-list P4 blocks `secret-scan nuget-vulnerability-gate nuget-deprecation-report dotnet-setup dotnet-restore dotnet-build dotnet-test`. Any file under `actions/<dir>/` where `<dir>` not in allow-list and not `_shared` containing string `_shared` → `::error file=…::` + exit 1. Keeps P5 blocks free of P4 files.
  - `README.md` sections in order: `# pernix-ci` (purpose: reusable GitHub Actions building blocks for Pernix .NET repos) → `## Using a block` (`uses: Pernix-Labs/pernix-ci/actions/<block-name>@<sha|vX.Y.Z>`, recommend full SHA or `vX.Y.Z`, caller owns `actions/checkout`, `secret-scan` needs `fetch-depth: 0`) → `## Conventions` (Req 10.2 list; note `actions/_shared/` is P4-internal, other blocks must not use it, enforced by lint) → `## Policy` (Req 10.6: CI fails on secrets + high/critical vulns, moderate/low report only, app code keeps `TreatWarningsAsErrors`, callers own NuGetAudit level, recommend `NuGetAuditMode=all` + `NuGetAuditLevel=high`) → `## Gates` (table: block, purpose, link `actions/<block>/README.md` for the 7 P4 blocks per design "Block catalogue") → `## Artifacts` (placeholder: owned by P5 ci-artifacts) → `## Workflows` (placeholder: owned by P6) → `## Development` (lint, self-tests `test-<block-name>.yml`, fixtures `tests/fixtures/<block-name>/`, unit tests `tests/unit/<block-name>/`).

- [ ] 3 Block `secret-scan`
  - Deps: 1
  - Files: actions/secret-scan/action.yml, actions/secret-scan/README.md, actions/secret-scan/scan.sh, actions/secret-scan/report.py, tests/unit/secret-scan/test_report.py, tests/unit/secret-scan/fixtures/gitleaks-report.json, tests/fixtures/secret-scan/make-repo.sh, .github/workflows/test-secret-scan.yml
  - Verify: shellcheck + actionlint clean on task files; `python3 -I -m unittest discover -s tests/unit/secret-scan` passes; report.py never reads `Secret`/`Match` (grep)
  - Purpose: Req 3, design "`secret-scan`".
  - Inputs `scan-mode` (`auto`|`full-history`, default `auto`), `config-path` (default empty), `working-directory` (default `.`). Output `findings-count`. Permissions `contents: read`. No secret inputs, no license (gitleaks CLI binary, pinned latest stable 8.x, linux x64 tarball, SHA-256 constant in `scan.sh`).
  - `scan.sh`: range table from design (pull_request/pull_request_target base..head from `GITHUB_EVENT_PATH`; merge_group base_sha..head_sha; push before..sha, all-zero `before` → `github.sha` history, `before` missing in non-shallow repo → `github.sha` history; other events / `full-history` → all history). Shallow guard: `git rev-parse --is-shallow-repository` true AND endpoint missing → `error` "set actions/checkout fetch-depth: 0". Run `gitleaks git --redact --no-banner --exit-code 0 --report-format json --report-path "$RUNNER_TEMP/gitleaks.json" [--log-opts …] [--config …] <working-directory>`; gitleaks non-zero → tool error fail. Report stays in `$RUNNER_TEMP`.
  - `report.py`: per finding `::error file=<File>,line=<StartLine>::gitleaks <RuleID> in <Commit[:12]>`; summary table (rule, file, line, commit, fingerprint) or "no findings"; writes `findings-count`; exit 1 when count > 0. Uses `_shared/md.py`.
  - `make-repo.sh <dir> [--allowlist]`: init temp git repo, commit file with fake `ghp_` + 36 random alnum chars generated at runtime (no secret-shaped literal in repo); `--allowlist` adds `.gitleaksignore` with the finding fingerprint (compute via a first gitleaks run or construct `<commit>:<file>:github-pat:<line>`).
  - Self-test cases: this repo range (pass, needs `fetch-depth: 0`); temp repo `full-history` (fail, assert `findings-count`>0 via outcome + output); temp repo allowlisted (pass); shallow `--depth 1` clone with push-style range (fail).
  - README: purpose, inputs, outputs, permissions, checkout requirement, allowlist files, example.

- [ ] 4 Block `dotnet-setup`
  - Deps: 1
  - Files: actions/dotnet-setup/action.yml, actions/dotnet-setup/README.md, actions/dotnet-setup/detect.sh, tests/fixtures/dotnet-setup/with-global-json/global.json, tests/fixtures/dotnet-setup/no-global-json/.gitkeep, .github/workflows/test-dotnet-setup.yml
  - Verify: shellcheck + actionlint clean on task files
  - Purpose: Req 6, design "`dotnet-setup`".
  - Inputs `working-directory` (`.`), `global-json-file` (default `<working-directory>/global.json`), `dotnet-version` (multi-line, default empty). Output `dotnet-version`. Permissions `contents: read`.
  - Steps: `detect.sh` → output `global-json` path if file exists; absent AND `dotnet-version` empty → `error` naming both inputs. `actions/setup-dotnet` (SHA-pinned, latest major) with `global-json-file` + `dotnet-version` (both allowed: global.json SDK + extra channels like `8.0.x`). `detect.sh --resolve` → `dotnet --version` in `working-directory` → output; write `DOTNET_NOLOGO=1`, `DOTNET_CLI_TELEMETRY_OPTOUT=1` to `GITHUB_ENV`.
  - Fixture `with-global-json/global.json`: pin .NET 10 SDK (`rollForward: latestFeature`).
  - Self-test: global.json + `dotnet-version: 8.0.x` → assert output starts `10.` and `dotnet --list-runtimes` has 8.0; no-global-json with `dotnet-version: 10.0.x` → pass; neither → fail.
  - README: purpose, inputs, outputs, permissions, example (global.json + `8.0.x` for net8 test runtimes).

- [ ] 5 Block `dotnet-restore`
  - Deps: 4
  - Files: actions/dotnet-restore/action.yml, actions/dotnet-restore/README.md, actions/dotnet-restore/restore.sh, tests/fixtures/dotnet-restore/**, .github/workflows/test-dotnet-restore.yml
  - Verify: shellcheck + actionlint clean on task files; if local dotnet 10 SDK present, `restore.sh` against `tests/fixtures/dotnet-restore/app` succeeds
  - Purpose: Req 7, design "`dotnet-restore`".
  - Inputs `working-directory`, `project` (auto via `_shared/resolve_project.py`), `locked-mode` (`false`). Outputs `project`, `cache-hit`. Permissions `contents: read`.
  - Steps: `actions/cache` (SHA-pinned) `path: ~/.nuget/packages`, key `nuget-${{ runner.os }}-${{ hashFiles(<wd>/**/Directory.Packages.props, <wd>/**/*.csproj, <wd>/**/packages.lock.json, <wd>/**/global.json, <wd>/**/nuget.config, <wd>/**/NuGet.Config) }}`, restore-keys `nuget-${{ runner.os }}-`. `restore.sh`: `dotnet restore "$PROJECT" [--locked-mode]`, nothing else (Req 7.4, 1.11).
  - Fixtures: `app/` (`.slnx`, `Directory.Packages.props` CPM, `Directory.Build.props` `TreatWarningsAsErrors`, one net10.0 classlib with one nuget.org package, `global.json`), `locked/` (same + `RestorePackagesWithLockFile` + committed `packages.lock.json`), `ambiguous/` (two `.slnx`).
  - Self-test (uses `./actions/dotnet-setup` first): app pass + `project` output; locked-mode pass; ambiguous fail.
  - README: purpose, inputs, outputs, permissions, caching note, example.

- [ ] 6 Block `dotnet-build`
  - Deps: 5
  - Files: actions/dotnet-build/action.yml, actions/dotnet-build/README.md, actions/dotnet-build/build.sh, actions/dotnet-build/check_args.py, tests/unit/dotnet-build/test_check_args.py, tests/fixtures/dotnet-build/**, .github/workflows/test-dotnet-build.yml
  - Verify: shellcheck + actionlint clean; `python3 -I -m unittest discover -s tests/unit/dotnet-build` passes
  - Purpose: Req 8, design "`dotnet-build`".
  - Inputs `working-directory`, `project`, `configuration` (`Release`), `build-args` (newline list). Output `project`. Permissions `contents: read`.
  - `check_args.py`: reject (case-insensitive) `-f`, `--framework`, `-warnaserror*`, `/warnaserror*`, `-warnnotaserror*`, `/warnnotaserror*`, `-nowarn*`, `/nowarn*`, `-warnasmessage*`, `/warnasmessage*`, `@<path>`, and `-p:`/`/p:`/`-property:`/`/property:`/`--property:` whose `;`/`,`-split assignments name `TargetFramework`, `TargetFrameworks`, `TreatWarningsAsErrors`, `MSBuildTreatWarningsAsErrors`, `CodeAnalysisTreatWarningsAsErrors`, `WarningsAsErrors`, `WarningsNotAsErrors`, `NoWarn`, `WarningLevel`, `NuGetAudit`, `NuGetAuditMode`, `NuGetAuditLevel`. Allow e.g. `-p:Version=1.2.3`, `-p:ContinuousIntegrationBuild=true`. Error names arg.
  - `build.sh`: `dotnet build "$PROJECT" --configuration "$CONFIGURATION" --no-restore "${BUILD_ARGS[@]}"`.
  - Fixtures: `strict/` (`.slnx`, CPM, `TreatWarningsAsErrors`, classlib `net8.0;net10.0`, `global.json`), `strict-warning/` (same + code emitting a compiler warning, e.g. unused variable CS0168).
  - Self-test (setup with `8.0.x` extra + restore first): strict pass; strict-warning fail; `build-args: -p:NoWarn=CS0168` on strict-warning fails before build; `build-args: -p:Version=1.2.3` passes.
  - README: purpose, inputs, outputs, permissions, forbidden-args list, example.

- [ ] 7 Block `nuget-vulnerability-gate`
  - Deps: 5
  - Files: actions/nuget-vulnerability-gate/action.yml, actions/nuget-vulnerability-gate/README.md, actions/nuget-vulnerability-gate/gate.sh, actions/nuget-vulnerability-gate/report.py, tests/unit/nuget-vulnerability-gate/**, tests/fixtures/nuget-vulnerability-gate/**, .github/workflows/test-nuget-vulnerability-gate.yml
  - Verify: shellcheck + actionlint clean; `python3 -I -m unittest discover -s tests/unit/nuget-vulnerability-gate` passes
  - Purpose: Req 4, design "`nuget-vulnerability-gate`".
  - Inputs `working-directory`, `project`. Outputs `critical-count`, `high-count`, `moderate-count`, `low-count`. Permissions `contents: read`.
  - `gate.sh`: resolve project; `dotnet list "$PROJECT" package --vulnerable --include-transitive --format json --output-version 1` → `$RUNNER_TEMP/vuln.json`, capture exit + stderr; `report.py`.
  - `report.py`: not-restored (`problems[]` error / "No assets file" / `project.assets.json`) → `error` "run dotnet-restore first"; other error, non-zero exit, bad JSON → fail. Walk `projects[].frameworks[].{topLevelPackages,transitivePackages}[].vulnerabilities[]`; key (`id`, `resolvedVersion`, `advisoryurl`); aggregate TFMs/projects; `direct` if in any topLevelPackages; severity case-insensitive. Outputs counts on unique keys. Summary sorted Critical→Low. `::error::` per Critical/High, `::warning::` per Moderate/Low. Exit 1 if critical+high > 0.
  - Unit tests on recorded JSON in `tests/unit/nuget-vulnerability-gate/fixtures/`: none, moderate-only, high, cross-TFM dedupe, problems/not-restored, malformed.
  - Live fixtures: `clean/`, `moderate/`, `high/` (`.slnx`, CPM, net10.0, `global.json`); `high/` sets `TreatWarningsAsErrors=false` so restore passes and gate fails. Choose package versions with stable GHSA advisories, record IDs in `tests/fixtures/nuget-vulnerability-gate/README.md`.
  - Self-test (setup + restore first): clean pass; moderate pass + `moderate-count`>0; high fail; unrestored fixture (no restore step) fail.
  - README: purpose, inputs, outputs, permissions, policy, recommended caller `Directory.Build.props` (`NuGetAuditMode=all`, `NuGetAuditLevel=high`) and statement that blocks never override NuGetAudit (Req 4.8), example.

- [ ] 8 Block `nuget-deprecation-report`
  - Deps: 5
  - Files: actions/nuget-deprecation-report/action.yml, actions/nuget-deprecation-report/README.md, actions/nuget-deprecation-report/report.sh, actions/nuget-deprecation-report/report.py, tests/unit/nuget-deprecation-report/**, tests/fixtures/nuget-deprecation-report/**, .github/workflows/test-nuget-deprecation-report.yml
  - Verify: shellcheck + actionlint clean; `python3 -I -m unittest discover -s tests/unit/nuget-deprecation-report` passes
  - Purpose: Req 5, design "`nuget-deprecation-report`".
  - Inputs `working-directory`, `project`. Output `deprecated-count`. Permissions `contents: read`.
  - `report.sh`: `dotnet list "$PROJECT" package --deprecated --include-transitive --format json --output-version 1`; `report.py`: same failure handling as vuln gate (not restored / tool error / bad JSON → fail); key (`id`, `resolvedVersion`); columns project(s), TFM(s), package, version, `deprecationReasons`, `alternativePackage.id` + `versionRange`, direct/transitive; `::warning::` per direct package; exit 0 otherwise.
  - Unit tests on recorded JSON: none, deprecated direct+transitive, alternative absent, malformed.
  - Live fixture `deprecated/` (`.slnx`, CPM, net10.0, `global.json`) referencing a package deprecated on nuget.org; record package + reason in fixture `README.md`.
  - Self-test (setup + restore first): deprecated pass + `deprecated-count`>0.
  - README: purpose, inputs, outputs, permissions, example.

- [ ] 9 Block `dotnet-test`
  - Deps: 6
  - Files: actions/dotnet-test/action.yml, actions/dotnet-test/README.md, actions/dotnet-test/test.sh, actions/dotnet-test/enforce.sh, actions/dotnet-test/select_runner.py, actions/dotnet-test/trx_summary.py, tests/unit/dotnet-test/**, tests/fixtures/dotnet-test/**, .github/workflows/test-dotnet-test.yml
  - Verify: shellcheck + actionlint clean; `python3 -I -m unittest discover -s tests/unit/dotnet-test` passes; if local dotnet 10 SDK present, build + run `mtp-xunit` fixture produces TRX via `--report-xunit-trx`
  - Purpose: Req 9 + design "`dotnet-test`" (design overrides Req 9.5/9.15: TRX-format selection, run-level zero-test rule).
  - Inputs per design table: `working-directory`, `project`, `configuration` (`Release`), `global-json-file`, `filter` (VSTest: single `--filter` expression; MTP: newline list, one arg per line), `test-args` (newline list), `trx-format` (`auto`|`mtp`|`xunit`), `min-tests` (`1`), `results-directory` (`${{ runner.temp }}/test-results`), `upload-results` (`true`), `artifact-name` (`test-results`). Outputs `test-runner`, `trx-format`, `passed-count`, `failed-count`, `skipped-count`, `total-count`, `results-directory`. Permissions `contents: read`.
  - Composite steps: (1) `test.sh` — runner detect via `select_runner.py` (`globaljson.py` `test.runner` == `Microsoft.Testing.Platform` ignore-case → `mtp`, else `vstest`); MTP TRX format: `trx-format` explicit, else auto over `*/obj/*/project.assets.json` under `working-directory` whose `libraries` include `Microsoft.Testing.Platform/`: all have `Microsoft.Testing.Extensions.TrxReport/` → `mtp`; else all have `xunit.v3.core/` → `xunit`; else `error` (reference TrxReport, use xunit.v3, or set `trx-format`); empty set → `error` "no MTP test projects found; restore first". `timeout 30 docker info` else `error` (Testcontainers needs Docker). Commands: VSTest `dotnet test "$PROJECT" --configuration "$CFG" --no-build --results-directory "$RD" --logger "trx;LogFilePrefix=tr" [--filter "$FILTER"] "${TEST_ARGS[@]}"`; MTP `dotnet test <--solution|--project> "$PROJECT" --configuration "$CFG" --no-build --results-directory "$RD" <--report-trx|--report-xunit-trx> --ignore-exit-code 8 "${FILTER_ARGS[@]}" "${TEST_ARGS[@]}"`. Records `exit-code` output; step does not fail on test failure. Sets no Testcontainers env. (2) `trx_summary.py` `if: always()` — parse all `*.trx` (TeamTest 2010 ns): passed, failed = failed+error+timeout+aborted, total, skipped = total−passed−failed, duration max finish − min start; summary totals + failed table (name, TRX stem, message ≤500, ≤200 rows); outputs. (3) `actions/upload-artifact` (SHA-pinned) `if: always() && inputs.upload-results == 'true'`, `path: <rd>/**/*.trx`, `if-no-files-found: warn`. (4) `enforce.sh` `if: always()` — fail if exit-code ≠ 0, failed > 0, no TRX, or total < `min-tests` (`0` disables); message names rule; non-zero exit with 0 failures → "test host exited <code>".
  - Unit tests: runner detection (JSONC, absent, VSTest), TRX auto-detect over synthetic assets files, TRX counters/duration/failed table on recorded VSTest, TrxReport, xunit-native TRX samples.
  - Fixtures (`.slnx`, CPM, net10.0, own `global.json`): `vstest/` (xunit.v3 + `xunit.runner.visualstudio` + `Microsoft.NET.Test.Sdk`); `mtp-xunit/` (xunit.v3 MTP, `OutputType` `Exe`, no TrxReport, `global.json` `test.runner: Microsoft.Testing.Platform`, plus explicit-only project with `[Fact(Explicit = true)]`, plus one Testcontainers test starting `alpine`); `mtp-trxreport/` (MSTest MTP + `Microsoft.Testing.Extensions.TrxReport`, `test.runner` MTP). Each has a test failing only when env `FIXTURE_FORCE_FAIL=1`.
  - Self-test (setup + restore + build per fixture, unique `artifact-name` per case): per fixture pass; `FIXTURE_FORCE_FAIL=1` fail; filter narrowing (VSTest expr; MTP lines `--filter-class` / `<pattern>`) pass with lower `total-count`; filter matching nothing fail; `mtp-xunit` asserts `trx-format == xunit` and passes despite explicit-only project; `mtp-trxreport` asserts `trx-format == mtp`.
  - README: purpose, inputs, outputs, permissions, runner detection, TRX format, zero-test rule (`min-tests`), Docker requirement, `artifact-name` uniqueness, examples VSTest + MTP.

- [ ] 10 External-caller self-test proving `_shared` relative path
  - Deps: 3, 7, 8, 9
  - Files: .github/workflows/test-external-caller.yml
  - Verify: actionlint clean; workflow uses only path-relocated `uses:` (no `./actions/…` from workspace root)
  - Purpose: approver note: prove `${{ github.action_path }}/../_shared` resolves when a block is called the way an external caller calls it.
  - `on: pull_request` + `push: branches: [main]`, `permissions: contents: read`. Job: `actions/checkout` (SHA-pinned) with `path: pernix-ci` (no checkout at workspace root, so no `actions/` or `actions/_shared` under `$GITHUB_WORKSPACE`); copy `pernix-ci/tests/fixtures/dotnet-restore/app` to `caller/`, `git init` + commit in `caller/` for secret-scan. Call blocks via `uses: ./pernix-ci/actions/<block>` with `working-directory: caller`: `secret-scan` (`scan-mode: full-history`, `working-directory: caller`), `dotnet-setup`, `dotnet-restore`, `nuget-vulnerability-gate`, `nuget-deprecation-report`, `dotnet-build`; then copy `pernix-ci/tests/fixtures/dotnet-test/mtp-xunit` to `caller-test/` and run setup/restore/build/`dotnet-test` there. Every step must succeed. Add a guard step asserting `[ ! -e "$GITHUB_WORKSPACE/actions" ]`.
