---
status: approved
createdAt: 2026-11-22T19:07:57Z
updatedAt: 2026-11-22T19:12:16Z
approvedAt: 2026-11-22T19:12:16Z
---

# Requirements: CI gates (P4)

**Spec ID:** 2026-11-22-ci-gates
**Author:** Architect (Orca worker, task_76a370b36068; revised task_b801c4f3adaa)

## Introduction

`Pernix-Labs/pernix-ci` is new public repo of reusable GitHub Actions building blocks for Pernix repos. P4 delivers single-purpose CI gate blocks (secret scan, NuGet vulnerability gate, NuGet deprecation report, .NET setup/restore/build/test) plus repo foundations (root `README.md`, `.github/workflows/lint.yml`). Callers: .NET repos (net8/net10, `.slnx`, `Directory.Packages.props` CPM, `TreatWarningsAsErrors`), runner `ubuntu-latest`. Test projects run on VSTest or Microsoft.Testing.Platform (MTP). First caller `pernix-outbox-relay` uses xunit.v3 on MTP (`global.json` `test.runner` = `Microsoft.Testing.Platform`, test projects `OutputType` `Exe`).

## Alignment with Product Vision

No `product.md` exists. Spec serves programme goal: Pernix repos share one audited CI/CD toolkit. P4 = gates, P5 (parallel) = artifacts, P6 (later) = reusable workflows composing P4+P5 blocks for mono-repos (CI per commit SHA, CD from tag).

## Goals

- **G1.** Each gate block below exists as composite action `actions/<block-name>/action.yml` + `actions/<block-name>/README.md`, does one thing, and passes its self-test workflow on `ubuntu-latest`.
- **G2.** CI of a caller fails on any secret finding and on any high/critical NuGet vulnerability (direct or transitive). Moderate/low vulnerabilities and deprecated packages are reported by the gate blocks and never fail them.
- **G3.** .NET restore/build/test blocks run caller code exactly as a local build does: caller MSBuild settings (warnings-as-errors, TargetFramework, NuGetAudit) pass through untouched. Tests run on VSTest or MTP with Docker available, results as TRX + job summary.
- **G4.** Repo foundations exist: root `README.md` (purpose, conventions, P4 block catalogue, placeholder sections `Artifacts` (P5) and `Workflows` (P6)). `.github/workflows/lint.yml` runs actionlint + shellcheck and is green on `main`.
- **G5.** Blocks expose inputs/outputs sufficient for P6 to compose them in a reusable workflow without forking block logic.

## Non-goals

- **NG1.** Artifact blocks (container image build/push to GHCR, NuGet pack/publish via Trusted Publishing, version-from-tag). Owned by P5.
- **NG2.** Reusable workflows, mono-repo orchestration, tag-based CD. Owned by P6.
- **NG3.** Release/tagging process of `pernix-ci` itself. Not requested. README documents how callers reference blocks only.
- **NG4.** Code-scanning (SARIF upload to GitHub Security tab). Needs `security-events: write`. Not requested. Job summary + exit code suffice.
- **NG5.** Configurable vulnerability fail threshold. Human ruling 2026-11-22 pins policy (high/critical fail, moderate report).
- **NG6.** Code coverage, mutation testing, formatting/analyzer gates. Not requested.
- **NG7.** `CODEOWNERS`, `.editorconfig`. P4 owns them but goal does not request them. Add only if human asks.
- **NG8.** P5 block docs/fixtures. P5 documents only in its own block READMEs and `tests/fixtures/<p5-block>/`.
- **NG9.** Private NuGet feed authentication (GitHub Packages, Azure Artifacts). Callers restore from nuget.org only (ruling Q8).
- **NG10.** Overriding caller NuGetAudit settings. Caller `Directory.Build.props` owns audit level (ruling Q5).

## Block catalogue (P4)

| Block | Purpose | Gate? |
|---|---|---|
| `secret-scan` | gitleaks scan of git history/diff | fails on any finding |
| `nuget-vulnerability-gate` | `dotnet list package --vulnerable --include-transitive` | fails on high/critical |
| `nuget-deprecation-report` | `dotnet list package --deprecated` | report only |
| `dotnet-setup` | install .NET SDK(s) from caller `global.json` | setup |
| `dotnet-restore` | restore solution/project | fails on restore error |
| `dotnet-build` | Release build | fails on build error |
| `dotnet-test` | run tests (VSTest or MTP), TRX + summary | fails on test failure |

