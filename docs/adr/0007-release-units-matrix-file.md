# ADR 0007: Release-units matrix file

## Status

Accepted (2026-11-22). Spec: [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md), D4, D13, ruling Q2. Block: [`release-units`](../../actions/release-units/README.md).

## Context

- A caller mono-repo releases several units independently (for example `relay` with an image and packages, `client` with packages only).
- `.slnx` and `.csproj` files cannot say which projects form a releasable unit, which project is the image entry point, or which Dockerfile builds it.
- Ruling Q2: the unit is the version line. No separate `version-line` field.

## Decision

Each caller declares units in `.github/release-units.yml` with top-level key `units` only. Per unit: `name` (`^[a-z0-9][a-z0-9-]*$`, unique, equals the tag prefix), optional `image` (`project`, `dockerfile`, `context`, `name`), optional non-empty `packages`, optional `extra-inputs` pathspecs. A unit needs `image` or `packages`. The file lists only what MSBuild cannot tell. Everything else is derived ([ADR 0008](0008-msbuild-graph-last-touch-reuse.md)).

The schema is strict: unknown keys, duplicate or malformed names, absent paths, absolute paths, `..` and pathspec magic fail before any build. `units-file` and all matrix paths are relative to `working-directory`. `yq` v4 (version and SHA-256 pinned) converts YAML to JSON. Retention reads the same file through `release-units` (D13).

## Consequences

- One file per caller drives CI, CD and retention.
- Typos fail early instead of being ignored.
- Dockerfile `COPY` sources outside the project closure must be listed in `extra-inputs`, or changes to them do not move `L`.
- Template: [`templates/release-units.yml`](../../templates/release-units.yml).
