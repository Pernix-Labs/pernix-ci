# ADR 0008: MSBuild graph resolution, pathspec inputs, last-touch reuse

## Status

Accepted (2026-11-22). Spec: [P6 requirements](../specs/2026-11-22-ci-release-flow/requirements.md) Req 2, [P6 ci-release-flow design](../specs/2026-11-22-ci-release-flow/design.md) D5. Block: [`release-units`](../../actions/release-units/README.md).

## Context

- CI should not rebuild a unit's image when nothing the unit depends on changed since the last build.
- Unit dependencies live in `ProjectReference` items, including ones injected by `Directory.Build.props/targets`, and in build-wide files (`Directory.Packages.props`, `global.json`, `nuget.config`).
- Hand-maintained input lists drift.

## Decision

`release-units` resolves each unit from MSBuild evaluation and git:

1. Closure: breadth-first walk of `ProjectReference` from `image.project` and `packages[]`. Each project is evaluated once with `dotnet msbuild -getProperty -getItem`. No restore.
2. Test projects: every project in the solution is evaluated. A project is a test project when `IsTestProject` or `IsTestingPlatformApplication` is `true`, or it has a `PackageReference` to a known test framework (`Microsoft.NET.Test.Sdk`, `xunit`, `xunit.v3*`, `NUnit`, `MSTest`, `MSTest.TestFramework`, `TUnit`). Evaluation without restore does not see properties set by test packages, hence the package list.
3. A test project joins a unit only when it directly references a non-test project of the unit's closure. Transitive matching would make `Svc.Tests` a test of a package unit through a shared project. The test project's own closure joins the unit.
4. Inputs as git pathspecs: each closure project directory minus `bin/` and `obj/`, every ancestor's `Directory.Build.props`, `Directory.Build.targets`, `Directory.Packages.props`, `global.json` and `nuget.config` (any case, listed whether present or not), the Dockerfile and `<context>/.dockerignore`, and `extra-inputs`.
5. Last-touch sha `L` = `git log -1 --format=%H HEAD -- <pathspecs>`.

CI looks up `sha-<L>` ([ADR 0001](0001-sha-commit-image-tag.md)). Present: reuse it, skip build and gates, rescan, pack dry check. Missing: build, gate, push. Each unit is gated through a generated `.slnx` holding its closure and test projects (`dotnet-unit-solution`, D5), so the single-`project` P4 blocks scope to the unit without change.

## Consequences

- Commits that do not touch a unit's inputs reuse its image.
- Requires full history (`fetch-depth: 0`). The block fails on a shallow clone. Reusable workflows set it.
- One MSBuild evaluation per project (about 1 to 2 s). Fine below about 30 projects.
- Requires SDK 9.0.200 or later for `.slnx`.
- Inputs not visible to MSBuild or git pathspecs (for example Dockerfile `COPY` sources outside the closure) need `extra-inputs` ([ADR 0007](0007-release-units-matrix-file.md)).