Split rationale: `--vulnerable` and `--deprecated` are separate `dotnet list` modes with different policies (gate vs report). `dotnet-setup` is split from restore so build/test/audit blocks share one SDK install step (ruling Q1).

## Requirements

### Requirement 1 — Shared block conventions

**User Story:** As a Pernix repo maintainer, I want every block to follow one contract, so that I can compose and audit them uniformly.

#### Acceptance Criteria

1. Each block SHALL be a composite action at `actions/<block-name>/action.yml` with `actions/<block-name>/README.md` documenting purpose, inputs, outputs, required `permissions`, and a usage example.
2. All block inputs and outputs SHALL be kebab-case.
3. WHEN a block uses a third-party action THEN it SHALL reference it by full 40-char commit SHA with trailing `# vX.Y.Z` comment.
4. WHEN a block downloads a third-party binary THEN it SHALL pin exact version and verify SHA-256 checksum before execution, and SHALL fail on mismatch.
5. Each block README SHALL state least-privilege `permissions`. No P4 block SHALL require more than `contents: read`.
6. Blocks SHALL NOT echo secret values, tokens, or unredacted secret findings to logs, summaries, or outputs.
7. Blocks SHALL NOT perform `actions/checkout`. Caller owns checkout. README SHALL state required checkout options (for example `fetch-depth`).
8. Shell logic beyond a single command SHALL live in `actions/<block-name>/*.sh` scripts (bash, `set -euo pipefail`) so shellcheck covers it.
9. Each block SHALL accept `working-directory` input (default `.`) where it operates on .NET code, so P6 can target a mono-repo unit.
10. WHEN a block fails THEN it SHALL emit a GitHub `::error::` annotation stating cause and remediation.
11. .NET blocks SHALL NOT pass MSBuild properties or CLI switches that override caller settings for TargetFramework, warnings, or NuGetAudit (`NuGetAudit`, `NuGetAuditMode`, `NuGetAuditLevel`, `WarningsAsErrors`, `WarningsNotAsErrors`, `NoWarn`, `TreatWarningsAsErrors`).

### Requirement 2 — Self-tests and fixtures

**User Story:** As a pernix-ci maintainer, I want each block exercised in CI against fixtures, so that regressions surface before callers hit them.

#### Acceptance Criteria

1. Each block SHALL have `.github/workflows/test-<block-name>.yml` triggered on `pull_request` and `push` to `main`.
2. Fixtures SHALL live under `tests/fixtures/<block-name>/`. P4 SHALL create only P4 block fixture dirs.
3. Each gate block self-test SHALL cover pass case AND fail case. Fail case SHALL assert block step outcome is `failure` (via `continue-on-error` + outcome check) and the workflow itself SHALL succeed.
4. Fixtures SHALL NOT commit secret-shaped literals. Secret-scan positive fixtures SHALL be generated at runtime inside the self-test job.
5. Self-test workflows SHALL declare top-level `permissions` at least-privilege.
6. `dotnet-test` fixtures SHALL include a VSTest test project and an MTP xunit.v3 test project (`OutputType` `Exe`, fixture `global.json` with `test.runner` = `Microsoft.Testing.Platform`). Each SHALL be self-tested for pass, fail, and filter cases.

### Requirement 3 — `secret-scan`

**User Story:** As a security owner, I want every push and PR scanned for secrets with gitleaks, so that leaked credentials block merge.

#### Acceptance Criteria

1. WHEN invoked on `pull_request` THEN block SHALL scan commits in range PR base..head.
2. WHEN invoked on `push` THEN block SHALL scan commits in range `github.event.before`..`github.sha`. IF `before` is all-zero (new branch) THEN block SHALL scan full reachable history of `github.sha`.
3. WHEN input `scan-mode` is `full-history` THEN block SHALL scan entire repository history regardless of event. Default `scan-mode` SHALL be `auto` (criteria 1–2).
4. IF commits required for the selected range are absent (shallow clone) THEN block SHALL fail with error instructing `fetch-depth: 0`, never pass silently.
5. WHEN gitleaks reports ≥1 finding THEN block SHALL fail.
6. Block SHALL run gitleaks with redaction. Logs and job summary SHALL show rule ID, file, line, commit SHA per finding, never the secret value.
7. Block SHALL write job summary with finding count and redacted finding table (or "no findings").
8. Block SHALL expose output `findings-count`.
9. IF caller repo contains `.gitleaks.toml` or `.gitleaksignore` at its root THEN block SHALL apply them. Input `config-path` SHALL override config location (ruling Q2).
10. Block SHALL run the gitleaks CLI binary (pinned version + SHA-256, per Req 1.4), not `gitleaks/gitleaks-action`, and SHALL NOT require a license key or any secret input (ruling Q3).

