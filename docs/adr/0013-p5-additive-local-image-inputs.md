# ADR 0013: Additive P5 inputs `image-build-push.push` and `image-scan.image-source`

## Status

Accepted (2026-11-22). Spec: [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md) D9, ruling Q1, F4.

## Context

- PR CI must build and scan images without pushing ([ADR 0009](0009-pr-ci-local-build-no-push.md)).
- P5 `image-build-push` always pushed and `image-scan` always pulled from the registry (F4).
- NG2 forbids changing P4/P5 block behaviour except through a gated amendment.

## Decision

Two additive inputs, defaults unchanged:

- `image-build-push` `push` (default `true`). `false` skips `docker login` and loads the image into the local Docker store as `<image>:sha-<sha>`. `ref` has no `@digest` and `platforms` must be one platform.
- `image-scan` `image-source` (`remote` default, `docker`). `docker` runs Trivy with `--image-src docker` and passes no registry credentials.

Existing P5 self-tests stay green unchanged. Each block's self-test gains one case for the new value.

## Consequences

- P5 callers see byte-for-byte identical behaviour with defaults.
- Local mode needs no `packages` permission, so fork PRs work.
- Two more input combinations to maintain in each block.
