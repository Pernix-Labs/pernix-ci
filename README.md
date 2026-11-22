# pernix-ci

Reusable GitHub Actions building blocks for Pernix .NET repos. Each block is a composite action under `actions/<block-name>/`.

## Using a block

Reference a block by path and ref:

```yaml
steps:
  - uses: actions/checkout@<sha>
    with:
      fetch-depth: 0 # required by secret-scan
  - uses: Pernix-Labs/pernix-ci/actions/<block-name>@<sha|vX.Y.Z>
```

- Pin `<ref>` to a full commit SHA or a `vX.Y.Z` tag. Do not use a branch.
- The caller owns `actions/checkout`. Blocks do not check out code.
- `secret-scan` needs full history: set `fetch-depth: 0` on checkout.

## Conventions

- Each block does one thing. Blocks never call other blocks.
- Inputs and outputs use kebab-case names.
- Third-party actions are pinned by full commit SHA. Downloaded binaries are pinned by version and SHA-256.
- Least-privilege permissions. Blocks need `contents: read` at most.
- Blocks never echo secrets.
- Blocks never override caller MSBuild settings (`global.json`, `Directory.Build.props`, `Directory.Packages.props`, `nuget.config`).
- Every block has a self-test workflow.
- Fixtures live under `tests/fixtures/<block-name>/`.
- Workflows are linted with actionlint and scripts with shellcheck.
- `actions/_shared/` is internal to the gate blocks listed under [Gates](#gates). Other blocks must not use it. Lint enforces this.

## Policy

- CI fails on any detected secret.
- CI fails on high or critical NuGet vulnerabilities. Moderate and low vulnerabilities are reported only.
- Application code keeps `TreatWarningsAsErrors`.
- Callers own their NuGetAudit level. Recommended in `Directory.Build.props`: `NuGetAuditMode=all` and `NuGetAuditLevel=high`.

## Gates

| Block | Purpose |
|---|---|
| [`secret-scan`](actions/secret-scan/README.md) | gitleaks scan of git history or diff. Fails on any finding. |
| [`nuget-vulnerability-gate`](actions/nuget-vulnerability-gate/README.md) | `dotnet list package --vulnerable --include-transitive`. Fails on high or critical. |
| [`nuget-deprecation-report`](actions/nuget-deprecation-report/README.md) | `dotnet list package --deprecated`. Report only. |
| [`dotnet-setup`](actions/dotnet-setup/README.md) | Installs .NET SDK(s) from caller `global.json`. |
| [`dotnet-restore`](actions/dotnet-restore/README.md) | Restores the solution or project. Fails on restore error. |
| [`dotnet-build`](actions/dotnet-build/README.md) | Release build. Fails on build error. |
| [`dotnet-test`](actions/dotnet-test/README.md) | Runs tests (VSTest or MTP), writes TRX and a summary. Fails on test failure. |

## Artifacts

Owned by P5 ci-artifacts.

## Workflows

Owned by P6.

## Development

- Lint: `.github/workflows/lint.yml` runs actionlint, shellcheck over all `*.sh` files, and `.github/scripts/check-shared-usage.sh` on every pull request and push to `main`.
- Self-tests: each block has `.github/workflows/test-<block-name>.yml`.
- Fixtures: `tests/fixtures/<block-name>/`.
- Unit tests: python helpers are tested under `tests/unit/<block-name>/`. Run `python3 -I -m unittest discover -s tests/unit/<block-name>`.