### Requirement 4 — `nuget-vulnerability-gate`

**User Story:** As a security owner, I want high/critical vulnerable NuGet packages to fail CI and lower severities reported, so that policy from 2026-11-22 ruling is enforced.

#### Acceptance Criteria

1. Block SHALL run `dotnet list <target> package --vulnerable --include-transitive --format json` against input `project` (solution `.slnx`/`.sln` or project file; default: auto-detect single solution in `working-directory`).
2. IF target has not been restored THEN block SHALL fail with error instructing to run `dotnet-restore` first.
3. WHEN any direct or transitive package has advisory severity `High` or `Critical` THEN block SHALL fail.
4. WHEN only `Moderate`/`Low` advisories exist THEN block SHALL succeed and report them.
5. Block SHALL write job summary table: project, TFM, package, resolved version, severity, advisory URL, direct/transitive. Duplicate package+version+advisory rows across TFMs SHALL collapse to one row listing TFMs.
6. Block SHALL expose outputs `critical-count`, `high-count`, `moderate-count`, `low-count`.
7. IF `dotnet list` exits non-zero or returns unparseable output THEN block SHALL fail (fail closed), not report zero.
8. Block README SHALL document recommended caller `Directory.Build.props` settings `NuGetAuditMode=all` + `NuGetAuditLevel=high`, so restore under `TreatWarningsAsErrors` fails only on high/critical, matching the ruling. README SHALL state that blocks never override these settings (ruling Q5).

### Requirement 5 — `nuget-deprecation-report`

**User Story:** As a maintainer, I want deprecated NuGet packages listed, so that I can plan replacements without blocking CI.

#### Acceptance Criteria

1. Block SHALL run `dotnet list <target> package --deprecated --include-transitive --format json`.
2. WHEN deprecated packages exist THEN block SHALL succeed and write job summary table: project, TFM, package, version, reasons, alternative package.
3. Block SHALL emit `::warning::` annotation per deprecated direct package.
4. Block SHALL expose output `deprecated-count`.
5. IF `dotnet list` fails THEN block SHALL fail (tool error ≠ report).

### Requirement 6 — `dotnet-setup`

**User Story:** As a block composer, I want one step that installs the caller's pinned SDK, so that restore/build/test/audit use the same SDK.

#### Acceptance Criteria

1. Block SHALL install SDK from caller `global.json` (input `global-json-file`, default `<working-directory>/global.json`) using `actions/setup-dotnet` pinned by SHA.
2. IF no `global.json` exists THEN block SHALL install SDK versions from input `dotnet-version` (multi-line), else fail with error naming both options.
3. Block SHALL support installing multiple SDK channels (net8 + net10) in one invocation.
4. Block SHALL expose output `dotnet-version` (resolved SDK of `dotnet --version` in `working-directory`).

### Requirement 7 — `dotnet-restore`

**User Story:** As a block composer, I want deterministic restore with package cache, so that build/test/audit start fast and identical.

#### Acceptance Criteria

1. Block SHALL run `dotnet restore <project>` in `working-directory`.
2. WHEN input `locked-mode` is `true` THEN block SHALL pass `--locked-mode`. Default `false` (ruling Q4).
3. Block SHALL cache NuGet global packages folder keyed on OS + hash of `**/Directory.Packages.props`, `**/*.csproj`, `**/packages.lock.json`, `global.json`, `nuget.config` under `working-directory`.
4. Block SHALL pass caller settings through untouched, including NuGetAudit (Req 1.11). WHEN caller audit settings raise NU1901–NU1904 as errors THEN restore SHALL fail exactly as a local restore does (ruling Q5).
5. IF restore fails THEN block SHALL fail.

### Requirement 8 — `dotnet-build`

**User Story:** As a maintainer, I want a Release build that honours my repo's strictness, so that CI matches local `TreatWarningsAsErrors` behaviour.

