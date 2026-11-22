# ADR 0009: PR CI builds and scans locally, pushes only on default branch and CD

## Status

Accepted (2026-11-22). Spec: [P6 requirements](../specs/2026-11-22-ci-release-flow/requirements.md) ruling Q8, Req 4.2, 4.5, 4.6, 4.12. Design: [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md) Push mode, D9.

## Context

- PR images are never reused: squash merges create new shas, so `sha-<L>` on `main` differs from the PR's.
- Pushing PR images costs GHCR storage and needs `packages: write`, which fork PRs do not have.
- PRs still need the image build and the image scan as gates.

## Decision

`ci.yml` computes push mode in the `resolve` job: on when `push-image` is `true`, or `push-image` is `auto` and either `tag` is set (CD) or the event is a push to the default branch. Otherwise off.

Push mode off: `image-build-push` with `push: false` loads the image into the runner's Docker store, and `image-scan` with `image-source: docker` scans it there. No `image-exists` lookup, no reuse, nothing written to GHCR. Push mode on: reuse or build and push `sha-<L>`, scan the remote digest.

## Consequences

- PRs, including forks, gate the image without registry writes.
- GHCR holds only default-branch and CD commit images.
- PR CI always builds image units. No reuse speedup on PRs.
- Needs the additive P5 inputs `push` and `image-source` ([ADR 0013](0013-p5-additive-local-image-inputs.md)).
