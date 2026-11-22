# nuget-push

Pushes `.nupkg` files to nuget.org with [Trusted Publishing](https://learn.microsoft.com/nuget/nuget-org/trusted-publishing). `NuGet/login` exchanges the job's GitHub OIDC token for a short-lived API key. There is no API key input, and no long-lived key is ever stored or used.

## Why a composite action, not a reusable workflow

This block is a composite action. It runs inside the caller's job. It is NOT a reusable workflow, and must not be wrapped in one.

The nuget.org Trusted Publishing policy matches claims in the OIDC token: the caller repository, the caller's workflow file (`cd.yml`), and the job's environment (`release`). A composite action keeps those claims pointing at the caller's `cd.yml` job. A reusable workflow would run as a separate job with its own workflow file and environment, and the token would no longer match the policy.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `packages` | yes | | Glob or newline list of globs/paths. Globs use bash `globstar` (`**`). Only `.nupkg` files are kept. Zero matches fails. |
| `user` | unless `dry-run` | | nuget.org profile name (user or organization) that owns the Trusted Publishing policy. Passed to `NuGet/login`. |
| `skip-duplicate` | no | `true` | Passes `--skip-duplicate`, so an already published version does not fail the step. |
| `dry-run` | no | `false` | Skips `NuGet/login` and pushes to `local-feed-dir`. Never contacts nuget.org. |
| `local-feed-dir` | no | `$RUNNER_TEMP/nuget-local-feed` | Local folder feed used by `dry-run`. Created if missing. |

There is no API key input.

## Outputs

| Name | Description |
|---|---|
| `pushed-count` | Number of `.nupkg` files pushed successfully, including skipped duplicates. |

## Permissions

Real push, in the caller job:

```yaml
environment: release
permissions:
  id-token: write
  contents: read
```

`dry-run: true` needs neither `id-token: write` nor an environment.

## Prerequisites

- The caller job must set up the .NET SDK, e.g. with `actions/setup-dotnet`.
- A nuget.org Trusted Publishing policy owned by `user`, with repository owner, repository, workflow file `cd.yml` and environment `release` matching the caller. Policy setup is a nuget.org admin action.

## Behavior

1. `nuget-push.sh resolve` expands `packages` with `globstar` and `nullglob`, keeps existing `.nupkg` files (`.snupkg` excluded), dedupes, and fails on zero matches. Fails if `user` is empty and `dry-run` is not `true`.
2. `NuGet/login` (skipped in dry-run) returns a short-lived key, masked by the action.
3. `nuget-push.sh push` runs per package:
   - Real: `dotnet nuget push <pkg> --source https://api.nuget.org/v3/index.json --api-key "$NUGET_API_KEY" [--skip-duplicate]`. `dotnet` pushes an adjacent `.snupkg` automatically.
   - Dry-run: `dotnet nuget push <pkg> --source <local-feed-dir> [--skip-duplicate]`, no key.

The key is passed only through the step's env. It is never echoed, written to a file, or set as an output. The script never uses `set -x`.

Local folder feeds ignore `--skip-duplicate` (`dotnet` prints a warning) and overwrite an existing version, so dry-run re-pushes always succeed.

## Example

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@<sha> # vX.Y.Z
      - uses: actions/setup-dotnet@<sha> # vX.Y.Z
        with:
          dotnet-version: 8.0.x
      - id: pack
        uses: pernix-labs/pernix-ci/actions/nuget-pack@<sha>
        with:
          projects: src/My.Lib/My.Lib.csproj
          version: 1.2.3
      - uses: pernix-labs/pernix-ci/actions/nuget-push@<sha>
        with:
          packages: ${{ steps.pack.outputs.packages }}
          user: pernix-labs
```

This job must live in the caller repository's `.github/workflows/cd.yml`, the file named in the policy.

## Troubleshooting

`NuGet/login` fails or nuget.org rejects the key when an OIDC claim does not match the policy. Check each policy field against the caller:

| Policy field | Must equal |
|---|---|
| Repository owner | Caller repository owner, e.g. `pernix-labs` |
| Repository | Caller repository name |
| Workflow file | `cd.yml`, the file containing the job that calls this action. Not a reusable workflow file. |
| Environment | `release`, set as `environment: release` on that job |

Also check:

- The job has `permissions: id-token: write`. Without it no OIDC token exists.
- `user` is the nuget.org profile that owns the policy.
- The package ID is owned by `user` on nuget.org, or does not exist yet.

Never fall back to an API key secret. Fix the policy or the caller job instead.

## Manual verification

The self-test runs dry-run only and never contacts nuget.org. The real path is first exercised by a caller's `cd.yml`:

1. Policy exists with the fields above.
2. Caller job has `environment: release` and `id-token: write`.
3. Run logs show `NuGet/login` succeeded and `dotnet nuget push` reported the package pushed or skipped.
4. `pushed-count` equals the number of packages.
5. No API key appears in logs.
