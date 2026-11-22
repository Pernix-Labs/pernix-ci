---
status: approved
createdAt: 2026-11-22T19:07:25Z
updatedAt: 2026-11-22T19:11:08Z
approvedAt: 2026-11-22T19:11:08Z
---

# Requirements: P5 ci-artifacts — artifact building blocks

**Spec ID:** 2026-11-22-ci-artifacts
**Author:** architect worker (task_0ce8850326bd)

## Introduction

`Pernix-Labs/pernix-ci` (public) hosts reusable GitHub Actions building blocks for Pernix repos. P5 delivers seven single-purpose composite actions for container images (GHCR) and NuGet packages (nuget.org). Callers: .NET repos (net8/net10, `slnx`, `Directory.Packages.props` CPM, `TreatWarningsAsErrors`), runner `ubuntu-latest`. P6 composes blocks into tag-based CI/CD reusable workflows for mono-repos.

Blocks: `image-exists`, `image-build-push`, `image-scan`, `image-promote`, `image-retention`, `nuget-pack`, `nuget-push`.

## Alignment with Product Vision

No `product.md` in repo. Human rulings 2026-11-22 are binding vision:
- Tags `vX.Y.Z[-pre]` (SemVer), mono-repo prefix `<unit>/vX.Y.Z`. Version from tag only.
- Images to GHCR (`ghcr.io/pernix-labs/...`). Low retention, storage small.
- Packages to nuget.org via Trusted Publishing (OIDC, `NuGet/login`). Never an API key. No nuget.org unlisting.
- CI fails on secrets and high/critical vulns. Moderate = report only.
- App code keeps `TreatWarningsAsErrors`.

P5 blocks are version-agnostic: they receive version/tag as input. Tag parsing (`<unit>/vX.Y.Z` → version) is P6.

## Goals

- **G1.** Seven composite actions exist at `actions/<block-name>/action.yml`, each doing one thing, each with `actions/<block-name>/README.md` (purpose, inputs, outputs, permissions, example).
- **G2.** Each block has self-test `.github/workflows/test-<block-name>.yml` (triggers `pull_request` + `push` to `main`) using fixtures under `tests/fixtures/<block-name>/`, green on `main`.
- **G3.** Image self-tests use `ghcr.io/pernix-labs/pernix-ci-selftest-*` with `GITHUB_TOKEN` and leave no residual versions created by the run.
- **G4.** `nuget-push` self-test never contacts nuget.org.
- **G5.** All workflows + action shell pass `actionlint` and `shellcheck` locally.
- **G6.** Every block exposes outputs sufficient for P6 to compose CI (reuse existing sha image) and CD (promote + publish from tag) without reading block internals.

## Non-goals

- **NG1.** Reusable CI/CD workflows composing blocks. Owned by P6.
- **NG2.** Tag parsing, version derivation from `<unit>/vX.Y.Z`. P6. Blocks take version/tags as inputs.
- **NG3.** `.github/workflows/lint.yml`, root `README.md`, `docs/` outside this spec dir, lint config, `.editorconfig`, `CODEOWNERS`. Owned by P4.
- **NG4.** ADRs / `docs/adr` / `docs/architecture`. Decisions recorded in this spec's `design.md`. P6 consolidates.
- **NG5.** Source secret scanning, code quality gates. P4 ci-gates.
- **NG6.** Image signing (cosign), SBOM/attestation publishing. Not requested.
- **NG7.** nuget.org unlisting or deletion. Human ruling forbids.
- **NG8.** API-key NuGet publishing, any registry other than GHCR / nuget.org. Human ruling.
- **NG9.** Versioning/release process of `pernix-ci` itself (`@v1` refs). Not in P5 scope.
- **NG10.** nuget.org Trusted Publishing policy setup, GHCR org/package settings. Human/admin action, documented in READMEs only.

## Requirements

### Requirement 1 — Shared block conventions

**User Story:** As a P6 workflow author, I want uniform, auditable blocks, so that I compose them without surprises.

#### Acceptance Criteria

