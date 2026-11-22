# release-tag

Parses a release tag into unit, version, prerelease flag and commit `T`, and fails unless `T` is reachable from the default branch. The version comes only from the tag.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `tag` | yes | | Release tag, e.g. `relay/v1.2.3` or `v1.2.3`. |
| `unit-names` | yes | | Newline-separated unit names (`release-units` output `unit-names`). |
| `default-branch` | no | `${{ github.event.repository.default_branch }}` | `T` must be an ancestor of `origin/<default-branch>`. Self-tests pass the PR head branch. |
| `commit` | no | | Self-test only. 40-hex commit used instead of resolving the tag. Callers leave empty. |
| `working-directory` | no | `.` | Directory inside the git checkout. |

## Outputs

| Name | Description |
|---|---|
| `unit` | Unit name. |
| `version` | Version without `v`, e.g. `1.0.0-rc.1`. |
| `prerelease` | `true` when the version has a prerelease part, else `false`. |
| `commit` | `T`, 40 hex. |

## Grammar

- `<unit>/v<semver>`. `<unit>` matches `^[a-z0-9][a-z0-9-]*$` and must be in `unit-names`.
- `v<semver>` only when `unit-names` holds exactly one unit. That unit is the output.
- `<semver>` is SemVer 2.0 `MAJOR.MINOR.PATCH[-PRERELEASE]`. No leading zeros in numeric parts.
- Build metadata (`+...`) is rejected. OCI image tags do not allow `+`.

| Tag | Matrix | Result |
|---|---|---|
| `svc/v1.2.3` | `svc`, `lib` | unit `svc`, version `1.2.3`, prerelease `false` |
| `lib/v1.0.0-rc.1` | `svc`, `lib` | unit `lib`, version `1.0.0-rc.1`, prerelease `true` |
| `v1.2.3` | `svc` | unit `svc`, version `1.2.3` |
| `api/v1.2.3` | `svc`, `lib` | fails: unknown unit |
| `v1.2.3` | `svc`, `lib` | fails: unit required |
| `svc/v1.2.3+build.1` | any | fails: build metadata not allowed |
| `svc/v01.2.3` | any | fails: grammar |
| `svc/1.2.3` | any | fails: grammar |

## Commit resolution

1. `commit` empty: `T` = `refs/tags/<tag>^{commit}`. Annotated and lightweight tags both work. A missing tag fails.
2. `commit` set: it must be 40 lower-case hex and a commit in the checkout. When the tag also exists and points at another commit, the block fails.
3. `git merge-base --is-ancestor T origin/<default-branch>` must succeed, else the block fails.

Every failure is one `::error::release-tag: …` line naming the tag and the expected form. The job summary lists tag, unit, version, prerelease and commit.

## Requirements

- Full git history with tags and `origin/<default-branch>` (`actions/checkout` `fetch-depth: 0`). A shallow repository fails.
- `python3` on `PATH`.

## Permissions

```yaml
permissions:
  contents: read
```

## Example

```yaml
jobs:
  resolve:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          ref: ${{ github.ref_name }}
          fetch-depth: 0
          persist-credentials: false
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<commit-sha> # vX.Y.Z
      - id: units
        uses: Pernix-Labs/pernix-ci/actions/release-units@<commit-sha> # vX.Y.Z
      - id: tag
        uses: Pernix-Labs/pernix-ci/actions/release-tag@<commit-sha> # vX.Y.Z
        with:
          tag: ${{ github.ref_name }}
          unit-names: ${{ steps.units.outputs.unit-names }}
```
