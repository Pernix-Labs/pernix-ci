---
status: approved
createdAt: 2026-11-22T20:37:49Z
updatedAt: 2026-11-22T21:28:53Z
approvedAt: 2026-11-22T20:41:10Z
completedAt: 2026-11-22T21:28:53Z
---

# Tasks: P6 ci-release-flow — tag-based CI/CD for .NET mono-repos

**Spec ID:** 2026-11-22-ci-release-flow
**Requirements:** [requirements.md](./requirements.md)
**Design:** [design.md](./design.md)

Shared rules for every task (read before starting):
- Read `docs/specs/2026-11-22-ci-release-flow/requirements.md` (your Req + NFRs) and `design.md` (Architecture, your component, Data Models, Decisions, Error Handling, Testing Strategy row) first. Read `docs/adr/0012-reusable-workflow-self-pinning.md` (task 1 output) before any reusable-workflow or template work: it fixes the self-pinning mode (`job.workflow_sha` or caller-passed `pernix-ci-ref`).
- Write ONLY files in your task's `Files`. Spec docs under `docs/specs/` are frozen. Never touch `actions/_shared/` or `.github/scripts/check-shared-usage.sh`.
- Block layout (P4 style, design D3): `actions/<block>/action.yml` (thin, inputs → `env:`), `actions/<block>/<block>.sh` (bash entry, `set -euo pipefail`, never `set -x`), python3 stdlib helper `actions/<block>/<name>.py` for parsing/logic, `actions/<block>/README.md` (purpose, inputs, outputs, permissions, example, preconditions). No `${{ }}` in `run:` bodies. Kebab-case I/O. `::error::` with remediation on every failure. New blocks never use `actions/_shared`.
- Third-party actions pinned by full 40-char SHA + `# vX.Y.Z` comment. Reuse pins already in repo (`grep -rh "uses: actions/" .github actions`) for `actions/checkout`, `actions/upload-artifact`, `actions/download-artifact`. New pins resolved via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (deref annotated tags). Binaries: version + SHA-256 pinned, verified before exec.
- Self-tests: `.github/workflows/test-<name>.yml`, `on: pull_request` + `push: branches: [main]`, least-privilege `permissions` per job, no `pull_request_target`. Registry jobs: per-run packages `pernix-ci-selftest-release-flow-${{ github.run_id }}-${{ github.run_attempt }}-*`, fork-PR skip with `::notice::`, `if: always()` cleanup deleting whole packages (P5 owner rule), `leftover-check` job (P5 AB2).
- Unit tests: `tests/unit/<block>/test_*.py`, run `python3 -I -m unittest discover -s tests/unit/<block>`; self-test workflow runs them.
- Local verify before done: `shellcheck` on your `*.sh`, `actionlint` on your workflow files, unit tests pass. Real CI run is task 14.
- Commit only your files on your worktree branch, message names the task. No co-author lines. Never push tags. Outward-facing actions (repo creation, PR open, pushing outside your branch) need coordinator approval via `orca orchestration ask`.

- [ ] 1 RK1 verify `job.workflow_sha` cross-repo + ADR 0012
  - Files: docs/adr/0012-reusable-workflow-self-pinning.md
  - Agent: any
  - Verify: ADR 0012 states observed `job.workflow_sha` value (or empty) from a real cross-repo run with run URL, chosen mode, and consequences for tasks 8-11
  - Purpose: resolve design RK1/D1 before any reusable workflow is written.
  - Probe: temp branch `probe/rk1-workflow-sha` in `Pernix-Labs/pernix-ci` with reusable `.github/workflows/probe-workflow-sha.yml` (`on: workflow_call`, one job echoing `job.workflow_sha`, `job.workflow_ref`, `job.workflow_repository`, `github.workflow_sha`, `github.sha` into job summary, and a step `actions/checkout` with `repository: Pernix-Labs/pernix-ci`, `ref: ${{ job.workflow_sha }}`, `path: pernix-ci` then `ls pernix-ci/actions`). Caller workflow in a different repo calling `Pernix-Labs/pernix-ci/.github/workflows/probe-workflow-sha.yml@probe/rk1-workflow-sha`. Caller repo is supplied by the coordinator in the dispatch. IF none given THEN ask coordinator (caller repo or approval to create a scratch repo) before pushing anything. Run, capture summary.
  - Pass = `job.workflow_sha` equals probe branch HEAD sha AND checkout at it succeeds. Mode `job-workflow-sha`.
  - Else (empty/absent/wrong) = mode `pernix-ci-ref` without re-asking (foreman ruling): reusable workflows take required input `pernix-ci-ref`, check out pernix-ci at it; templates set it equal to their `uses:` ref; self-tests pass `${{ github.event.pull_request.head.sha || github.sha }}`.
  - Cleanup: delete probe branch and caller probe file/branch. Probe files never land in this PR.
  - ADR 0012 sections Status (`Accepted`) / Context (F3, R1, D1) / Decision (mode) / Evidence (run URL, observed values) / Consequences (exact checkout step snippet for every reusable-workflow job, guard step text, rejected options per D1).