1. Each block SHALL be a composite action at `actions/<block-name>/action.yml` with `README.md` beside it documenting purpose, inputs, outputs, required job `permissions`, example.
2. Input and output names SHALL be kebab-case.
3. Third-party actions SHALL be pinned by full 40-char commit SHA with trailing `# vX.Y.Z` comment.
4. Each README SHALL state least-privilege `permissions` required by caller job.
5. Blocks SHALL NOT echo secret or token values. WHEN a token is passed THEN block SHALL pass it via env or stdin, never command-line args visible in logs, and SHALL mask derived credentials via `::add-mask::`.
6. Blocks SHALL NOT read or depend on state from another block except via declared inputs.
7. IF a required input is empty or malformed THEN block SHALL fail before any side effect with `::error::` naming the input.
8. Inputs consumed in `run:` scripts SHALL be passed through `env:`, never interpolated `${{ }}` into script body.
9. Image blocks SHALL accept image name as full ref without tag (e.g. `ghcr.io/pernix-labs/foo`). IF registry host is not `ghcr.io` THEN block SHALL fail.
10. Canonical commit tag SHALL be `sha-<full 40-char commit sha>`. Blocks taking a sha SHALL default `sha` input to `${{ github.sha }}`.
11. Every image block (`image-exists`, `image-build-push`, `image-scan`, `image-promote`, `image-retention`) SHALL take `registry-token` input, default `${{ github.token }}`, used for all GHCR registry and GitHub Packages API calls.

### Requirement 2 — `image-exists`

**User Story:** As P6 CI, I want to know whether `<image>:sha-<sha>` already exists, so that I skip rebuild and reuse it.

#### Acceptance Criteria

1. WHEN invoked with `image` + `tag` THEN block SHALL query registry manifest without pulling layers.
2. IF manifest exists THEN block SHALL set output `exists=true` and `digest=<sha256:...>`.
3. IF registry returns not-found THEN block SHALL set `exists=false`, `digest=` empty, and succeed.
4. IF registry returns auth error, rate limit, or 5xx THEN block SHALL fail, never report `false`.
5. Required permission: `packages: read`.

### Requirement 3 — `image-build-push`

**User Story:** As P6 CI, I want to build and push an image tagged by commit sha, so that downstream steps reference one immutable artifact.

#### Acceptance Criteria

1. WHEN invoked with `image`, `context`, `dockerfile` THEN block SHALL run `docker buildx build` and push `<image>:sha-<sha>`.
2. Block SHALL set OCI labels `org.opencontainers.image.revision=<sha>`, `org.opencontainers.image.version=<version>`, `org.opencontainers.image.source=<repo url>`.
3. Block SHALL pass build args `BUILD_VERSION=<version>` and `BUILD_COMMIT=<sha>`. IF `version` input empty THEN `BUILD_VERSION` SHALL be `0.0.0-sha.<short sha>` and label `version` same.
4. Block SHALL accept extra `build-args` (newline list) and `platforms` (default `linux/amd64`).
5. Block SHALL use layer cache (GitHub Actions cache backend) scoped per image, toggleable via `cache` input (default `true`).
6. WHEN push succeeds THEN block SHALL output `image`, `tag`, `digest`, `ref` (`<image>@<digest>`).
7. IF build or push fails THEN block SHALL fail and SHALL NOT push partial tags.
8. Block SHALL NOT add version tags or `latest`. Version tagging is `image-promote` only.
9. Required permissions: `packages: write`, `contents: read`.

### Requirement 4 — `image-scan`

**User Story:** As P6 CI/CD, I want a Trivy scan of a pushed image, so that high/critical vulns and embedded secrets block release.

#### Acceptance Criteria

1. WHEN invoked with `image-ref` (tag or digest ref) THEN block SHALL scan it with Trivy from registry, no local build, running both `vuln` and `secret` scanners.
2. IF any vuln finding has severity in `fail-severities` (default `HIGH,CRITICAL`) THEN block SHALL fail after writing reports.
3. IF any secret is found in image layers THEN block SHALL fail after writing reports, regardless of `fail-severities`.
4. Vuln findings below threshold (e.g. `MEDIUM`) SHALL be reported only, never fail.
5. Block SHALL write SARIF file (vulns + secrets) and output its path as `sarif-file`. Secret values SHALL NOT appear in SARIF, summary, or logs (rule ID + file path only).
6. Block SHALL write summary to `$GITHUB_STEP_SUMMARY`: vuln counts per severity, secret count as separate line, top findings.
7. Block SHALL output `critical-count`, `high-count`, `medium-count`, `low-count`, `secret-count`.
8. Block SHALL accept `ignore-file` (path to `.trivyignore`) and `ignore-unfixed` (default `false`).
9. WHEN `upload-sarif=true` (default `false`) THEN block SHALL upload SARIF to code scanning, requiring `security-events: write`.
10. Block SHALL pin Trivy version. IF Trivy vulnerability DB download fails THEN block SHALL fail, never pass silently.
11. Required permissions: `packages: read` (+ `security-events: write` when uploading).

