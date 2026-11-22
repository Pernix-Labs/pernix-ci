---
status: approved
createdAt: 2026-11-22T19:16:27Z
updatedAt: 2026-11-22T19:59:17Z
approvedAt: 2026-11-22T19:18:24Z
completedAt: 2026-11-22T19:59:17Z
---

# Tasks: P5 ci-artifacts — artifact building blocks

**Spec ID:** 2026-11-22-ci-artifacts
**Requirements:** [requirements.md](./requirements.md)
**Design:** [design.md](./design.md)

Shared rules for every task (read before starting):
- Read `docs/specs/2026-11-22-ci-artifacts/requirements.md` (R1, R9, NFRs) and `design.md` (Architecture, Owner rule, your block's component, Decisions, Testing Strategy row) first.
- Write ONLY files in your task's `Files`. Never touch root `README.md`, `docs/` (spec docs frozen), `.github/workflows/lint.yml`, lint config, `.editorconfig`, `CODEOWNERS` (P4-owned).
- Layout per block: `actions/<block>/action.yml` (thin, inputs → `env:`), `actions/<block>/<block>.sh` (all logic, `set -euo pipefail`, never `set -x`, no `${{ }}` in `run:` bodies), `actions/<block>/README.md` (purpose, inputs, outputs, permissions, example, preconditions).
- Inputs/outputs kebab-case. Third-party actions pinned by full 40-char SHA + `# vX.Y.Z` comment, resolved via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (deref annotated tags). Use latest release of: `actions/checkout` v4/v5, `docker/setup-buildx-action` v3, `docker/build-push-action` v6, `actions/cache` v4, `github/codeql-action` v4, `NuGet/login` v1, `actions/setup-dotnet` v4/v5.
- Self-test `.github/workflows/test-<block>.yml`: `on: pull_request` + `push: branches: [main]`, minimal `permissions` per job, invokes `./actions/<block>`. Image tests: per-run package `pernix-ci-selftest-<block>-${{ github.run_id }}-${{ github.run_attempt }}` (D11), fork-PR skip with notice (R9.10), `if: always()` cleanup deleting whole package via Packages API (owner rule).
- Local verify before done: `shellcheck actions/<block>/*.sh` and `actionlint .github/workflows/test-<block>.yml` clean. CI self-test run is task 9.
- Commit your files on your worktree branch with a message naming the block. No co-author lines.

- [x] 1 image-exists block
  - Files: actions/image-exists/action.yml, actions/image-exists/image-exists.sh, actions/image-exists/README.md, .github/workflows/test-image-exists.yml, tests/fixtures/image-exists/Dockerfile
  - Agent: any
  - Verify: shellcheck actions/image-exists/*.sh && actionlint .github/workflows/test-image-exists.yml clean; outputs and 403 fallback match design D13
  - Isolation: worktree
  - Purpose: report whether `<image>:<tag>` exists in GHCR without pulling (R2, design `image-exists`, D13).
  - Inputs `image`, `tag`, `registry-token` (default `${{ github.token }}`), `registry-username` (default `${{ github.actor }}`). Outputs `exists`, `digest`.
  - Token exchange via `curl -K -` (creds on stdin), mask bearer. `HEAD` manifest with 4-type `Accept`. `200` → true + `Docker-Content-Digest`. `404` → false. `403` from token exchange or HEAD only → owner rule (`GET /users/{owner}` `.type`) → `GET {base}/packages/container/{name}` via `gh api` with `GH_TOKEN=registry-token`: API `404` → false; else fail. `429`/`5xx`: one retry 5s, then fail. All else fail.
  - Validate `image` matches `^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$`, `tag` OCI grammar, before network.
  - Fixture: scratch + `COPY` one file.
  - Self-test asserts: `true` + digest after seed push (plain `docker buildx build --push`); `false` for random tag in existing package; `false` + empty digest for never-created package `pernix-ci-selftest-image-exists-<run_id>-missing`; failure on non-ghcr image (`continue-on-error` + outcome check). Permissions: `packages: write` (seed/cleanup), `contents: read`.
  - README: permission `packages: read`; D13 behavior.

- [x] 2 image-build-push block
  - Files: actions/image-build-push/action.yml, actions/image-build-push/image-build-push.sh, actions/image-build-push/README.md, .github/workflows/test-image-build-push.yml, tests/fixtures/image-build-push/Dockerfile, tests/fixtures/image-build-push/app.txt
  - Agent: any
  - Verify: shellcheck actions/image-build-push/*.sh && actionlint .github/workflows/test-image-build-push.yml clean; tag/labels/build-args/cache match R3 and design
  - Isolation: worktree
  - Purpose: build + push `<image>:sha-<sha>` with OCI labels, build args, gha cache (R3, design `image-build-push`, D4, D12).
  - Inputs per design (`image`, `context`, `dockerfile`, `sha`, `version`, `build-args`, `platforms`, `cache`, `source-url`, `registry-token`, `registry-username`). Outputs `image`, `tag`, `digest`, `ref`.
  - Steps: script `prepare` (validate sha 40-hex, version empty|SemVer 2.0; effective version `0.0.0-sha.<sha7>` if empty; labels `org.opencontainers.image.revision|version|source`; `BUILD_VERSION`/`BUILD_COMMIT` appended after user args; cache `type=gha,scope=<image path>`; `docker login ghcr.io --password-stdin`) → `docker/setup-buildx-action` → `docker/build-push-action` (`push: true`, single tag, `provenance: false`, `sbom: false`) → script `outputs`. No version tags, no `latest`.
  - Fixture Dockerfile: `ARG BUILD_VERSION BUILD_COMMIT`, writes them to `/build-info`; base without `RUN` needing pulls is preferred (busybox pinned by digest acceptable).
  - Self-test asserts: tag `sha-${{ github.sha }}`; labels via `docker buildx imagetools inspect --raw` on config blob; `/build-info` content; second build run shows cache hit (log or timing marker). Cleanup package.
  - README: permissions `packages: write`, `contents: read`; D12 docker config note.

- [x] 3 image-scan block
  - Files: actions/image-scan/action.yml, actions/image-scan/image-scan.sh, actions/image-scan/README.md, .github/workflows/test-image-scan.yml, tests/fixtures/image-scan/clean/Dockerfile, tests/fixtures/image-scan/clean/app.txt, tests/fixtures/image-scan/vulnerable/Dockerfile, tests/fixtures/image-scan/secret/Dockerfile
  - Agent: any
  - Verify: shellcheck actions/image-scan/*.sh && actionlint .github/workflows/test-image-scan.yml clean; fail rule, secret stripping, outputs match R4 and design D3/D5/D9
  - Isolation: worktree
  - Purpose: Trivy vuln + secret scan of pushed image ref; fail on `fail-severities` or any secret (R4, design `image-scan`, D3, D5, D9).
  - Inputs/outputs per design. Steps: `actions/cache` (`~/.cache/trivy/db`, key `trivy-db-<UTC date>`) → script `scan` (install Trivy latest stable release, version + sha256 pinned in script, verify checksum; one `trivy image --scanners vuln,secret --format json --exit-code 0` with DB repos `ghcr.io/aquasecurity/trivy-db,public.ecr.aws/aquasecurity/trivy-db`; registry creds via `TRIVY_USERNAME`/`TRIVY_PASSWORD`; strip `.Secrets[].Match`/`.Code`; `trivy convert --format sarif`; counts; summary) → `github/codeql-action/upload-sarif` if `upload-sarif == 'true'` → script `enforce`.
  - Trivy non-zero exit (DB/auth) → fail. Secret values never in SARIF, summary, logs.
  - Fixtures: clean = scratch + file; vulnerable = old base pinned by digest with known HIGH/CRITICAL CVEs; secret = busybox-based, secret-pattern string (GitHub PAT format) assembled at build time from split build-arg fragments passed by workflow, so no matching literal in repo (D9).
  - Self-test asserts: clean → `result=pass`; vulnerable → step failure + `high-count+critical-count>0`; secret → failure + `secret-count>0`; grep SARIF + summary file for secret value → absent. Permissions: `packages: write`, `contents: read`. Never `upload-sarif` in self-test.

- [x] 4 image-promote block
  - Files: actions/image-promote/action.yml, actions/image-promote/image-promote.sh, actions/image-promote/README.md, .github/workflows/test-image-promote.yml, tests/fixtures/image-promote/Dockerfile, tests/fixtures/image-promote/app.txt
  - Agent: any
  - Verify: shellcheck actions/image-promote/*.sh && actionlint .github/workflows/test-image-promote.yml clean; raw manifest copy preserves digest incl. multi-arch index
  - Isolation: worktree
  - Purpose: add tags to existing manifest, byte-identical, no rebuild (R5, design `image-promote`, D6).
  - Inputs `image`, `source-tag`, `tags` (newline list), `allow-overwrite` (default `false`), common. Outputs `digest`, `tags`.
  - Logic: validate tags (OCI grammar) → token exchange `pull,push` → `GET` source manifest with 4-type `Accept` (`application/vnd.oci.image.index.v1+json`, `application/vnd.oci.image.manifest.v1+json`, `application/vnd.docker.distribution.manifest.list.v2+json`, `application/vnd.docker.distribution.manifest.v2+json`), keep raw bytes + `Content-Type` + digest; `404` → fail → `HEAD` all targets first (same digest skip, different digest fail unless `allow-overwrite`) → `PUT` identical bytes with returned `Content-Type` → `HEAD` verify digest.
  - Fixture: scratch + `COPY` only (no `RUN`, so multi-platform builds need no QEMU).
  - Self-test asserts: promote `sha-x` → `1.2.3`, `v1.2.3`, equal digests; re-run idempotent; conflicting tag fails without `allow-overwrite`; missing source fails; index built `--platform linux/amd64,linux/arm64` promotes with equal digest and OCI index `mediaType`. Cleanup package.

- [x] 5 image-retention block
  - Files: actions/image-retention/action.yml, actions/image-retention/image-retention.sh, actions/image-retention/README.md, .github/workflows/test-image-retention.yml, tests/fixtures/image-retention/Dockerfile
  - Agent: any
  - Verify: shellcheck actions/image-retention/*.sh && actionlint .github/workflows/test-image-retention.yml clean; classification, keep/age rules, child protection, last-version guard, D14 message match R6 and design
  - Isolation: worktree
  - Purpose: delete expired GHCR versions (R6, design `image-retention`, D7, D14, owner rule).
  - Inputs per design incl. `reference-time`; outputs `deleted-count`, `kept-count`, `deleted-versions`.
  - Logic: owner rule → `gh api --paginate` versions → classify stable > prerelease > sha-only → mark (stable beyond `keep-versions` by `created_at`; prerelease > `prerelease-max-age-days`; sha-only > `max-age-days`; age vs `reference-time`) → child protection (index `manifests[].digest` of retained versions via registry `GET`, 4-type `Accept`) → last-version guard → unless `dry-run`: re-`GET` + re-classify, `DELETE`. `403` at DELETE → `::error::` from `remediation_message` (subcommand `remediation-message`, text per D14, org/user settings URL), deleted-so-far, outputs, exit 1. Other API error → same without remediation text.
  - Summary table per package.
  - Fixture: scratch + `ARG SEED` label for distinct digests.
  - Self-test asserts: seed 7 stable, 2 prerelease, 3 sha-only in per-run package; `dry-run=true`, `reference-time`=now+30d → plan deletes 2 oldest stable, both prerelease, sha-only subject to guards, prerelease not counted in keep-5; real-delete run → `deleted-count` matches plan; `image-retention.sh remediation-message` for org and user → expected URL + "Manage Actions access" text. Cleanup package.
  - README: Admin precondition, "Manage Actions access" steps, R5 created_at note, `reference-time` purpose.

- [x] 6 nuget-pack block
  - Files: actions/nuget-pack/action.yml, actions/nuget-pack/nuget-pack.sh, actions/nuget-pack/README.md, .github/workflows/test-nuget-pack.yml, tests/fixtures/nuget-pack/Directory.Build.props, tests/fixtures/nuget-pack/Fixture.Lib/Fixture.Lib.csproj, tests/fixtures/nuget-pack/Fixture.Lib/Class1.cs
  - Agent: any
  - Verify: shellcheck actions/nuget-pack/*.sh && actionlint .github/workflows/test-nuget-pack.yml clean; local run of nuget-pack.sh on fixture with dotnet produces 1.2.3-rc.1 package
  - Isolation: worktree
  - Purpose: `dotnet pack` projects at input version only (R7, design `nuget-pack`, D8).
  - Inputs `projects`, `version`, `output-dir` (default `artifacts/nuget`), `configuration` (default `Release`). Outputs `packages`, `package-count`, `output-dir` (absolute).
  - Logic: SemVer 2.0 regex (no `v`) → projects exist → fail if `output-dir` has `*.nupkg` → per project `dotnet pack -c <cfg> -o <out> -p:Version=<v> -p:PackageVersion=<v> -p:ContinuousIntegrationBuild=true` → collect `.nupkg` (exclude `.snupkg`), zero → fail → nuspec version check via `unzip -p`.
  - Fixture: net8.0 lib, `TreatWarningsAsErrors=true`, `Directory.Build.props` sets `<Version>9.9.9</Version>` to prove override. No CPM needed in fixture.
  - Self-test (uses `actions/setup-dotnet` 8.0.x): version `1.2.3-rc.1` → package version matches, `package-count=1`; `v1.2.3` fails; non-empty output-dir fails. Permissions `contents: read`.
  - README: caller must set up SDK.

- [x] 7 nuget-push block
  - Files: actions/nuget-push/action.yml, actions/nuget-push/nuget-push.sh, actions/nuget-push/README.md, .github/workflows/test-nuget-push.yml, tests/fixtures/nuget-push/Fixture.Push/Fixture.Push.csproj, tests/fixtures/nuget-push/Fixture.Push/Class1.cs
  - Agent: any
  - Verify: shellcheck actions/nuget-push/*.sh && actionlint .github/workflows/test-nuget-push.yml clean; no API key input; dry-run path never contacts nuget.org
  - Isolation: worktree
  - Purpose: push `.nupkg` to nuget.org via Trusted Publishing, in caller's job (R8, design `nuget-push`).
  - Inputs `packages`, `user`, `skip-duplicate` (`true`), `dry-run` (`false`), `local-feed-dir` (empty → `$RUNNER_TEMP/nuget-local-feed`). No API key input. Output `pushed-count`.
  - Steps: script `resolve` (globstar/nullglob, `.nupkg` only, zero → fail; `user` required unless dry-run) → `NuGet/login` (`id: login`, `if: inputs.dry-run != 'true'`) → script `push` (env `NUGET_API_KEY` from login output; real → `https://api.nuget.org/v3/index.json` `--api-key "$NUGET_API_KEY"`; dry-run → local folder, no key; `--skip-duplicate` per input).
  - Self-test: plain `dotnet pack` fixture (setup-dotnet 8.0.x) → `dry-run=true` → package in local feed, `pushed-count=1`; re-push with `skip-duplicate` succeeds; zero-match glob fails. Job `permissions: contents: read` only, no `id-token: write`.
  - README MUST state: composite action, runs inside caller job, NOT a reusable workflow, because nuget.org Trusted Publishing policy matches caller repo workflow file (`cd.yml`) and environment (`release`). Example job with `environment: release`, `permissions: id-token: write, contents: read`. Troubleshooting: policy fields. No API key ever.

- [x] 8 Cross-block consistency audit
  - Deps: 1, 2, 3, 4, 5, 6, 7
  - Files: actions/image-exists/action.yml, actions/image-build-push/action.yml, actions/image-scan/action.yml, actions/image-promote/action.yml, actions/image-retention/action.yml, actions/nuget-pack/action.yml, actions/nuget-push/action.yml, actions/image-exists/README.md, actions/image-build-push/README.md, actions/image-scan/README.md, actions/image-promote/README.md, actions/image-retention/README.md, actions/nuget-pack/README.md, actions/nuget-push/README.md, .github/workflows/test-image-exists.yml, .github/workflows/test-image-build-push.yml, .github/workflows/test-image-scan.yml, .github/workflows/test-image-promote.yml, .github/workflows/test-image-retention.yml, .github/workflows/test-nuget-pack.yml, .github/workflows/test-nuget-push.yml
  - Agent: any
  - Verify: shellcheck actions/*/*.sh && actionlint .github/workflows/test-*.yml clean; every `uses:` third-party ref is 40-char SHA + version comment; same action → same SHA everywhere
  - Purpose: align merged blocks with shared conventions (R1, G1, G5, G6).
  - Checks + minimal fixes: one SHA per third-party action across all files; kebab-case names; `registry-token`/`registry-username` defaults identical on image blocks; no `${{ }}` in `run:` bodies; every README has purpose, inputs, outputs, permissions, example; outputs match design "Block output contract". Do not change block logic; report anything beyond conventions to coordinator.

- [x] 9 CI self-test run on PR branch
  - Deps: 8
  - Files: none
  - Agent: any
  - Verify: all seven `test-*.yml` workflows green on the PR; no `pernix-ci-selftest-*` packages left by the run
  - Purpose: prove G2, G3, G4 in real CI (GHCR, gha cache, Trivy DB).
  - Push branch, open or update the spec PR only with coordinator approval (outward-facing). Watch runs via `gh run list/watch`. On failure: report failing block + log excerpt to coordinator; fixes go back to that block's files as a new task. Confirm via `gh api` that no `pernix-ci-selftest-*` package remains from the run. If GHCR denies package create/delete (R1/R2), escalate.
