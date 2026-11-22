# Reusable workflow `ci.yml`

Per-commit CI for .NET mono-repos. Resolves release units from `.github/release-units.yml`, then runs one matrix leg per unit: .NET gates, image build + scan, NuGet pack dry check. A unit whose `sha-<L>` image already exists in GHCR is reused and rescanned instead of rebuilt (`L` = last-touch sha, see [`release-units`](../../actions/release-units/README.md)).

Call it on `push` and `pull_request`. Caller `cd.yml` also calls it with `tag` before the CD workflow (spec D7).

## Jobs

| Job | Does |
|---|---|
| `secret-scan` | `secret-scan` (`auto` mode) on the caller repo, once per run. |
| `resolve` | `dotnet-setup`, `release-units` (all units), `release-tag` when `tag` is set. Selects units (tag unit, else `unit`, else all) and computes push mode and commit `S`. |
| `unit` | Matrix, one leg per unit, `fail-fast: false`. Leg steps below. |
| `summary` | Merges the leg results into output `units`, writes a job summary table, fails when any leg did not succeed and names the failed units. |

Unit leg:

1. Image unit with push mode on: `image-exists` on `<image>:sha-<L>`. Exists → reuse.
2. Not reused, or unit has packages: `dotnet-setup`, `dotnet-unit-solution`, `dotnet-restore` on the generated unit solution.
3. Not reused: `nuget-vulnerability-gate`, `nuget-deprecation-report`, `dotnet-build`, `dotnet-test`. A unit with no test projects skips `dotnet-test` with a notice.
4. Image unit, not reused: `image-build-push` with `sha` = `L`, `version` = CI version `0.0.0-ci.g<L[:7]>`, `push` = push mode.
5. Image unit: `image-scan`, always. Remote digest when push mode is on (reused or pushed), local Docker image when off.
6. Packages unit: `nuget-pack` dry check at the CI version into `$RUNNER_TEMP`. Never pushed. Runs on reuse too.
7. Leg result `{name, last-touch-sha, image-ref, reused}` uploaded as artifact `unit-result-<run_attempt>-<resolve check_run_id>-<name>`. The `check_run_id` of the `resolve` job keeps names unique when one caller run calls `ci.yml` more than once. TRX artifacts use `test-results-<run_attempt>-<resolve check_run_id>-<name>` for the same reason.

Push mode is on when `push-image` is `true`, or `push-image` is `auto` and either `tag` is set or the event is a push to the default branch. Pull requests (including forks) and other branches build and scan locally and write nothing to GHCR.

Workspace per job: caller repo in `repo/`, pernix-ci in `pernix-ci/` at `job.workflow_sha`. Blocks run from that same pernix-ci commit ([ADR 0012](../adr/0012-reusable-workflow-self-pinning.md)). The run fails where `job.workflow_sha` is empty (GHES).

## Inputs

| Name | Default | Description |
|---|---|---|
| `units-file` | `.github/release-units.yml` | Matrix file, relative to `working-directory`. |
| `working-directory` | `.` | Mono-repo root inside the caller repo. |
| `sha` | | Commit to gate. Empty means PR head sha, else `github.sha`. Ignored when `tag` is set. |
| `unit` | | Gate only this unit. Empty gates all. Ignored when `tag` is set. |
| `tag` | | Release tag `<unit>/vX.Y.Z[-pre]` (CD use). Gates the tagged unit at the tagged commit. |
| `commit` | | Self-test only. Commit used instead of resolving `tag`. Callers leave empty. |
| `default-branch` | | Self-test only. Branch the tag commit must be reachable from. Empty means the repository default branch. |
| `push-image` | `auto` | `auto`, `true` or `false`. |
| `image-name-prefix` | | Prefix for every GHCR package name (self-tests). |
| `solution` | | Solution file, relative to `working-directory`. Empty auto-detects one `*.slnx`, else one `*.sln`. |

## Outputs

| Name | Description |
|---|---|
| `units` | JSON array `[{"name", "last-touch-sha", "image-ref", "reused"}]` for the gated units that succeeded. `image-ref` is `<image>@<digest>`, empty in push mode off and for packages-only units. `reused` is `true` or `false`. |
| `unit` | Tagged unit. Empty without `tag`. |
| `version` | Tagged version without `v`. Empty without `tag`. |
| `commit` | Tagged commit. Empty without `tag`. |

## Permissions

The caller job must grant:

```yaml
permissions:
  contents: read
  packages: write
```

`packages: write` is used only in push mode (default-branch push, CD). Pull request runs write nothing to GHCR, and fork pull requests run unchanged with their read-only token.

## Caller example

```yaml
# .github/workflows/ci.yml in the caller repo
name: ci

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  ci:
    uses: Pernix-Labs/pernix-ci/.github/workflows/ci.yml@<commit-sha> # vX.Y.Z
    permissions:
      contents: read
      packages: write
```

The `uses:` ref is the only pin. Blocks follow it through `job.workflow_sha`.
