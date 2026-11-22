---
status: approved
createdAt: 2026-11-22T20:22:23Z
updatedAt: 2026-11-22T20:27:23Z
approvedAt: 2026-11-22T20:27:23Z
---

# Requirements: P6 ci-release-flow — tag-based CI/CD for .NET mono-repos

**Spec ID:** 2026-11-22-ci-release-flow
**Author:** architect worker (task_a01dd7b4fa92)

## Introduction

P4 (#2) shipped gate blocks, P5 (#1) shipped artifact blocks. P6 composes them into tag-based CI/CD for .NET mono-repos: release-unit resolution, tag parser, reusable CI and CD workflows, caller templates, self-tests, ADR consolidation, README `Workflows`, first `pernix-ci` release `v1.0.0` + moving `v1`.

Flow:
- **CI** (every commit sha): per unit, compute last-touch sha `L`. Default branch: image `ghcr.io/<owner>/<image>:sha-<L>` exists → reuse + rescan. Else build, gate, push, scan. PR: build + scan locally, never push, never reuse. Packages units → gates + pack dry check.
- **CD** (version tag): parse tag → unit + version + commit `T`. Compute `L` at `T`. No `sha-<L>` image → run CI first. Promote image (no rebuild). Caller-owned publish job in `cd.yml`, environment `release`, runs `nuget-pack` + `nuget-push`.

First caller (P7): `Pernix-Labs/pernix-outbox-relay`. Units `relay` (image + packages Core, Hosting, Outbox.PostgreSql, Destination.Kafka) and `client` (3 packages). xunit.v3 on MTP.

## Alignment with Product Vision

No `product.md`. Human rulings 2026-11-22 binding:
- Building blocks small, one thing well.
- Tags `vX.Y.Z[-pre]`, mono-repo `<unit>/vX.Y.Z[-pre]`. Version from tag only.
- GHCR + nuget.org Trusted Publishing. Never an API key.
- Low GHCR retention. No nuget.org unlisting.
- CI fails on secrets and high/critical vulns.
- Caller app code keeps `TreatWarningsAsErrors`.
- No `legacy`/migration guard code.

## Goals

- **G1.** Caller declares units in one matrix file listing only what `slnx`/`csproj` cannot tell. Unit inputs and last-touch sha resolve automatically.
- **G2.** Tag `<unit>/vX.Y.Z[-pre]` (or `vX.Y.Z[-pre]` in single-unit repo) yields unit, SemVer version, commit. Version never read from files.
- **G3.** Reusable CI workflow per commit: on default branch reuse `sha-<L>` image when present, else build + gate + push. On PR build + scan locally, no push. Fails on secret, high/critical vuln (NuGet or image), build error, test failure.
- **G4.** Reusable CD workflow from tag: resolve → CI if image missing → scan → promote. Caller `cd.yml` template publishes packages via Trusted Publishing in caller-defined job, environment `release`.
- **G5.** Scheduled GHCR retention for every unit image via `image-retention`.
- **G6.** Self-tests green on `main`: fixture mono-repo (image unit, package unit, shared project) covers resolution, tag parsing, reuse-vs-build, promote, publish dry-run. External-caller test calls blocks as `Pernix-Labs/pernix-ci/actions/<block>@<sha>`.
- **G7.** `docs/adr/` holds ADRs for P5 and P6 decisions. Root `README.md` `## Workflows` filled.
- **G8.** `pernix-ci` tagged `v1.0.0` + moving `v1` at PR closeout, after human confirmation.

## Non-goals

- **NG1.** Onboarding `pernix-outbox-relay`. Own spec P7.
- **NG2.** Changes to P4/P5 block behaviour. Approved + merged. P6 composes via existing inputs/outputs. Exception only via Q-gated amendment.
- **NG3.** nuget.org Trusted Publishing policy setup, GHCR org settings, GitHub `release` environment creation in caller repos. Human/admin action, documented only.
- **NG4.** Version derivation from files, commit messages, or conventional commits. Ruling: tag only.
- **NG5.** Changelog / GitHub Release generation. Not requested.
- **NG6.** Image signing, SBOM, attestations. Not requested (P5 NG6).
- **NG7.** nuget.org unlisting/deletion. Ruling.
- **NG8.** Non-.NET units, non-GHCR registries, private NuGet feeds. Out of programme scope (P4 NG9, P5 NG8).
- **NG9.** Automatic tag creation / version bumping. Humans push tags.
- **NG10.** Multi-arch images by default. `platforms` passthrough only (P5 default `linux/amd64`).

## Requirements

### Requirement 1 — Release-unit matrix file

**User Story:** As a mono-repo maintainer, I want to list publishable units once, so that CI/CD knows what to build without me listing inputs.

#### Acceptance Criteria

1. Caller repo SHALL declare units in `.github/release-units.yml` (path overridable via workflow input `units-file`).
2. Each unit entry SHALL carry: `name` (`^[a-z0-9][a-z0-9-]*$`, unique), at least one of `image` / `packages`, optional `extra-inputs` (Req 2.3). Unit is the version line: each unit versions independently via its own tags. No `version-line` field, no major-number guard.
3. `image` SHALL carry `project` (entry `.csproj`), `dockerfile`, optional `context` (default repo root), optional `name` (GHCR package name, default unit `name`).
4. `packages` SHALL be a non-empty list of `.csproj` paths to pack.
5. A unit MAY carry both `image` and `packages`. Tag of that unit releases both.
6. Matrix SHALL NOT list transitive projects or repo-wide build inputs. They resolve per Req 2.
7. IF file missing, YAML invalid, unknown key, duplicate name, or referenced path absent THEN resolution SHALL fail before any build with `::error::` naming file, unit, key.
8. WHEN exactly one unit declared THEN tags `vX.Y.Z[-pre]` SHALL be accepted for it (Req 3.2).

### Requirement 2 — Unit input resolution + last-touch sha

**User Story:** As CI, I want each unit's inputs and last-touch commit computed from the project graph and git, so that unchanged units reuse images.

#### Acceptance Criteria

1. New block SHALL resolve units (proposed name `release-units`). It SHALL follow P4/P5 block conventions (composite, kebab-case I/O, README, self-test, SHA-pinned deps, no `actions/_shared`).
2. Per unit, block SHALL compute project closure = all `.csproj` in `image.project` + `packages[]` + unit test projects, plus transitive `ProjectReference`s, as evaluated by MSBuild (incl. references injected by `Directory.Build.props/targets`). Unit test projects = test projects (`IsTestProject`) in `.slnx` referencing any non-test closure project.
3. Unit inputs SHALL be: each closure project's directory (incl. test projects, so a test-only change moves `L`); repo-wide build inputs `Directory.Packages.props`, `Directory.Build.props`, `Directory.Build.targets` (every one in an ancestor dir of any closure project up to repo root), `global.json`, `NuGet.Config` (any case); for image units `dockerfile` and `<context>/.dockerignore`; unit `extra-inputs` pathspecs (Dockerfile `COPY` sources outside project dirs).
4. Inputs SHALL exclude `bin/` and `obj/`.
5. Block SHALL compute last-touch sha `L` = newest commit reachable from current commit touching any unit input (`git log -1` over input pathspecs).
6. IF repo is shallow THEN block SHALL fail with error instructing `fetch-depth: 0`. Never fall back to current sha silently.
7. IF no commit touches inputs (impossible in practice) THEN block SHALL fail.
8. Block SHALL output JSON array, one object per unit: `name`, `kinds` (`image`, `packages`), `last-touch-sha`, `image` (`ghcr.io/<owner lowercase>/<image name>` or empty), `image-project`, `dockerfile`, `context`, `packages` (csproj list), `projects` (closure), `inputs` (pathspecs), `test-projects`.
9. Block SHALL write job summary: unit, kinds, `L`, input count.
10. Block SHALL accept input `unit` to restrict output to one unit (CD).

### Requirement 3 — Tag parser + CI version

**User Story:** As CD, I want one parser turning a tag into unit, version, commit, so that version comes from the tag only.

#### Acceptance Criteria

1. New block SHALL parse tags (proposed name `release-tag`), same conventions as Req 2.1.
2. Grammar: `<unit>/v<semver>` or, single-unit repo only, `v<semver>`. `<semver>` = SemVer 2.0 `MAJOR.MINOR.PATCH[-PRERELEASE]`. Build metadata (`+...`) SHALL be rejected (ruling grammar has none, OCI tags disallow `+`).
3. IF `<unit>` absent from matrix, or bare `v` tag used in multi-unit repo, or grammar mismatch THEN block SHALL fail with `::error::` naming tag and expected form.
4. Block SHALL resolve tag to commit `T` (`<tag>^{commit}`, annotated + lightweight).
5. IF `T` not reachable from default branch THEN block SHALL fail.
6. Block SHALL output `unit`, `version` (no `v`), `prerelease` (`true`|`false`), `commit` (`T`, 40 hex).
7. Version SHALL come only from tag. No block or workflow SHALL read `<Version>`/`<VersionPrefix>` from files.
8. CI builds SHALL use commit-based prerelease version `0.0.0-ci.g<sha7>` of `L`. Value SHALL be valid SemVer 2.0 for every sha.

### Requirement 4 — Reusable CI workflow

**User Story:** As a caller, I want one `uses:` line for per-commit CI, so that every commit is gated and unit images exist for CD.

#### Acceptance Criteria

1. pernix-ci SHALL provide reusable workflow (`on: workflow_call`) for CI (proposed `.github/workflows/ci.yml`). Caller invokes on `push` and `pull_request`.
2. CI SHALL run for commit `S` = push sha or PR head sha. Image push mode: ON for default-branch push and CD-invoked CI, OFF for PR and other branches.
3. CI SHALL run `secret-scan` once per run (repo-wide, `auto` mode).
4. CI SHALL resolve units (Req 2) and fan out one matrix leg per unit.
5. Image leg, push mode ON: `image-exists` on `<image>:sha-<L>`. `exists=true` → reuse, skip setup/build/test, run `image-scan` on existing digest (always rescan), summary states reuse + digest. `exists=false` → `dotnet-setup`, `dotnet-restore`, `nuget-vulnerability-gate`, `nuget-deprecation-report`, `dotnet-build`, `dotnet-test` (unit test projects), `image-build-push` (`sha` = `L`, `version` per Req 3.8), `image-scan` on pushed digest.
6. Image leg, push mode OFF: no `image-exists`, no reuse. Run .NET gates as Req 4.5 `exists=false`, build image locally (load into runner docker, no push), scan local image (vulns + secrets, same fail rule as `image-scan`). Nothing written to GHCR.
7. Packages leg: every run `dotnet-setup`, `dotnet-restore`, `nuget-vulnerability-gate`, `nuget-deprecation-report`, `dotnet-build`, `dotnet-test`, `nuget-pack` dry check (`version` per Req 3.8, temp `output-dir`, never pushed).
8. Unit with both kinds SHALL run image leg logic plus pack dry check in same leg; pack dry check SHALL run even on image reuse.
9. CI SHALL fail on any secret, high/critical NuGet vuln, high/critical image vuln or image secret, restore/build/test failure, pack failure.
10. IF `image-scan` fails after push THEN `sha-<L>` image remains (no delete). Next CI on same `L` reuses and rescans it (Req 4.5), so it fails again until a new commit moves `L` or advisories change.
11. CI SHALL expose outputs per unit: `last-touch-sha`, `image-ref` (`<image>@<digest>`, empty in push mode OFF), `reused` (`true`|`false`).
12. PR CI (push mode OFF) SHALL need no `packages: write` and SHALL run identically for fork PRs.
13. Reusable workflow SHALL accept inputs `units-file`, `working-directory` (mono-repo root inside caller repo, default `.`), `sha` (default per Req 4.2), `unit` (default all), `push-image` (default per Req 4.2 push mode, override for self-tests).
14. Reusable workflows SHALL run blocks from the same pernix-ci commit as the reusable workflow itself (R1).

### Requirement 5 — Reusable CD workflow

**User Story:** As a release manager, I want pushing a tag to ship exactly the tested bits, so that release = promotion, not rebuild.

#### Acceptance Criteria

1. pernix-ci SHALL provide reusable workflow for CD (proposed `.github/workflows/cd.yml`) with input `tag` (default `github.ref_name`).
2. CD SHALL parse tag (Req 3) → `unit`, `version`, `T`. Checkout `T`. Resolve unit (Req 2, `unit` filter) → `L` at `T`.
3. Image kind: `image-exists` on `sha-<L>`. `exists=false` → run reusable CI (Req 4, push mode ON) for `S=T`, `unit`. Then `image-scan` the `sha-<L>` digest (re-scan, new CVEs since CI) and `image-promote` `sha-<L>` → tag `X.Y.Z[-pre]` only (no `v` prefix, no moving `X.Y`/`X`, no `latest`). No rebuild.
4. Packages kind: CD SHALL run reusable CI for `S=T`, `unit` before publish (no reusable artifact signal for packages).
5. CD SHALL expose outputs for caller publish job: `unit`, `version`, `commit` (`T`), `packages` (csproj newline list), `image-ref`, `image-tags`.
6. Reusable CD SHALL NOT call `NuGet/login`, `nuget-push`, or request `id-token: write`.
7. IF any step fails THEN no image tag and no package SHALL be published. Promote SHALL run only after all gates pass. Caller publish job SHALL `needs:` CD.
8. Re-run of CD on same tag SHALL succeed idempotently (promote idempotent per P5 R5.5, `nuget-push` `skip-duplicate`).

### Requirement 6 — Caller templates

**User Story:** As a caller, I want copy-paste workflow templates, so that onboarding is one PR.

#### Acceptance Criteria

1. pernix-ci SHALL ship templates (proposed `templates/`): `ci.yml`, `cd.yml`, `retention.yml`, `release-units.yml` example.
2. `cd.yml` template SHALL trigger on push of tags `v*` and `*/v*`, call reusable CD, then define own job `publish` with `environment: release`, `permissions: id-token: write, contents: read`, `needs:` CD, `if:` packages non-empty.
3. `publish` job SHALL checkout `T`, run `dotnet-setup`, `dotnet-restore`, `nuget-pack` (`projects` = CD `packages`, `version` = CD `version`), `nuget-push` (`user` from caller repo variable), all via `Pernix-Labs/pernix-ci/actions/<block>@<ref>`.
4. Template README / header SHALL state why publish lives in caller `cd.yml`: nuget.org Trusted Publishing policy matches caller workflow file `cd.yml` + environment `release`. File SHALL keep name `cd.yml`.
5. Templates SHALL pin pernix-ci by `vX.Y.Z` tag or full sha, never branch. Third-party actions SHA-pinned.
6. Templates SHALL declare least-privilege `permissions` per job: CI/CD `contents: read`, `packages: write`; publish adds `id-token: write`; retention `packages: write`.
7. Templates SHALL pass actionlint in pernix-ci lint workflow.

### Requirement 7 — Image retention

**User Story:** As org admin, I want unit images pruned on a schedule, so that GHCR storage stays low.

#### Acceptance Criteria

1. pernix-ci SHALL provide reusable retention workflow (proposed `.github/workflows/image-retention.yml`) taking `units-file`, deriving GHCR package names from all image units.
2. Retention SHALL call `image-retention` with P5 defaults (sha-only 14d, prerelease 14d, keep 5 stable) unless caller overrides via inputs.
3. `retention.yml` template SHALL run on `schedule` (daily) + `workflow_dispatch` (with `dry-run` input).
4. WHEN CD finds `sha-<L>` deleted by retention THEN CD SHALL rebuild via CI (Req 5.3). Documented.

### Requirement 8 — Self-tests

**User Story:** As maintainer, I want the full flow exercised on every PR, so that callers never hit regressions first.

#### Acceptance Criteria

1. Fixture mono-repo SHALL live under `tests/fixtures/release-flow/`: `Shared` project, image unit (service project referencing `Shared`, Dockerfile), package unit (library referencing `Shared`), MTP xunit.v3 test project(s), `Directory.Packages.props`, `Directory.Build.props` (`TreatWarningsAsErrors`), `global.json`, `.slnx`, `release-units.yml`.
2. Resolution self-test SHALL materialise fixture into a fresh git repo with scripted commits and assert `L` per unit for: change in `Shared` (both units move), service-only change (image unit only), `Directory.Packages.props` change (both), unrelated file (none), Dockerfile change (image unit only), test-project change (unit with that test project moves), `extra-inputs` path change (that unit only).
3. Tag parser self-test SHALL assert valid: `svc/v1.2.3`, `lib/v1.0.0-rc.1`, `v1.2.3` (single-unit matrix); invalid: unknown unit, bare `v` in multi-unit, `+build`, leading zero, missing `v`, unreachable commit.
4. CI workflow self-test SHALL run reusable CI on fixture with `push-image=true` twice for same `L`: first builds + pushes (`reused=false`), second reuses (`reused=true`, same digest, rescan ran). Plus one run with `push-image=false`: local build + scan, nothing pushed (leftover check).
5. CD workflow self-test SHALL call reusable CD with synthetic tag input, assert promote to run-unique version tag with same digest as `sha-<L>`, then run a `publish` job mirroring `cd.yml` template with `nuget-push` `dry-run=true` (no nuget.org, no `id-token: write`).
6. Image self-tests SHALL use per-run packages `ghcr.io/pernix-labs/pernix-ci-selftest-release-flow-*` and delete them `if: always()` + leftover check (P5 D11, AB2).
7. External-caller self-test SHALL call blocks as `Pernix-Labs/pernix-ci/actions/<block>@<sha>` (deferred from P4), pinned to the literal `main` HEAD sha at PR time. After `v1.0.0` tagging, a run pinned to `@v1` SHALL pass.
8. Unit tests for resolver + tag parser logic SHALL live under `tests/unit/<block>/` (`python3 -I -m unittest`), if logic is python.
9. Self-tests SHALL trigger on `pull_request` + `push` to `main`, least-privilege `permissions`, fork PR skip for registry steps.

### Requirement 9 — Docs + ADRs

**User Story:** As a future maintainer, I want decisions and usage in one place, so that I don't re-derive them from specs.

#### Acceptance Criteria

1. `docs/adr/` SHALL hold ADRs (`NNNN-<slug>.md`) for meaningful P5 decisions (at least: raw OCI promote, sha tag `sha-<40hex>`, Trivy CLI over action, no shared lib for P5, `nuget-push` composite for Trusted Publishing, retention classes) and P6 decisions (matrix file, MSBuild graph resolution, last-touch reuse, tag grammar, CI version, CD split reusable + caller publish).
2. Root `README.md` `## Workflows` SHALL replace placeholder: flow overview, reusable workflow table, caller setup checklist (matrix file, `fetch-depth: 0`, `release` environment, nuget.org policy fields, GHCR Admin), template links. `## Artifacts` placeholder SHALL be filled with P5 block table.
3. Each new block and reusable workflow SHALL have README (purpose, inputs, outputs, permissions, example).

### Requirement 10 — pernix-ci release

**User Story:** As a caller, I want a stable `v1` ref, so that I pin a supported version.

#### Acceptance Criteria

1. At PR closeout, after merge to `main`, coordinator SHALL ask human before tagging.
2. WHEN human approves THEN `v1.0.0` (annotated) and moving `v1` SHALL point at merge commit on `main`.
3. README SHALL document `v1` moves on each `v1.x.y`, and `vX.Y.Z` / sha pinning recommended for Trusted Publishing callers.

## Non-Functional Requirements

### Code Architecture and Modularity
- New blocks single-purpose: resolve units, parse tag. No block calls a block. Composition only in reusable workflows.
- New blocks SHALL NOT use `actions/_shared` (lint guard stays P4-only).
- Reusable workflows thin: wiring of blocks, no inline logic beyond one-line glue.
- No `legacy`/migration guard code.

### Performance
- Unchanged unit on default branch (image exists for `L`) skips SDK setup, build, test. Rescan always runs.
- PR CI writes nothing to GHCR.
- Unit legs run in parallel.

### Security
- No secret inputs. No API key anywhere. `id-token: write` only in caller `publish` job.
- No `pull_request_target`.
- Inputs via `env:`, no `${{ }}` in `run:` bodies.
- Tag/unit strings validated before use in paths, refs, shell.

### Reliability
- Fail closed: shallow clone, missing image on promote, parse errors, API errors → failure.
- Promote and publish idempotent on re-run.
- Concurrent default-branch CI / CD runs on same `L` may both push `sha-<L>`. Accepted: identical inputs. Promote uses digest observed at CD time.
- Reused image rescanned every run, so new advisories fail CI on unchanged units.

### Usability
- Every failure `::error::` with remediation.
- Job summary per run: units, `L`, reused/built, gate results, promoted tags, published packages.

## Findings

- **F1.** Image built in CI carries `BUILD_VERSION` + OCI `version` label = CI version, not release version. Consequence of promote-no-rebuild ruling. Release version lives in image tag only. README SHALL state this.
- **F2.** P5 `image-build-push` default `0.0.0-sha.<sha7>` is invalid SemVer when `sha7` is all digits with leading zero. P6 always passes explicit version (Req 3.8), so P6 avoids it. P5 unchanged (NG2).
- **F3.** GitHub `uses:` takes no expressions. External-caller test cannot reference the PR's own commit (Req 8.7). Reusable workflows cannot statically know their own sha (R1).
- **F4.** P5 `image-build-push` always pushes and `image-scan` scans from registry. PR local build + scan (Req 4.6) is not covered by P5 blocks. Design picks mechanism within NG2 (new single-purpose block or inline wiring).

## Risks

- **R1.** Reusable workflow must run blocks from its own pernix-ci commit (Req 4.14). No GitHub context exposes the called workflow's sha without OIDC. Design must pick: OIDC `job_workflow_sha` claim, caller-passed `pernix-ci-ref`, or pinned literal refs updated at release. Affects G6/G8.
- **R2.** MSBuild graph evaluation needs SDK in resolve job. Adds ~30s per run.
- **R3.** Dockerfile `COPY` of paths outside closure dirs invisible to resolution unless listed in `extra-inputs` → stale reuse if caller omits them.
- **R4.** First caller unit `relay` mixes image + 4 packages under one tag (Req 1.5).
- **R5.** PR CI never pushes, so the first default-branch CI after merge always builds (squash merge creates new sha). Accepted: GHCR storage small, PR images never reusable.

## Resolved questions

Foreman rulings 2026-11-22.

1. [x] **Q1.** Matrix file `.github/release-units.yml`? **Yes** (Req 1.1).
2. [x] **Q2.** Meaning of "version line"? **Dropped.** Unit is the version line. `relay` and `client` version independently via own tags. No `version-line` field, no major-number guard (Req 1.2).
3. [x] **Q3.** One unit holds both `image` and `packages`? **Yes** (Req 1.5).
4. [x] **Q4.** Test projects run in unit leg and count as unit inputs? **Yes** (Req 2.2, 2.3).
5. [x] **Q5.** Optional per-unit `extra-inputs`? **Yes** (Req 1.2, 2.3).
6. [x] **Q6.** CD rejects tag commit not reachable from default branch? **Yes** (Req 3.5).
7. [x] **Q7.** CI version `0.0.0-ci.g<sha7>` of `L`? **Yes** (Req 3.8).
8. [x] **Q8.** PR image push? **Changed.** PR CI builds image and scans locally (load, no push). PR images never reused (squash merges create new shas), GHCR storage small. `sha-<L>` pushed only from default-branch CI and CD (Req 4.2, 4.5, 4.6, 4.12, R5).
9. [x] **Q9.** Rescan on reuse? **Yes, always** (Req 4.5, 4.10).
10. [x] **Q10.** Promoted image tags? **`X.Y.Z[-pre]` only** (Req 5.3).
11. [x] **Q11.** External-caller `@sha` test? **As proposed.** Pin current `main` HEAD sha in this PR, rerun pinned to `@v1` after tagging (Req 8.7).
12. [x] **Q12.** Fill README `## Artifacts`? **Yes** (Req 9.2).
