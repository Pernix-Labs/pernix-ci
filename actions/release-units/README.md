# release-units

Validates the release-unit matrix file, resolves each unit's MSBuild project closure and input pathspecs, and computes its last-touch sha `L`: the newest commit reachable from `HEAD` that touches any unit input. CI reuses the `sha-<L>` image of an unchanged unit.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `units-file` | no | `.github/release-units.yml` | Matrix file, relative to `working-directory`. |
| `working-directory` | no | `.` | Mono-repo root inside the git checkout. All matrix paths are relative to it. |
| `solution` | no | | Solution file, relative to `working-directory`. Empty auto-detects exactly one `*.slnx`, else exactly one `*.sln`. |
| `unit` | no | | Restrict output to this unit. Unknown name fails. |
| `owner` | no | `${{ github.repository_owner }}` | GHCR owner, lower-cased in `image`. |
| `image-name-prefix` | no | | Prefix for every GHCR package name (self-tests use per-run packages). |

## Outputs

| Name | Description |
|---|---|
| `units` | JSON array, one object per unit (below). |
| `unit-names` | Newline-separated unit names, in output order. |
| `count` | Number of units in `units`. |

Element of `units`:

```json
{
  "name": "relay",
  "kinds": ["image", "packages"],
  "last-touch-sha": "<40hex>",
  "ci-version": "0.0.0-ci.g<7hex>",
  "image": "ghcr.io/pernix-labs/pernix-outbox-relay",
  "image-package": "pernix-outbox-relay",
  "image-project": "src/Relay/Relay.csproj",
  "dockerfile": "src/Relay/Dockerfile",
  "context": ".",
  "packages": ["src/Core/Core.csproj"],
  "packages-list": "src/Core/Core.csproj",
  "projects": ["src/Core/Core.csproj", "src/Relay/Relay.csproj", "tests/Relay.Tests/Relay.Tests.csproj"],
  "test-projects": ["tests/Relay.Tests/Relay.Tests.csproj"],
  "projects-list": "src/Core/Core.csproj\nsrc/Relay/Relay.csproj\ntests/Relay.Tests/Relay.Tests.csproj",
  "inputs": [":(glob)src/Relay/**", "..."]
}
```

- Project paths are relative to `working-directory`. `inputs` pathspecs are relative to the git repository root.
- Image fields are empty strings for a packages-only unit. `packages` is `[]` for an image-only unit.
- `*-list` fields repeat the arrays as newline strings for block inputs that take newline lists.
- `ci-version` is `0.0.0-ci.g<first 7 hex of L>`. The `g` prefix keeps it valid SemVer 2.0 for every sha, including all-digit shas with a leading zero.

## Matrix file

```yaml
units:
  - name: relay                         # ^[a-z0-9][a-z0-9-]*$, unique, tag prefix
    image:                              # optional
      project: src/Relay/Relay.csproj   # entry project
      dockerfile: src/Relay/Dockerfile
      context: .                        # optional, default "."
      name: pernix-outbox-relay         # optional, default unit name
    packages:                           # optional, non-empty list of .csproj
      - src/Core/Core.csproj
    extra-inputs:                       # optional, Dockerfile COPY sources outside project dirs
      - deploy/entrypoint.sh
```

The schema is strict. The block fails before any build on a missing file, invalid YAML, unknown key, duplicate or malformed name, a unit with neither `image` nor `packages`, an absent path, or a path that is absolute, contains `..`, or starts with pathspec magic `:`. Each problem is one `::error file=<units-file>::unit <name>: key <key>: …` line. `extra-inputs` entries containing `*`, `?` or `[` are git globs and are not checked for existence.

## Resolution

1. Fails when the repository is shallow (`actions/checkout` `fetch-depth: 0`).
2. Closure: breadth-first walk of `ProjectReference` from `image.project` and `packages[]`. Each project is evaluated once with `dotnet msbuild <proj> -getProperty:IsTestProject -getProperty:IsTestingPlatformApplication -getItem:ProjectReference -getItem:PackageReference`, so references injected by `Directory.Build.props/targets` count. No restore runs.
3. Test projects: every project from `dotnet sln <solution> list` is evaluated the same way. A project is a test project when `IsTestProject` or `IsTestingPlatformApplication` is `true`, or it has a `PackageReference` to `Microsoft.NET.Test.Sdk`, `xunit`, `xunit.v3*`, `NUnit`, `MSTest`, `MSTest.TestFramework` or `TUnit` (case-insensitive). The package list is needed because evaluation without restore does not see properties that test packages set. A test project belongs to a unit when it directly references a non-test project of the unit's closure. Its own closure joins the unit.
4. Inputs, per closure project directory: `:(glob)<dir>/**` minus `**/bin/**` and `**/obj/**`. For every ancestor directory of a closure project up to the repo root: `Directory.Build.props`, `Directory.Build.targets`, `Directory.Packages.props`, `global.json`, and `nuget.config` in any case. These are listed whether or not they exist, so adding one later moves `L`. Image units add `dockerfile` and `<context>/.dockerignore`. `extra-inputs` are added as given.
5. `L` = `git log -1 --format=%H HEAD -- <inputs>`. No matching commit fails.

The job summary lists unit, kinds, `L`, input count and test projects.

## Requirements

- .NET SDK on `PATH` (run `dotnet-setup` first). `dotnet sln list` on `.slnx` needs SDK 9.0.200 or later.
- Full git history.
- Linux x64/arm64 runner (macOS arm64 for local runs). `yq` v4.54.3 is downloaded into `$RUNNER_TEMP` and verified by SHA-256.

## Permissions

```yaml
permissions:
  contents: read
```

## Example

```yaml
jobs:
  resolve:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    outputs:
      units: ${{ steps.units.outputs.units }}
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<commit-sha> # vX.Y.Z
      - id: units
        uses: Pernix-Labs/pernix-ci/actions/release-units@<commit-sha> # vX.Y.Z
```
