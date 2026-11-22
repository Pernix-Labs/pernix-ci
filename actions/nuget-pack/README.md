# nuget-pack

Runs `dotnet pack` for each project at exactly the `version` input. The input version overrides any `<Version>` or `<PackageVersion>` set in project files or `Directory.Build.props`.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `projects` | yes | | Newline list of `.csproj` paths. Each path must exist. |
| `version` | yes | | SemVer 2.0 version without a leading `v`, e.g. `1.2.3-rc.1`. Validated with the official semver.org regex. |
| `output-dir` | no | `artifacts/nuget` | Output directory. Created if missing. Must not already contain `.nupkg` files. |
| `configuration` | no | `Release` | Build configuration. |

Invalid inputs fail before any pack runs.

## Outputs

| Name | Description |
|---|---|
| `packages` | Newline list of absolute `.nupkg` paths. Symbol packages (`.snupkg`) are excluded. |
| `package-count` | Number of `.nupkg` files produced. |
| `output-dir` | Absolute path of the output directory. |

## Permissions

```yaml
permissions:
  contents: read
```

## Prerequisites

This block does not install the .NET SDK. The caller job must set it up first, e.g. with `actions/setup-dotnet`.

## Behavior

1. Validates `version` as SemVer 2.0 and checks that every project path exists.
2. Fails if `output-dir` already contains `*.nupkg`. This keeps `packages` limited to this run's output, so no stale package reaches a later push.
3. Per project runs `dotnet pack <proj> -c <configuration> -o <output-dir> -p:Version=<version> -p:PackageVersion=<version> -p:ContinuousIntegrationBuild=true`. `TreatWarningsAsErrors` is not overridden.
4. Collects `*.nupkg` from `output-dir`. Zero packages fails.
5. Reads each package's `.nuspec` with `unzip -p` and fails if its `<version>` differs from `version`.

## Example

```yaml
jobs:
  pack:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<sha> # vX.Y.Z
      - uses: actions/setup-dotnet@<sha> # vX.Y.Z
        with:
          dotnet-version: 8.0.x
      - id: pack
        uses: pernix-labs/pernix-ci/actions/nuget-pack@<sha>
        with:
          projects: |
            src/My.Lib/My.Lib.csproj
          version: 1.2.3
      - env:
          PACKAGES: ${{ steps.pack.outputs.packages }}
        run: printf '%s\n' "$PACKAGES"
```