#### Acceptance Criteria

1. Block SHALL run `dotnet build <project> --configuration <configuration> --no-restore`. Input `configuration` default `Release`.
2. Block SHALL NOT pass `-p:TargetFramework`, `-f`, `-warnaserror-`, `-p:TreatWarningsAsErrors=false`, `-p:NoWarn`, `-nowarn`, or any property listed in Req 1.11.
3. WHEN caller `Directory.Build.props` sets `TreatWarningsAsErrors` and a warning occurs THEN build SHALL fail.
4. Block SHALL accept input `build-args` (extra args, default empty) so P6 can pass for example `-p:Version=<from tag>` or `-p:ContinuousIntegrationBuild=true` (ruling Q6).
5. IF `build-args` contains an argument matching Req 8.2 or Req 1.11 THEN block SHALL fail before building with error naming the rejected argument (ruling Q6).
6. Block SHALL build all TargetFrameworks declared by caller projects.

### Requirement 9 — `dotnet-test`

**User Story:** As a maintainer, I want tests (incl. Testcontainers integration tests) run on VSTest or MTP with results visible in the job summary, so that failures are diagnosable without log spelunking.

#### Acceptance Criteria

1. Block SHALL detect test runner from caller `global.json` (input `global-json-file`, default `<working-directory>/global.json`): `test.runner` = `Microsoft.Testing.Platform` → MTP mode. Absent `global.json`, absent `test.runner`, or `VSTest` → VSTest mode.
2. Block SHALL expose output `test-runner` (`vstest` | `mtp`).
3. Block SHALL run `dotnet test` on `<project>` with `--configuration <configuration> --no-build`, producing TRX files into input `results-directory` (default `${{ runner.temp }}/test-results`).
4. WHEN in VSTest mode THEN block SHALL produce TRX via `--logger trx` and `--results-directory`.
5. WHEN in MTP mode THEN block SHALL produce TRX via the MTP TRX report option (`--report-trx`) and `--results-directory`. IF the test host rejects the option THEN block SHALL fail with error instructing to reference `Microsoft.Testing.Extensions.TrxReport` or the framework's equivalent.
6. WHEN input `filter` is non-empty AND mode is VSTest THEN block SHALL pass `--filter <filter>`.
7. WHEN input `filter` is non-empty AND mode is MTP THEN block SHALL pass `filter` verbatim as MTP filter arguments (for example xunit.v3 `--filter-class Pernix.*`).
8. Block SHALL accept input `test-args` (extra raw args, default empty) appended in runner-appropriate position.
9. Block SHALL verify Docker daemon reachable (`docker info`) before tests in both modes. IF unreachable THEN block SHALL fail with error stating Testcontainers requires Docker on runner.
10. Block SHALL NOT set environment that disables Testcontainers (for example `TESTCONTAINERS_RYUK_DISABLED`) unless caller passes it.
11. WHEN tests finish (pass or fail) THEN block SHALL write job summary from TRX in both modes: totals (passed/failed/skipped, duration) and table of failed tests with message (truncated).
12. WHEN any test fails THEN block SHALL fail after summary is written.
13. WHEN input `upload-results` is `true` (default) THEN block SHALL upload TRX files as artifact named from input `artifact-name` (default `test-results`) via `actions/upload-artifact` pinned by SHA, regardless of test outcome.
14. Block SHALL expose outputs `passed-count`, `failed-count`, `skipped-count`, `results-directory`.
15. IF zero TRX files are produced, or zero tests ran (including MTP exit code 8), THEN block SHALL fail (no silent pass on discovery or filter failure).

### Requirement 10 — Root `README.md`

**User Story:** As a Pernix engineer, I want one landing page, so that I know what blocks exist and how to use them.

#### Acceptance Criteria

