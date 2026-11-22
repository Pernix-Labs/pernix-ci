# ADR 0005: `nuget-push` runs in the caller job

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), R8.1. Used by [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md), D7.

## Context

- Ruling: nuget.org publishing uses Trusted Publishing, never an API key.
- A nuget.org Trusted Publishing policy matches OIDC token claims: repository owner, repository, workflow file and environment.
- In a job inside a reusable workflow, the token carries the reusable workflow's file, not the caller's `cd.yml`. The policy would not match.

## Decision

`nuget-push` is a composite action, never a reusable workflow. It runs inside the caller's `cd.yml` job `publish` with `environment: release` and `permissions: id-token: write`. It gets a short-lived key from `NuGet/login` (input `user`) and has no API key input. `dry-run` pushes to a local folder feed without login.

## Consequences

- Policy fields are fixed: caller owner, caller repo, workflow file `cd.yml`, environment `release`. The caller file must keep the name `cd.yml`.
- `id-token: write` is granted to the caller's `publish` job only. pernix-ci reusable workflows never request it.
- The `publish` job lives in `templates/cd.yml`, so callers copy it ([ADR 0011](0011-cd-split-caller-publish.md)).
- Self-tests exercise dry-run only. The first real nuget.org push happens in a caller repo.
