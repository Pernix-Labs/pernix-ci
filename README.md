# pernix-ci

Reusable GitHub Actions building blocks for Pernix .NET repos. Each block is a composite action under `actions/<block-name>/`.

## Using a block

Reference a block by path and ref:

```yaml
steps:
  - uses: actions/checkout@<sha>
    with:
      fetch-depth: 0 # required by secret-scan
  - uses: Pernix-Labs/pernix-ci/actions/<block-name>@<sha|vX.Y.Z>
```

- Pin `<ref>` to a full commit SHA or a `vX.Y.Z` tag. Do not use a branch.
- The caller owns `actions/checkout`. Blocks do not check out code.
- `secret-scan` needs full history: set `fetch-depth: 0` on checkout.

## Conventions

- Each block does one thing. Blocks never call other blocks.
- Inputs and outputs use kebab-case names.
- Third-party actions are pinned by full commit SHA. Downloaded binaries are pinned by version and SHA-256.
- Least-privilege permissions. Blocks need `contents: read` at most.
- Blocks never echo secrets.
- Blocks never override caller MSBuild settings (`global.json`, `Directory.Build.props`, `Directory.Packages.props`, `nuget.config`).
- Every block has a self-test workflow.
- Fixtures live under `tests/fixtures/<block-name>/`.
- Workflows are linted with actionlint and scripts with shellcheck.
- `actions/_shared/` is internal to the gate blocks listed under [Gates](#gates). Other blocks must not use it. Lint enforces this.

## Policy

- CI fails on any detected secret.
- CI fails on high or critical NuGet vulnerabilities. Moderate and low vulnerabilities are reported only.
- Application code keeps `TreatWarningsAsErrors`.
- Callers own their NuGetAudit level. Recommended in `Directory.Build.props`: `NuGetAuditMode=all` and `NuGetAuditLevel=high`.

## Gates

| Block | Purpose |
|---|---|
| [`secret-scan`](actions/secret-scan/README.md) | gitleaks scan of git history or diff. Fails on any finding. |
| [`nuget-vulnerability-gate`](actions/nuget-vulnerability-gate/README.md) | `dotnet list package --vulnerable --include-transitive`. Fails on high or critical. |
| [`nuget-deprecation-report`](actions/nuget-deprecation-report/README.md) | `dotnet list package --deprecated`. Report only. |
| [`dotnet-setup`](actions/dotnet-setup/README.md) | Installs .NET SDK(s) from caller `global.json`. |
| [`dotnet-restore`](actions/dotnet-restore/README.md) | Restores the solution or project. Fails on restore error. |
| [`dotnet-build`](actions/dotnet-build/README.md) | Release build. Fails on build error. |
| [`dotnet-test`](actions/dotnet-test/README.md) | Runs tests (VSTest or MTP), writes TRX and a summary. Fails on test failure. |

## Artifacts

| Block | Purpose |
|---|---|
| [`image-exists`](actions/image-exists/README.md) | Reports whether `<image>:<tag>` exists in GHCR, with its digest. No layer pull. |
| [`image-build-push`](actions/image-build-push/README.md) | Builds `<image>:sha-<sha>` with buildx and pushes it to GHCR. |
| [`image-scan`](actions/image-scan/README.md) | Trivy vulnerability and secret scan. Fails on high or critical vulnerabilities and on any secret. |
| [`image-promote`](actions/image-promote/README.md) | Adds tags to an existing image manifest. Same digest, no rebuild. |
| [`image-retention`](actions/image-retention/README.md) | Deletes expired GHCR versions by class: stable, prerelease, sha-only. |
| [`nuget-pack`](actions/nuget-pack/README.md) | `dotnet pack` at a given SemVer version. |
| [`nuget-push`](actions/nuget-push/README.md) | Pushes packages to nuget.org with Trusted Publishing. Runs in the caller job. |

- `image-build-push` input `push` (default `true`): `false` loads the image into the runner's Docker store and writes nothing to GHCR.
- `image-scan` input `image-source` (default `remote`): `docker` scans an image in the local Docker store, for example one built with `push: false`.
- Both inputs are additive. Defaults keep the original behaviour ([ADR 0013](docs/adr/0013-p5-additive-local-image-inputs.md)).

## Workflows

Reusable workflows compose the blocks into CI and CD for .NET mono-repos. A repo declares release units (a deployable image, NuGet packages, or both) in `.github/release-units.yml`.

Flow:

1. CI per commit (`push` to the default branch, `pull_request`): resolve units and their last-touch sha `L`, then per unit run the .NET gates, build and scan the image, and dry-check `nuget-pack`. On the default branch an existing `sha-<L>` image is reused and rescanned instead of rebuilt, and a new one is pushed. On pull requests the image is built and scanned locally and never pushed.
2. CD per tag (`<unit>/vX.Y.Z[-pre]`, or `vX.Y.Z[-pre]` in a single-unit repo): the caller `cd.yml` runs CI for the tagged commit, then reusable `cd.yml` rescans `sha-<L>` and promotes it to tag `X.Y.Z[-pre]`, then the caller `publish` job packs and pushes NuGet packages at that version.
3. Retention on a schedule: delete expired GHCR versions of every unit image.

Reusable workflows check out pernix-ci at their own commit (`job.workflow_sha`) and call blocks from it, so the `uses:` ref pins everything ([ADR 0012](docs/adr/0012-reusable-workflow-self-pinning.md)). They need github.com. Decisions: [ADR 0001-0013](docs/adr/).

| Reusable workflow | Purpose |
|---|---|
| [`ci.yml`](docs/workflows/ci.md) | Per-commit CI: resolve units, gate, build or reuse, scan, pack dry check. |
| [`cd.yml`](docs/workflows/cd.md) | Per-tag release: parse tag, rescan and promote `sha-<L>` to `<version>`. No build, no NuGet push. |
| [`image-retention.yml`](docs/workflows/image-retention.md) | Scheduled GHCR cleanup for every image unit. |

| Block | Purpose |
|---|---|
| [`release-units`](actions/release-units/README.md) | Validates the matrix file, resolves each unit's projects, inputs and last-touch sha `L`. |
| [`release-tag`](actions/release-tag/README.md) | Parses a release tag into unit, version and commit. Checks the commit is on the default branch. |
| [`dotnet-unit-solution`](actions/dotnet-unit-solution/README.md) | Writes a `.slnx` with one unit's projects, so the gate blocks scope to that unit. |

Caller setup:

1. Add `.github/release-units.yml` ([ADR 0007](docs/adr/0007-release-units-matrix-file.md)).
2. Copy the templates to `.github/workflows/`. Keep the name `cd.yml`.
3. `fetch-depth: 0` is handled by the reusable workflows. Direct users of `release-units` and `release-tag` must set it.
4. Create environment `release` in the repo settings.
5. Add a nuget.org Trusted Publishing policy: repository owner, repository, workflow file `cd.yml`, environment `release`.
6. Set repository variable `NUGET_USER` to the nuget.org profile name that owns the policy.
7. Give the repo Admin on each GHCR package for retention. This is the default for packages the repo's workflows pushed first. Otherwise: package settings, Manage Actions access, add the repo with Admin.
8. Pin pernix-ci by `vX.Y.Z` tag or full commit sha, never a branch. Use the same ref on every pernix-ci line.

Templates:

- [`templates/ci.yml`](templates/ci.yml): CI on push to `main` and pull requests.
- [`templates/cd.yml`](templates/cd.yml): jobs `ci`, `release`, `publish` on release tags.
- [`templates/retention.yml`](templates/retention.yml): daily retention plus manual dry run.
- [`templates/release-units.yml`](templates/release-units.yml): matrix file example.

Notes:

- An image's `BUILD_VERSION` build arg and OCI `version` label hold the CI version `0.0.0-ci.g<L[:7]>`, not the release version. Promotion does not rebuild, so the release version exists only as the image tag ([ADR 0010](docs/adr/0010-tag-grammar-and-versions.md)).
- Retention deletes `sha-<L>` images after 14 days. When a release tag points at such a commit, the `ci` job of the caller `cd.yml` rebuilds `sha-<L>` before promotion ([ADR 0011](docs/adr/0011-cd-split-caller-publish.md)).

## Releases

- pernix-ci releases are tagged `vX.Y.Z`. The first is `v1.0.0`.
- `v1` is a moving tag. It moves to each new `v1.x.y`.
- Callers using nuget.org Trusted Publishing should pin `vX.Y.Z` or a full commit sha, not `v1`, so the code that runs with `id-token: write` changes only when they change the pin.

## Development

- Lint: `.github/workflows/lint.yml` runs actionlint, shellcheck over all `*.sh` files, and `.github/scripts/check-shared-usage.sh` on every pull request and push to `main`. It also lints `templates/ci.yml`, `templates/cd.yml` and `templates/retention.yml`.
- actionlint 1.7.12 does not know `job.workflow_sha`. `.github/actionlint.yaml` ignores that one error for `ci.yml`, `cd.yml` and `image-retention.yml`. Remove the entries once actionlint supports it.
- Self-tests: each block has `.github/workflows/test-<block-name>.yml`.
- Fixtures: `tests/fixtures/<block-name>/`.
- Unit tests: python helpers are tested under `tests/unit/<block-name>/`. Run `python3 -I -m unittest discover -s tests/unit/<block-name>`.
