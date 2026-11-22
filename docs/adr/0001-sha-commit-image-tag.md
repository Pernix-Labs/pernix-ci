# ADR 0001: Canonical commit image tag `sha-<40hex>`

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), R1.10, ruling Q2.

## Context

- CI builds one image per commit and CD promotes that image without rebuild. Both must name the same image by commit.
- Short shas (7 to 12 characters) can collide in large repos and differ in length between tools.
- OCI tags allow `[A-Za-z0-9_.-]` up to 128 characters, so a full sha fits.

## Decision

The canonical commit tag is `sha-<full 40-char commit sha>`. Blocks that take a sha default it to `${{ github.sha }}`. `image-build-push` always writes exactly this tag. P6 passes the unit's last-touch sha `L`, so the tag is `sha-<L>` ([ADR 0008](0008-msbuild-graph-last-touch-reuse.md)).

## Consequences

- `image-exists` and `image-promote` address an image by commit without a lookup table.
- The tag is unambiguous and stable across tools.
- Tags are long in registry UIs.
- Retention classifies `sha-*`-only versions as sha-only and expires them ([ADR 0006](0006-image-retention-classes.md)).
