# dotnet-build

Builds the caller's restored .NET solution or project with `dotnet build` and keeps the caller's strictness intact. Run it after `dotnet-setup` and `dotnet-restore`, and before `dotnet-test`.

The block runs this command in `working-directory`:

```sh
dotnet build <project> --configuration <configuration> --no-restore <build-args...>
```

It passes no MSBuild properties of its own. Caller settings in `Directory.Build.props`, `Directory.Packages.props`, and the project files apply exactly as in a local build. When the caller sets `TreatWarningsAsErrors`, any warning fails the build. Every `TargetFramework` the caller declares is built. Any build failure fails the block.

When `project` is empty, the block looks at the top level of `working-directory` and picks exactly one `*.slnx`, else exactly one `*.sln`, else exactly one `*.csproj`. Several candidates of the winning kind, or none, fail the block and list what was found.

## Inputs

| Name | Default | Description |
|---|---|---|
| `working-directory` | `.` | Directory that holds the solution or project. |
| `project` | auto-detect | Solution or project path, relative to `working-directory`. |
| `configuration` | `Release` | Value passed to `--configuration`. |
| `build-args` | empty | Extra `dotnet build` arguments, one per line. Blank lines and surrounding whitespace are dropped. Lines are not split on spaces or shell-expanded. |

## Outputs

| Name | Description |
|---|---|
| `project` | Resolved solution or project path, relative to `working-directory`. |

## Permissions

```yaml
permissions:
  contents: read
```

## Forbidden build-args

Before building, the block checks every `build-args` line. Matching is case-insensitive. Any match fails the block, and the error names the rejected argument.

1. Switches `-f` and `--framework`.
2. Switches starting with `warnaserror`, `warnnotaserror`, `nowarn`, or `warnasmessage`, with a `-`, `--`, or `/` prefix. For example `-warnaserror-`, `/nowarn:CS0168`.
3. The MSBuild short forms `-err` and `-noerr`, with any of those prefixes.
4. Response files `@<path>`, because their contents cannot be checked.
5. `-p:`, `/p:`, `-property:`, `/property:`, or `--property:` when any `;`- or `,`-separated assignment names one of these properties. A bare `-p` or `--property` line is checked against the next line.
   - `TargetFramework`, `TargetFrameworks`
   - `TreatWarningsAsErrors`, `MSBuildTreatWarningsAsErrors`, `CodeAnalysisTreatWarningsAsErrors`
   - `WarningsAsErrors`, `WarningsNotAsErrors`, `WarningsAsMessages`, `MSBuildWarningsAsMessages`, `NoWarn`, `WarningLevel`
   - `NuGetAudit`, `NuGetAuditMode`, `NuGetAuditLevel`

Other properties are allowed, for example `-p:Version=1.2.3` and `-p:ContinuousIntegrationBuild=true`.

## Checkout

The block does not check out code. Run `actions/checkout` first. No special options are needed.

## Example

```yaml
steps:
  - uses: actions/checkout@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
  - uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
  - id: build
    uses: Pernix-Labs/pernix-ci/actions/dotnet-build@<sha> # vX.Y.Z
    with:
      build-args: |
        -p:Version=1.2.3
        -p:ContinuousIntegrationBuild=true
  - run: echo "Built ${{ steps.build.outputs.project }}"
```
