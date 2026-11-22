# Reusable workflow `image-retention.yml`

Prunes GHCR versions of every image unit in the release-unit matrix. Runs `release-units` on the caller's default branch to derive the GHCR package names, then runs the `image-retention` block on them. When the matrix has no image unit, the job logs a notice and deletes nothing.

Defaults match the `image-retention` block: sha-only and untagged versions expire after 14 days, prerelease versions after 14 days, the newest 5 stable versions are kept. A stable version is tagged `X.Y.Z`, which is the tag `cd.yml` promotes.

A `sha-<L>` image deleted here is rebuilt by the `ci` job of the caller's `cd.yml` on the next release of that unit.

The workflow checks out pernix-ci at its own commit (`job.workflow_sha`) into `pernix-ci/` and calls blocks by local path ([ADR 0012](../adr/0012-reusable-workflow-self-pinning.md)). The caller repo is checked out into `repo/`.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `units-file` | string | `.github/release-units.yml` | Matrix file, relative to `working-directory`. |
| `working-directory` | string | `.` | Mono-repo root inside the caller repo. |
| `dry-run` | boolean | `false` | List planned deletions and delete nothing. |
| `max-age-days` | number | `14` | Delete sha-only (or untagged) versions older than this. |
| `prerelease-max-age-days` | number | `14` | Delete prerelease versions older than this. |
| `keep-versions` | number | `5` | Newest stable versions kept per package. |
| `image-name-prefix` | string | | Prefix for every GHCR package name. Self-tests only. |

## Outputs

None. The job summary of the `image-retention` block lists deleted (or planned) versions.

## Permissions

The calling job grants:

```yaml
permissions:
  contents: read
  packages: write
```

`GITHUB_TOKEN` also needs Admin on each GHCR package. The caller repo has it by default on packages its own workflows first pushed. Otherwise grant it in package settings → Manage Actions access → caller repo, role Admin. Without it, deletes fail.

## Example

```yaml
on:
  schedule:
    - cron: '17 3 * * *'
  workflow_dispatch:
    inputs:
      dry-run:
        type: boolean
        default: false

jobs:
  retention:
    permissions:
      contents: read
      packages: write
    uses: Pernix-Labs/pernix-ci/.github/workflows/image-retention.yml@vX.Y.Z
    with:
      dry-run: ${{ inputs.dry-run || false }}
```

Pin `@vX.Y.Z` or a full commit sha, never a branch.
