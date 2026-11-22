# ADR 0010: Tag grammar, tag-only release version, CI version

## Status

Accepted (2026-11-22). Spec: [P6 requirements](../specs/2026-11-22-ci-release-flow/requirements.md) Req 3, [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md) D6, D12. Block: [`release-tag`](../../actions/release-tag/README.md).

## Context

- Ruling: versions come from tags only, never from files or commit messages.
- Units version independently in one repo.
- CI builds (images, pack dry checks) need a valid SemVer version before any tag exists.

## Decision

Release tag grammar: `<unit>/v<semver>`, or bare `v<semver>` in a single-unit repo only. `<semver>` is SemVer 2.0 `MAJOR.MINOR.PATCH[-PRERELEASE]`. Build metadata (`+...`) is rejected because OCI tags disallow `+`. `release-tag` resolves unit, version, prerelease flag and tagged commit, and fails when the unit is unknown or the commit is not reachable from the default branch.

Release version = the tag's `<semver>`. `nuget-pack` gets it as `version`, and `image-promote` tags the image with exactly `<version>` (no `v`, D12).

CI version = `0.0.0-ci.g<L[:7]>`, computed by `release-units`. The `g` prefix keeps it valid SemVer when the short sha is all digits with a leading zero. CI passes it to `image-build-push` (`BUILD_VERSION`, OCI `version` label) and to the `nuget-pack` dry check.

## Consequences

- Caller trigger: `push: tags: ['v*', '*/v*']`.
- A promoted image keeps its CI version in `BUILD_VERSION` and the OCI `version` label. The release version exists only as the image tag (F1).
- No version file to bump. A release is one tag push.
