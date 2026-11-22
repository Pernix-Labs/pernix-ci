# ADR 0002: Promote via raw OCI manifest `PUT`

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), D6, R5.

## Context

- Release must ship exactly the tested bits: the promoted tag must resolve to the same digest as `sha-<L>` (R5.2).
- `docker buildx imagetools create` can rewrite the manifest and change its digest.
- crane or oras would add a tool to install, version-pin and checksum-verify.

## Decision

`image-promote` uses the OCI Distribution API with `curl`: token exchange (`pull,push`), `GET` the source manifest with a four-type `Accept` header, `HEAD` every target, then `PUT` the identical bytes with the identical `Content-Type` to each target, then `HEAD` each target and assert the digest. All targets are checked before the first `PUT`.

## Consequences

- Byte-identical manifest, so the digest is identical, including multi-arch indexes (the `Accept` header stops down-conversion).
- No layer transfer and no extra tool.
- The block owns about 25 lines of token exchange ([ADR 0004](0004-no-shared-lib-for-artifact-blocks.md)).
- A target tag on another digest fails unless `allow-overwrite` is `true`. Re-runs on the same digest succeed.
