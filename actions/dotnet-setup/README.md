# dotnet-setup

Installs the caller's .NET SDK with `actions/setup-dotnet` (SHA-pinned) and exposes the resolved SDK version. Use it before `dotnet-restore`, `dotnet-build`, and `dotnet-test` so every step runs on the same SDK.

The SDK comes from `global.json` and from `dotnet-version`. Both may be set: `global.json` picks the SDK, and `dotnet-version` adds extra channels, for example the `8.0.x` runtime that `net8.0` test projects need. When no `global.json` exists and `dotnet-version` is empty, the block fails and names both inputs.

The block also writes `DOTNET_NOLOGO=1` and `DOTNET_CLI_TELEMETRY_OPTOUT=1` to `GITHUB_ENV` for later steps.

## Inputs

| Name | Default | Description |
|---|---|---|
| `working-directory` | `.` | Directory whose `global.json` pins the SDK and where `dotnet --version` resolves. |
| `global-json-file` | `<working-directory>/global.json` | Path to `global.json`, relative to the repo root. When set explicitly, the file must exist. |
| `dotnet-version` | empty | Extra SDK versions or channels, one per line (for example `8.0.x`). Required when no `global.json` exists. |

## Outputs

| Name | Description |
|---|---|
| `dotnet-version` | SDK version printed by `dotnet --version` in `working-directory`. |

## Permissions

```yaml
permissions:
  contents: read
```

## Checkout

The block does not check out code. Run `actions/checkout` first. No special options are needed.

## Example

`global.json` pins the .NET 10 SDK. `8.0.x` adds the .NET 8 runtime for `net8.0` test projects.

```yaml
steps:
  - uses: actions/checkout@<sha> # vX.Y.Z
  - id: setup
    uses: Pernix-Labs/pernix-ci/actions/dotnet-setup@<sha> # vX.Y.Z
    with:
      dotnet-version: 8.0.x
  - run: echo "SDK ${{ steps.setup.outputs.dotnet-version }}"
```
