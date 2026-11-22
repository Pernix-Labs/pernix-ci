# ADR 0004: No shared library for artifact blocks

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), D2, NFR modularity.

## Context

- `image-exists`, `image-promote` and `image-retention` each need an OCI token exchange (about 25 lines).
- `actions/_shared/` is internal to the P4 gate blocks and lint enforces that.
- Blocks must stay standalone: outputs are the only contract between blocks (R1.6).

## Decision

P5 artifact blocks have no shared script library. The token exchange is duplicated in `image-exists.sh`, `image-promote.sh` and `image-retention.sh`. P6 blocks (`release-units`, `release-tag`, `dotnet-unit-solution`) follow the same rule and do not use `actions/_shared/`.

## Consequences

- Each block can be read, tested and changed alone.
- No `actions/_lib` directory in the shared `actions/` namespace.
- A fix to the token exchange must be applied in three scripts.
