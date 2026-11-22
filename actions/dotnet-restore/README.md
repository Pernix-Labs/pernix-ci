# dotnet-restore

Restores the caller's .NET solution or project with `dotnet restore` and caches the NuGet global packages folder with `actions/cache` (SHA-pinned). Run it after `dotnet-setup` and before `dotnet-build`, `dotnet-test`, `nuget-vulnerability-gate`, and `nuget-deprecation-report`.

The block runs `dotnet restore <project>` in `working-directory`, plus `--locked-mode` when `locked-mode` is `true`. It passes no other switches or MSBuild properties, so caller settings in `Directory.Build.props`, `Directory.Packages.props`, `global.json`, and `nuget.config` apply exactly as in a local restore. When the caller's NuGetAudit settings turn NU1901–NU1904 into errors, restore fails here too. Any restore failure fails the block.

When `project` is empty, the block looks at the top level of `working-directory` and picks exactly one `*.slnx`, else exactly one `*.sln`, else exactly one `*.csproj`. Several candidates of the winning kind, or none, fail the block and list what was found.

## Inputs

| Name | Default | Description |
|---|---|---|
| `working-directory` | `.` | Directory that holds the solution or project. |
| `project` | auto-detect | Solution or project path, relative to `working-directory`. |
| `locked-mode` | `false` | `true` passes `--locked-mode`, so restore fails when a `packages.lock.json` is out of date. |

## Outputs

| Name | Description |
|---|---|
| `project` | Resolved solution or project path, relative to `working-directory`. |
| `cache-hit` | `true` when the NuGet cache key matched exactly. |

## Permissions

```yaml
permissions:
  contents: read
```

## Checkout

The block does not check out code. Run `actions/checkout` first. No special options are needed.

## Caching

The cache holds `~/.nuget/packages`. The key is `nuget-<runner.os>-<hash>`, where the hash covers these files under `working-directory`: `**/Directory.Packages.props`, `**/*.csproj`, `**/packages.lock.json`, `**/global.json`, `**/nuget.config`, and `**/NuGet.Config`. On a miss, the newest cache with prefix `nuget-<runner.os>-` is restored and `dotnet restore` downloads only what is missing. `actions/cache` saves the cache at the end of a successful job.

## Example

```yaml
steps:
  - uses: actions/checkout@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
  - id: restore
    uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
    with:
      locked-mode: "true"
  - run: echo "Restored ${{ steps.restore.outputs.project }} (cache hit: ${{ steps.restore.outputs.cache-hit }})"
```
