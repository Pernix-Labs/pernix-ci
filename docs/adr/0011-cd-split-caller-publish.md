# ADR 0011: CD split into reusable CI, reusable CD and caller `publish`

## Status

Accepted (2026-11-22). Spec: [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md) D7, D14, ruling Q2.

## Context

- CD must release only gated bits and must rebuild `sha-<L>` when retention deleted it.
- A nested `uses: ./.github/workflows/ci.yml` inside a reusable workflow called cross-repo is not documented to resolve to pernix-ci at the same commit. The `owner/repo@ref` form cannot self-pin ([ADR 0012](0012-reusable-workflow-self-pinning.md)).
- NuGet Trusted Publishing must run in the caller's own workflow file ([ADR 0005](0005-nuget-push-in-caller-job.md)).

## Decision

The caller `cd.yml` ([template](../../templates/cd.yml)) chains three jobs:

1. `ci`: reusable `ci.yml` with `tag`. Push mode on. Reuses `sha-<L>` (rescan, pack dry check) or builds, gates and pushes it.
2. `release`: reusable `cd.yml`, `needs: ci`. Resolves tag and unit, requires `sha-<L>` to exist (fails with "run ci job first" otherwise), rescans the digest, promotes to `<version>`. Its `outputs` job exposes results only when `promote` succeeded or was skipped.
3. `publish`: caller job, `needs: release`, runs when the unit has packages, `environment: release`, `id-token: write`. Checks out the tagged commit, `dotnet-setup`, `dotnet-restore`, `nuget-pack` at the release version, `nuget-push`.

`concurrency: cd-${{ github.ref }}` without cancel.

## Consequences

- "CI only when the image is missing" holds in effect: `ci` reuses an existing image and runs only the cheap rescan and dry check.
- pernix-ci reusable workflows never request `id-token: write`.
- Callers own the `publish` job and must keep it in sync with the template.
- A caller that removes the `ci` job gets a failing `release` when `sha-<L>` is missing.