### Requirement 5 — `image-promote`

**User Story:** As P6 CD, I want to add version tags to an existing sha image, so that release ships exactly the tested bits.

#### Acceptance Criteria

1. WHEN invoked with `image`, `source-tag`, `tags` (newline list) THEN block SHALL add each tag to source manifest via registry-side copy (`docker buildx imagetools create` or equivalent), no rebuild, no layer pull.
2. Promoted tags SHALL resolve to same digest as `source-tag`. Block SHALL verify and fail on mismatch.
3. IF `source-tag` does not exist THEN block SHALL fail before creating any tag.
4. IF a target tag already exists on a different digest THEN block SHALL fail unless `allow-overwrite=true` (default `false`).
5. IF target tag already points to source digest THEN block SHALL treat as success (idempotent re-run).
6. Block SHALL output `digest` and `tags`.
7. Required permission: `packages: write`.

### Requirement 6 — `image-retention`

**User Story:** As org admin, I want old GHCR versions deleted, so that storage stays low.

#### Acceptance Criteria

1. WHEN invoked with `packages` (newline list of GHCR package names) THEN block SHALL list all versions via GitHub Packages API (paginated) for owner `owner` (default `${{ github.repository_owner }}`).
2. Block SHALL classify each version:
   - "stable" IF any tag matches `stable-tag-pattern` (default `^v?[0-9]+\.[0-9]+\.[0-9]+$`).
   - else "prerelease" IF any tag matches `prerelease-tag-pattern` (default `^v?[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z.-]+$`).
   - else "sha-only" (sha tags only, or untagged).
3. Block SHALL delete sha-only versions older than `max-age-days` (default `14`).
4. Block SHALL delete prerelease versions older than `prerelease-max-age-days` (default `14`). Prerelease versions SHALL NOT count toward `keep-versions`.
5. Block SHALL keep newest `keep-versions` (default `5`) stable versions per package, ordered by creation time, and delete older stable versions.
6. Block SHALL NOT delete a version referenced as child manifest by any retained version (multi-arch index, attestation manifest).
7. WHEN `dry-run=true` (default `false`) THEN block SHALL list planned deletions and delete nothing.
8. Block SHALL write planned/executed deletions to `$GITHUB_STEP_SUMMARY` and output `deleted-count`, `kept-count`, `deleted-versions` (JSON array of `{package, id, tags}`).
9. IF any API call fails THEN block SHALL fail and report versions already deleted.
10. Required permission: `packages: write`. `registry-token` SHALL have admin role on target packages. README SHALL state package-admin precondition.

### Requirement 7 — `nuget-pack`

**User Story:** As P6 CD, I want packages built at the tag version, so that package version equals release tag.

#### Acceptance Criteria

1. WHEN invoked with `projects` (newline list of `.csproj` paths), `version`, `output-dir` THEN block SHALL run `dotnet pack -c Release` per project into `output-dir`.
2. Block SHALL set version only from `version` input via `-p:Version=<version>`, overriding any version in project files or `Directory.Build.props`.
3. IF `version` is not valid SemVer 2.0 (no leading `v`) THEN block SHALL fail before packing.
4. Block SHALL pass `-p:ContinuousIntegrationBuild=true` and SHALL NOT override `TreatWarningsAsErrors`.
5. WHEN pack succeeds THEN block SHALL output `packages` (newline list of `.nupkg` paths, excluding `.snupkg`), `package-count`, `output-dir`.
6. IF any produced `.nupkg` version differs from `version` THEN block SHALL fail.
7. Block SHALL NOT install .NET SDK. Caller sets up SDK (documented in README).
8. Required permission: `contents: read`.

### Requirement 8 — `nuget-push`

**User Story:** As P6 CD, I want to publish `.nupkg` to nuget.org via Trusted Publishing, so that no long-lived API key exists.

#### Acceptance Criteria

