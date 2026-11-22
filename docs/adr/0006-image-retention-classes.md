# ADR 0006: Image retention classes stable / prerelease / sha-only

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), R6.2, ruling Q3, D7, AB1.

## Context

- Ruling: keep GHCR retention low.
- GHCR holds three kinds of versions: released (`X.Y.Z`), prereleased (`X.Y.Z-pre`), and commit images (`sha-<40hex>`) or untagged manifests.
- Releases need a rollback window. Prereleases and commit images do not.

## Decision

`image-retention` classifies each version by its tags, first match wins:

1. stable: a tag matches `^v?[0-9]+\.[0-9]+\.[0-9]+$`. Keep the newest `keep-versions` (default 5) by creation time.
2. prerelease: a tag matches `^v?[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z.-]+$`. Delete after `prerelease-max-age-days` (default 14). Does not count toward `keep-versions`.
3. sha-only: anything else. Delete after `max-age-days` (default 14).

A version that is a child manifest of a retained version is kept. The package's last version is kept, and its children are protected too. Each version is re-classified right before `DELETE`.

## Consequences

- Promoted tags are `<version>` without `v` (P6 D12), which the default patterns match.
- Ordering uses manifest push time, so promoting an old commit image yields an "old" stable version.
- A `sha-<L>` image older than 14 days may be gone at release time. The caller `cd.yml` `ci` job rebuilds it ([ADR 0011](0011-cd-split-caller-publish.md)).
- `GITHUB_TOKEN` deletes only when the repo has Admin on the package (default for packages that repo first pushed).
