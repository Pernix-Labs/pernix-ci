# dotnet-unit-solution

Writes one `.slnx` holding exactly a release unit's projects, so blocks that take a single `project` input (`dotnet-restore`, `nuget-vulnerability-gate`, `nuget-deprecation-report`, `dotnet-build`, `dotnet-test`) gate only that unit. Run it after `dotnet-setup`. Feed `projects` from the `projects-list` field of a `release-units` element.

The block runs, in `working-directory`:

```sh
dotnet new sln --format slnx --name <name> --output .pernix-ci-units
dotnet sln .pernix-ci-units/<name>.slnx add <projects...>
```

It fails when `.pernix-ci-units/<name>.slnx` already exists, when a listed project file is missing, when `name` is invalid, or when the SDK is older than 9.0.200 (the first SDK that writes `.slnx`). The generated file is not committed. Add `.pernix-ci-units/` to `.gitignore` if you run the block locally.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `projects` | yes | | Newline-separated project paths, relative to `working-directory`. Blank lines and surrounding whitespace are ignored. |
| `name` | yes | | Unit name, `^[a-z0-9][a-z0-9-]*$`. Names the output file. |
| `working-directory` | no | `.` | Mono-repo root. Project paths and the output path are relative to it. |

## Outputs

| Name | Description |
|---|---|
| `solution` | Generated solution path, relative to `working-directory`: `.pernix-ci-units/<name>.slnx`. |

## Usage

```yaml
- uses: Pernix-Labs/pernix-ci/actions/dotnet-unit-solution@<sha> # vX.Y.Z
  id: solution
  with:
    name: ${{ matrix.unit.name }}
    projects: ${{ matrix.unit.projects-list }}
- uses: Pernix-Labs/pernix-ci/actions/dotnet-restore@<sha> # vX.Y.Z
  with:
    project: ${{ steps.solution.outputs.solution }}
```

## Permissions

```yaml
permissions:
  contents: read
```