- [ ] 2 Fixture mono-repo `tests/fixtures/release-flow/repo`
  - Files: tests/fixtures/release-flow/**
  - Agent: any
  - Verify: in a temp copy: `dotnet build Fixture.slnx -c Release` clean with `TreatWarningsAsErrors`; `dotnet test` passes both MTP projects; `docker build -f src/Svc/Dockerfile .` succeeds
  - Purpose: fixture for Req 8.1 (design Testing Strategy "Fixture").
  - Contents per design: `global.json` (SDK 10, `test.runner` = `Microsoft.Testing.Platform`), `Directory.Build.props` (`TreatWarningsAsErrors`, `NuGetAuditMode=all`, `NuGetAuditLevel=high`), `Directory.Packages.props` (CPM), `Fixture.slnx`, `src/Shared/Shared.csproj`, `src/Svc/Svc.csproj` (refs Shared, console app) + `src/Svc/Dockerfile` (multi-stage `dotnet publish`, final `mcr.microsoft.com/dotnet/runtime-deps` pinned by digest, build args `BUILD_VERSION`, `BUILD_COMMIT`), `src/Lib/Lib.csproj` (refs Shared, packable), `tests/Svc.Tests`, `tests/Lib.Tests` (xunit.v3, MTP, `OutputType` `Exe`, TRX report ext, ≥1 test each), `deploy/svc.conf` copied by Dockerfile, `.dockerignore`, `.github/release-units.yml` (unit `svc`: image project `src/Svc/Svc.csproj`, dockerfile `src/Svc/Dockerfile`, `extra-inputs: [deploy/svc.conf]`; unit `lib`: packages `[src/Lib/Lib.csproj]`).
  - Image must pass Trivy HIGH/CRITICAL (no vulnerable packages).
  - Fixture holds no secret-shaped literals.

- [ ] 3 P5 amendment `image-build-push` input `push`
  - Files: actions/image-build-push/action.yml, actions/image-build-push/image-build-push.sh, actions/image-build-push/README.md, .github/workflows/test-image-build-push.yml
  - Agent: any
  - Verify: shellcheck + actionlint clean; existing self-test steps unchanged and still asserted; new `push: false` case asserted
  - Isolation: worktree
  - Purpose: design D9 / "P5 amendment" / ADR 0013, ruling Q1.
  - New input `push` (default `true`). `true` = byte-identical behaviour. `false` → skip `docker login`, `docker/build-push-action` `push: false` + `load: true`; outputs `image`, `tag` as today, `digest` = local image id, `ref` = `<image>:sha-<sha>`.
  - Self-test: add job/steps building with `push: false`, assert `docker image inspect <ref>` works locally and the tag is absent in GHCR (`image-exists`-style `HEAD` 404 or Packages API 404). Fork-safe: `push: false` case runs on fork PRs.
  - README: document `push`.

- [ ] 4 P5 amendment `image-scan` input `image-source`
  - Deps: 3
  - Files: actions/image-scan/action.yml, actions/image-scan/image-scan.sh, actions/image-scan/README.md, .github/workflows/test-image-scan.yml
  - Agent: any
  - Verify: shellcheck + actionlint clean; existing self-test cases unchanged; new `image-source: docker` clean + vulnerable cases asserted
  - Isolation: worktree
  - Purpose: design D9 / ADR 0013, ruling Q1.
  - New input `image-source` (`remote` default | `docker`; else fail before scan). `remote` = byte-identical. `docker` → `--image-src docker`, no registry creds passed. `IMAGE_REF_RE` unchanged.
  - Self-test: build `tests/fixtures/image-scan/clean` and `vulnerable` locally with plain `docker build -t ghcr.io/pernix-labs/pernix-ci-selftest-image-scan-local:<run>` (no push), scan with `image-source: docker`: clean → `result=pass`; vulnerable → step failure + counts > 0. Runs on fork PRs.

- [ ] 5 Block `release-units`
  - Deps: 2
  - Files: actions/release-units/action.yml, actions/release-units/release-units.sh, actions/release-units/release_units.py, actions/release-units/README.md, tests/unit/release-units/**, tests/fixtures/release-units/**, .github/workflows/test-release-units.yml
  - Agent: any
  - Verify: unit tests pass; shellcheck + actionlint clean; `test-release-units.yml` logic run locally against a temp git copy of the fixture asserts every Req 8.2 case
  - Isolation: worktree
  - Purpose: Req 1, Req 2, Req 3.8; design "Block `release-units`", Data Models, D4, D6, D13.
  - Inputs `units-file`, `working-directory`, `solution`, `unit`, `owner`, `image-name-prefix`. Outputs `units` (JSON per design Data Models incl. `ci-version`, `image-package`, `*-list` fields), `unit-names`, `count`.
  - `yq` (mikefarah v4, latest stable) downloaded by version + SHA-256 into `$RUNNER_TEMP`, verified; YAML → JSON. Strict schema per design D4.
  - Graph via `dotnet msbuild <proj> -getProperty:IsTestProject -getItem:ProjectReference` (JSON), BFS, memoised. Test projects from `dotnet sln <solution> list`. Pathspecs per design step 5 (globs, excludes, ancestor build files listed even if absent, `:(icase)` NuGet.Config, Dockerfile, `.dockerignore`, `extra-inputs` validated). `L` via `git log -1 --format=%H HEAD -- <pathspecs>`. Shallow → fail. Empty `L` → fail. `ci-version` `0.0.0-ci.g<sha7>`.
  - Unit tests: schema errors, pathspec builder, BFS on recorded msbuild JSON samples under `tests/fixtures/release-units/`, test-project detection, `ci-version` SemVer validity incl. all-digit sha.
  - Self-test (Req 8.2): `actions/setup-dotnet` via `./actions/dotnet-setup`, copy `tests/fixtures/release-flow/repo` to `$RUNNER_TEMP`, `git init`, initial commit, then per case: commit change → run `./actions/release-units` → assert `last-touch-sha` per unit (Shared → both; Svc only → svc; `Directory.Packages.props` → both; unrelated `README.md` → none; Dockerfile → svc; `tests/Lib.Tests` file → lib; `deploy/svc.conf` → svc). Shallow clone (`git clone --depth 1 file://…`) → step failure. `unit: lib` filter → one element.

- [ ] 6 Block `release-tag`
  - Files: actions/release-tag/action.yml, actions/release-tag/release-tag.sh, actions/release-tag/release_tag.py, actions/release-tag/README.md, tests/unit/release-tag/**, .github/workflows/test-release-tag.yml
  - Agent: any
  - Verify: unit tests pass; shellcheck + actionlint clean; self-test logic run locally against scripted temp repo
  - Isolation: worktree
  - Purpose: Req 3.1-3.7; design "Block `release-tag`", D8.
  - Inputs `tag`, `unit-names`, `default-branch`, `commit` (self-test only), `working-directory`. Outputs `unit`, `version`, `prerelease`, `commit`. Regex exactly per design. `+` → "build metadata not allowed". Reachability `git merge-base --is-ancestor <commit> origin/<default-branch>`.
  - Unit tests: Req 8.3 table (valid `svc/v1.2.3`, `lib/v1.0.0-rc.1`, `v1.2.3` single-unit; invalid unknown unit, bare `v` multi-unit, `+build`, leading zero, missing `v`).
  - Self-test: temp bare "origin" + clone, `main` with commits, annotated + lightweight tags, orphan branch commit tagged → unreachable failure; `commit` override with existing tag on other commit → failure.

- [ ] 7 Block `dotnet-unit-solution`
  - Deps: 2
  - Files: actions/dotnet-unit-solution/action.yml, actions/dotnet-unit-solution/dotnet-unit-solution.sh, actions/dotnet-unit-solution/README.md, .github/workflows/test-dotnet-unit-solution.yml
  - Agent: any
  - Verify: shellcheck + actionlint clean; locally on fixture copy: generated `.pernix-ci-units/svc.slnx` builds only listed projects
  - Isolation: worktree
  - Purpose: design "Block `dotnet-unit-solution`", D5.
  - Inputs `projects`, `name`, `working-directory`. Output `solution` (`.pernix-ci-units/<name>.slnx`). Existing output → fail. `dotnet new sln --format slnx` + `dotnet sln add`.
  - Self-test on fixture copy: svc solution contains Shared, Svc, Svc.Tests only; `dotnet build` on it succeeds; second run fails (exists).

- [ ] 8 Reusable workflow `ci.yml`
  - Deps: 1, 3, 4, 5, 6, 7
  - Files: .github/workflows/ci.yml, docs/workflows/ci.md
  - Agent: any
  - Verify: actionlint clean; job graph, push-mode expression, leg conditions match design "Unit leg" + "Push mode"; self-pinning matches ADR 0012
  - Isolation: worktree
  - Purpose: Req 4; design "Reusable workflow `.github/workflows/ci.yml`", D2, D10, D11, D14.
  - `on: workflow_call` inputs/outputs per design (+ `pernix-ci-ref` if ADR 0012 mode = `pernix-ci-ref`). Jobs `secret-scan`, `resolve`, `unit` (matrix, `fail-fast: false`), `summary`. Workspace `repo/` + `pernix-ci/`. Blocks via `./pernix-ci/actions/<block>`.
  - Leg: image + push → `image-exists`; reuse → skip gates, `image-scan` remote digest; build path → setup, `dotnet-unit-solution`, restore, vuln gate, deprecation report, build, test (skip + notice if no test projects, D10), `image-build-push` (`push` per mode, `sha` = `L`, `version` = `ci-version`, `image-name-prefix` applied via units JSON), `image-scan` (`remote` digest or `docker` local ref). Packages → setup + solution + restore (if not already) + `nuget-pack` dry check into `$RUNNER_TEMP`.
  - Leg result artifact `unit-result-<run_attempt>-<name>` + `summary` merge (D11). `summary` fails if any leg failed.
  - `docs/workflows/ci.md`: purpose, inputs, outputs, permissions, caller example (Req 9.3).

- [ ] 9 Reusable workflows `cd.yml` + `image-retention.yml`
  - Deps: 1, 5, 6
  - Files: .github/workflows/cd.yml, .github/workflows/image-retention.yml, docs/workflows/cd.md, docs/workflows/image-retention.md
  - Agent: any
  - Verify: actionlint clean; `outputs` job `if:` uses allow-list (`success` or `skipped`) for promote; no `id-token`, no NuGet in `cd.yml`
  - Isolation: worktree
  - Purpose: Req 5, Req 7; design "Reusable workflow `cd.yml`", "`image-retention.yml`", D7, D8, D12, D13.
  - `cd.yml`: jobs `resolve` (checkout ref `commit` else `tag`, `release-units`, `release-tag` with `commit` + `default-branch` passthrough, `jq` select), `promote` (`image-exists` → missing = fail "run ci job first"; `image-scan` digest; `image-promote` `sha-<L>` → `<version>`), `outputs` (allow-list condition). Outputs per design.
  - `image-retention.yml`: `release-units` → `jq` package list → skip with notice if empty → `image-retention` with P5 defaults overridable.
  - Self-pinning per ADR 0012.
  - Docs per Req 9.3.

- [ ] 10 Caller templates + lint coverage
  - Deps: 8, 9
  - Files: templates/ci.yml, templates/cd.yml, templates/retention.yml, templates/release-units.yml, .github/workflows/lint.yml
  - Agent: any
  - Verify: `actionlint templates/*.yml .github/workflows/*.yml` clean; `cd.yml` header states Trusted Publishing policy fields + keep filename `cd.yml`
  - Isolation: worktree
  - Purpose: Req 6; design "Templates `templates/`", D7, D14.
  - Exactly per design: `ci.yml` (push main + PR, concurrency), `cd.yml` (`ci` → `release` → `publish` in `environment: release`, `id-token: write` only there, `nuget-pack` + `nuget-push` via `Pernix-Labs/pernix-ci/actions/<block>@v1.0.0`, `user: ${{ vars.NUGET_USER }}`), `retention.yml` (daily cron + dispatch `dry-run`), `release-units.yml` (commented relay/client example). Pin pernix-ci as `@v1.0.0` (+ `pernix-ci-ref: v1.0.0` if ADR 0012 mode requires).
  - `lint.yml`: actionlint also runs on `templates/*.yml`. Nothing else changed.

- [ ] 11 Release-flow self-tests (CI + CD workflows)
  - Deps: 2, 8, 9, 10
  - Files: .github/workflows/test-release-ci.yml, .github/workflows/test-release-cd.yml
  - Agent: any
  - Verify: actionlint clean; assertions cover Req 8.4, 8.5, 8.6, 8.9 per design Testing table
  - Isolation: worktree
  - Purpose: Req 8.4-8.6, 8.9; design Testing table rows, D8.
  - `test-release-ci.yml`: `uses: ./.github/workflows/ci.yml`, `working-directory: tests/fixtures/release-flow/repo`, `image-name-prefix: pernix-ci-selftest-release-flow-${{ github.run_id }}-${{ github.run_attempt }}-`. Jobs `ci-build` (`push-image: 'true'`, assert svc `reused=false`) → `ci-reuse` (assert `reused=true`, same `image-ref`) ; `ci-local` (`push-image: 'false'`, assert `image-ref` empty); `cleanup` `if: always()`; `leftover-check`. Fork PR: registry jobs skip with notice, `ci-local` runs.
  - `test-release-cd.yml`: `ci` (tag `svc/v0.0.1-selftest.${{ github.run_id }}`, `commit: ${{ github.event.pull_request.head.sha || github.sha }}`, `default-branch: ${{ github.head_ref || github.event.repository.default_branch }}`) → `release` (`cd.yml`, same inputs) → assert promoted tag digest = `sha-<L>` digest via registry `HEAD`; `lib` tag run → `publish` job mirroring `templates/cd.yml` publish steps with local paths and `nuget-push dry-run: true`, no `id-token: write`, assert package version `0.0.1-selftest.<run_id>` in local feed; cleanup + leftover-check.

- [ ] 12 External-caller `@sha` + `@v1` self-tests
  - Files: .github/workflows/test-external-caller.yml, .github/workflows/test-external-caller-v1.yml
  - Agent: any
  - Verify: actionlint clean; existing job unchanged; new job pins `@377fbd2bab8e004aada51ae26be9b2432371c26b`
  - Isolation: worktree
  - Purpose: Req 8.7; design Testing table.
  - Add job `external-caller-pinned` to `test-external-caller.yml`: same steps as existing job but blocks via `Pernix-Labs/pernix-ci/actions/<block>@377fbd2bab8e004aada51ae26be9b2432371c26b` (only P4 blocks exist there); fixtures still from local checkout under `pernix-ci/`.
  - New `test-external-caller-v1.yml`: `on: workflow_dispatch` only, same steps `@v1`. Header comment: run at closeout after `v1.0.0` + `v1` tags exist.

- [ ] 13 ADRs 0001-0011, 0013 + root README
  - Deps: 1, 10, 11
  - Files: docs/adr/0001-sha-commit-image-tag.md, docs/adr/0002-promote-via-raw-oci-manifest.md, docs/adr/0003-trivy-cli-binary.md, docs/adr/0004-no-shared-lib-for-artifact-blocks.md, docs/adr/0005-nuget-push-in-caller-job.md, docs/adr/0006-image-retention-classes.md, docs/adr/0007-release-units-matrix-file.md, docs/adr/0008-msbuild-graph-last-touch-reuse.md, docs/adr/0009-pr-ci-local-build-no-push.md, docs/adr/0010-tag-grammar-and-versions.md, docs/adr/0011-cd-split-caller-publish.md, docs/adr/0013-p5-additive-local-image-inputs.md, README.md
  - Agent: any
  - Verify: every ADR row of design "ADR plan" exists with Status/Context/Decision/Consequences; README sections match design "README"; links resolve
  - Purpose: Req 9.1, 9.2, 10.3; design "ADR plan", "README", F1.
  - ADR format = ADR 0012 (task 1). Sources: P5 `docs/specs/2026-11-22-ci-artifacts/design.md` (D2, D3, D6, R1.10, R6.2, R8.1, as-built notes), this spec's D-codes and rulings.
  - README: fill `## Artifacts` (P5 table like `## Gates`, plus `push`/`image-source` notes), replace `## Workflows` placeholder (flow, reusable workflow table linking `docs/workflows/*.md`, new blocks table, caller setup checklist, template links, F1 image version-label note, retention rebuild note), add `## Releases` (`v1.0.0`, moving `v1`, pin `vX.Y.Z`/sha for Trusted Publishing callers). Keep other sections; add new blocks to `## Development` unit-test note only if needed.

- [ ] 14 CI run on PR branch
  - Deps: 11, 12, 13
  - Files: none
  - Agent: any
  - Verify: all `test-*.yml` + `lint.yml` green on the PR; no `pernix-ci-selftest-*` packages left by the run
  - Purpose: prove G3-G6 in real CI.
  - Push branch; open or update spec PR only with coordinator approval. Watch via `gh run list/watch`. On failure: report failing workflow + log excerpt to coordinator; fixes go to the owning task's files as a new task. Confirm via `gh api` no `pernix-ci-selftest-release-flow-*` package remains. `test-external-caller-v1.yml` NOT run here (post-tag closeout, coordinator asks human before tagging).
