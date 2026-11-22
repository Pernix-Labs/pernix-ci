# Reusable workflow `cd.yml`

Releases one unit from a tag. Parses the tag into unit, version and tagged commit `T`, resolves the unit at `T` (last-touch sha `L`), then for an image unit rescans the existing `sha-<L>` image and promotes it to tag `<version>`. It builds nothing and publishes no NuGet package.

The caller's `cd.yml` chains three jobs (see `templates/cd.yml`):

1. `ci`: reusable `ci.yml` with `tag`. Reuses `sha-<L>` when it exists, builds and pushes it when missing, runs all gates.
2. `release`: this workflow, `needs: ci`.
3. `publish`: caller job, `needs: release`, packs and pushes NuGet packages with Trusted Publishing.

When retention deleted `sha-<L>`, the caller's `ci` job rebuilds it before `release` runs. When `sha-<L>` is missing at `release` (the `ci` job was skipped or removed), the `promote` job fails with "run ci job first".

## Jobs

| Job | Runs when | Does |
|---|---|---|
| `resolve` | always | Checks out the caller repo at `commit` if set, else at the tag. Runs `dotnet-setup`, `release-units`, `release-tag`, selects the tagged unit. |
| `promote` | unit has an image | `image-exists` on `sha-<L>` (missing fails), `image-scan` of `<image>@<digest>`, `image-promote` `sha-<L>` → `<version>`. |
| `outputs` | `resolve` succeeded and `promote` succeeded or was skipped | Exposes the workflow outputs. A failed or cancelled `promote` blocks it, so a caller `publish` job gated on this workflow never runs after a failed promote. |

The workflow checks out pernix-ci at its own commit (`job.workflow_sha`) into `pernix-ci/` and calls blocks by local path ([ADR 0012](../adr/0012-reusable-workflow-self-pinning.md)). The caller repo is checked out into `repo/`.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `tag` | string | `github.ref_name` | Release tag `<unit>/vX.Y.Z[-pre]`, or `vX.Y.Z[-pre]` when the matrix has one unit. |
| `units-file` | string | `.github/release-units.yml` | Matrix file, relative to `working-directory`. |
| `working-directory` | string | `.` | Mono-repo root inside the caller repo. |
| `solution` | string | | Solution file, relative to `working-directory`. Empty auto-detects. |
| `image-name-prefix` | string | | Prefix for every GHCR package name. Self-tests only. |
| `commit` | string | | Self-test only. Commit used instead of resolving the tag. Callers leave empty. |
| `default-branch` | string | repository default branch | Self-test only. Branch `T` must be reachable from. Callers leave empty. |

## Outputs

| Name | Description |
|---|---|
| `unit` | Released unit name. |
| `version` | Version without the `v` prefix. |
| `prerelease` | `true` when the version has a prerelease part, else `false`. |
| `commit` | Tagged commit `T`, 40 hex. |
| `packages` | Newline list of the unit's package csproj paths, relative to `working-directory`. Empty for an image-only unit. |
| `image-ref` | Promoted image `<image>@<digest>`. Empty for a packages-only unit. |
| `image-tags` | Newline list of tags promoted to the digest (`<version>`). Empty for a packages-only unit. |

Outputs are empty when the workflow fails.

## Permissions

The calling job grants:

```yaml
permissions:
  contents: read
  packages: write
```

The workflow never requests `id-token: write` and never calls NuGet. Publishing lives in the caller's `publish` job because the nuget.org Trusted Publishing policy matches the caller workflow file `cd.yml` and environment `release`.

## Re-runs

Re-running on the same tag succeeds: `image-promote` is a no-op when `<version>` already points at the `sha-<L>` digest. It fails when `<version>` points at another digest (for example after a retention rebuild produced a new digest). Release a new patch version in that case.

## Example

```yaml
on:
  push:
    tags: ['v*', '*/v*']

concurrency: cd-${{ github.ref }}

jobs:
  ci:
    permissions:
      contents: read
      packages: write
    uses: Pernix-Labs/pernix-ci/.github/workflows/ci.yml@vX.Y.Z
    with:
      tag: ${{ github.ref_name }}

  release:
    needs: ci
    permissions:
      contents: read
      packages: write
    uses: Pernix-Labs/pernix-ci/.github/workflows/cd.yml@vX.Y.Z

  publish:
    needs: release
    if: needs.release.outputs.packages != ''
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          ref: ${{ needs.release.outputs.commit }}
          persist-credentials: false
      # dotnet-setup, dotnet-restore, nuget-pack, nuget-push: see templates/cd.yml
```

Pin `@vX.Y.Z` or a full commit sha, never a branch.
