# nuget-deprecation-report

Lists deprecated NuGet packages, direct and transitive, so you can plan replacements. Deprecations never fail the step. Run it after `dotnet-restore`.

The block runs this in `working-directory`:

```sh
dotnet list <project> package --deprecated --include-transitive --no-restore --format json --output-version 1
```

`--no-restore` stops the .NET 10 SDK from restoring implicitly, so a missing `dotnet-restore` step fails the block instead of being hidden. The block passes no MSBuild properties.

When `project` is empty, the block looks at the top level of `working-directory` and picks exactly one `*.slnx`, else exactly one `*.sln`, else exactly one `*.csproj`. Several candidates of the winning kind, or none, fail the block and list what was found.

## Inputs

| Name | Default | Description |
|---|---|---|
| `working-directory` | `.` | Directory that holds the solution or project. |
| `project` | auto-detect | Solution or project path, relative to `working-directory`. |

## Outputs

| Name | Description |
|---|---|
| `deprecated-count` | Unique deprecated packages (package + resolved version), direct and transitive. |

## Permissions

```yaml
permissions:
  contents: read
```

## Behaviour

| Condition | Result |
|---|---|
| Deprecated packages | pass, `::warning::` per direct package |
| No deprecated packages | pass |
| Project not restored (no `project.assets.json`) | fail: "run dotnet-restore first" |
| `dotnet list` exits non-zero, reports an error, or prints invalid JSON | fail (never reported as zero) |

The job summary lists projects, target frameworks, package, resolved version, deprecation reasons, alternative package with version range (`none` when nuget.org names none), and direct or transitive. Rows repeated across target frameworks or projects collapse to one row listing all of them. A package counts as direct when it is a top-level reference in any project.

## Example

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
  - id: deprecated
    uses: Pernix-Labs/pernix-ci/actions/nuget-deprecation-report@<sha> # vX.Y.Z
  - run: echo "deprecated=${{ steps.deprecated.outputs.deprecated-count }}"
```