1. Block SHALL be a composite action running inside caller's job, never a reusable workflow. README SHALL state why: nuget.org Trusted Publishing policy matches caller repo workflow file (`cd.yml`) and environment (`release`).
2. Block SHALL obtain short-lived key via `NuGet/login` (SHA-pinned) using `user` input (nuget.org profile name). Block SHALL have no API key input.
3. Caller job SHALL require `permissions: id-token: write` and `environment: release`. README SHALL show this.
4. WHEN invoked with `packages` (glob or newline list) THEN block SHALL `dotnet nuget push` each `.nupkg` (and matching `.snupkg` if present) to `https://api.nuget.org/v3/index.json`.
5. WHEN `skip-duplicate=true` (default `true`) THEN existing package versions SHALL NOT fail the step.
6. IF `packages` matches zero files THEN block SHALL fail.
7. WHEN `dry-run=true` (default `false`) THEN block SHALL skip `NuGet/login` and push to local folder feed `local-feed-dir`, never contacting nuget.org.
8. Temporary key SHALL be masked and never echoed or written to files/outputs.
9. Block SHALL output `pushed-count`.

### Requirement 9 — Self-tests

**User Story:** As maintainer, I want each block exercised on every PR, so that regressions surface before callers break.

#### Acceptance Criteria

1. Each block SHALL have `.github/workflows/test-<block-name>.yml` triggered on `pull_request` and `push` to `main`, invoking block via local path `./actions/<block-name>`.
2. Fixtures SHALL live only under `tests/fixtures/<block-name>/`.
3. Image self-tests SHALL push only to `ghcr.io/pernix-labs/pernix-ci-selftest-*` with `GITHUB_TOKEN` (`packages: write`), using run-unique tags.
4. Image self-tests SHALL delete versions they created in an `if: always()` cleanup step.
5. `image-exists` self-test SHALL assert both `true` (pushed fixture) and `false` (non-existent tag).
6. `image-scan` self-test SHALL assert pass on clean fixture image, and fail (via `continue-on-error` + outcome check) on fixture with known high/critical vuln and on fixture with embedded dummy secret (non-functional test value), asserting `secret-count` > 0 for the latter.
7. `image-retention` self-test SHALL seed stable, prerelease, and sha-only versions in selftest packages, run `dry-run=true`, and assert classification and planned deletions (stable beyond `keep-versions`, expired prerelease, expired sha-only; prerelease not counted toward `keep-versions`), plus one real-delete run scoped to run-created versions.
8. `nuget-pack` self-test SHALL pack fixture project and assert version and file list.
9. `nuget-push` self-test SHALL run `dry-run=true` with local feed and assert package present in feed. SHALL NOT request `id-token: write`.
10. IF self-test runs from fork PR (no `packages: write`) THEN image self-tests SHALL skip registry steps with notice, not fail.

## Non-Functional Requirements

### Code Architecture and Modularity
- One block = one directory = one responsibility. No shared script library across blocks unless design justifies it.
- Outputs are the only contract between blocks.

### Performance
- `image-exists`, `image-promote` complete without layer transfer.
- `image-build-push` reuses layer cache on unchanged layers.

### Security
- Least-privilege `permissions` per block, documented.
- No secret echo; `set -euo pipefail` in all shell; no `${{ }}` interpolation in `run:` bodies.
- Third-party actions SHA-pinned. Tool binaries (Trivy, crane/oras if used) version-pinned with checksum verification.

### Reliability
- Blocks idempotent on re-run (promote, push with skip-duplicate, retention).
- Registry/API errors fail loudly. No silent `false`/pass.

### Usability
- README example per block is copy-paste runnable.
- Errors via `::error::` naming input or ref.

## Resolved questions

1. Q1. `image-scan` also runs Trivy secret scanner and fails on any secret in image layers (R4.1, R4.3, R4.7, R9.6).
2. Q2. Canonical sha tag `sha-<full 40-char sha>` accepted (R1.10).
3. Q3. Prerelease versions do not count toward `keep-versions`. They expire after `prerelease-max-age-days` (default `14`) (R6.2, R6.4, R6.5, R9.7).
4. Q4. `upload-sarif` default `false` accepted (R4.9).
5. Coordinator change. All image blocks take `registry-token`, default `${{ github.token }}` (R1.11).