1. `README.md` SHALL state repo purpose and that blocks are composite actions under `actions/<block-name>/`.
2. `README.md` SHALL list conventions: single-purpose blocks, kebab-case I/O, SHA-pinned third-party actions, least-privilege permissions, no secret echo, no override of caller MSBuild settings, self-test per block, fixtures under `tests/fixtures/<block-name>/`, actionlint + shellcheck.
3. `README.md` SHALL show how callers reference a block: `uses: Pernix-Labs/pernix-ci/actions/<block-name>@<ref>`, recommending full commit SHA or `vX.Y.Z` tag.
4. `README.md` SHALL contain `## Gates` catalogue table (block, purpose, link to block README) for all P4 blocks.
5. `README.md` SHALL contain `## Artifacts` section with placeholder text marking P5 ownership, and `## Workflows` section with placeholder text marking P6 ownership.
6. `README.md` SHALL state release-wide policy from 2026-11-22 ruling relevant to gates: CI fails on secrets and high/critical vulns, moderate/low report only, app code keeps `TreatWarningsAsErrors`, callers own NuGetAudit level.

### Requirement 11 — Lint workflow

**User Story:** As a pernix-ci maintainer, I want workflows and scripts linted on every change, so that broken YAML/shell never reaches callers.

#### Acceptance Criteria

1. `.github/workflows/lint.yml` SHALL trigger on `pull_request` and `push` to `main`.
2. Lint job SHALL run actionlint over `.github/workflows/*.yml` (actionlint pinned by version + checksum or SHA-pinned action).
3. Lint job SHALL run shellcheck over all `*.sh` files in repo (incl. P5 scripts, since scripts are repo-wide).
4. WHEN actionlint or shellcheck reports any finding THEN lint job SHALL fail.
5. Lint workflow SHALL declare `permissions: contents: read`.

## Non-Functional Requirements

### Code Architecture and Modularity
- One block = one composite action = one concern. No block calls another block. Composition is P6's job.
- Blocks communicate only via inputs, outputs, files on runner (`results-directory`), and job summary.

### Performance
- `secret-scan` in `auto` mode on PR SHALL scan only PR range, not full history.
- `dotnet-restore` cache hit SHALL skip package download.

### Security
- No secret inputs on any P4 block. No `pull_request_target` in self-tests.
- All third-party code pinned (SHA for actions, version + checksum for binaries).
- Redacted output for every secret finding.

### Reliability
- Gates fail closed: tool error, parse error, missing history, missing TRX, zero tests run → failure, never pass.
- Self-tests cover pass and fail paths for every gate, and both test runners.
- CI behaves like a local build: no block alters caller MSBuild settings.

### Usability
- Every failure emits `::error::` with remediation.
- Every gate/report writes a job summary readable without opening logs.

## Resolved questions

1. [x] **Q1.** Add `dotnet-setup` block? **Decided 2026-11-22: accepted as proposed.** Block added (Req 6).
2. [x] **Q2.** Honour caller `.gitleaks.toml` / `.gitleaksignore`? **Decided: accepted as proposed.** Allowlists applied, `config-path` override (Req 3.9).
3. [x] **Q3.** gitleaks CLI vs `gitleaks/gitleaks-action`? **Decided: accepted as proposed.** Pinned CLI binary + SHA-256, no license (Req 3.10).
4. [x] **Q4.** `locked-mode` default? **Decided: accepted as proposed.** Default `false` (Req 7.2).
5. [x] **Q5.** NuGetAudit vs moderate=report-only? **Decided: proposal (b) rejected.** Blocks must NOT override caller NuGetAudit (no `-p:NuGetAudit=false`). CI behaves like a local build. Restore/build pass caller settings through untouched. Callers own audit level via `Directory.Build.props`. Vuln-gate README documents recommended `NuGetAuditMode=all` + `NuGetAuditLevel=high` so restore fails only on high/critical. `nuget-vulnerability-gate` stays the explicit, reportable gate (moderate/low reported) (Req 1.11, 4.8, 7.4, NG10).
6. [x] **Q6.** `build-args` passthrough on `dotnet-build`? **Decided: accepted as proposed.** Allowed, relaxation args rejected (Req 8.4, 8.5).
7. [x] **Q7.** Microsoft.Testing.Platform support? **Decided: MUST support MTP.** First caller `pernix-outbox-relay` uses xunit.v3 with `global.json` `test.runner` = `Microsoft.Testing.Platform` (test projects `OutputType` `Exe`, MTP filters like `--filter-class`). `dotnet-test` detects runner from `global.json` and supports VSTest and MTP: TRX, filter, Docker check, summary, artifacts. Fixture includes an MTP xunit.v3 test project (Req 2.6, 9).
8. [x] **Q8.** Private NuGet feeds? **Decided: accepted as proposed.** nuget.org only, feed auth out of scope (NG9).
