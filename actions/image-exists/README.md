# image-exists

Reports whether `<image>:<tag>` exists in GHCR. Uses the OCI Distribution API (`HEAD` on the manifest), so no layers are pulled.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `image` | yes | | Full image name without tag, e.g. `ghcr.io/pernix-labs/my-svc`. Must match `^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$`. |
| `tag` | yes | | Tag to check. Must match OCI tag grammar `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`. |
| `registry-token` | no | `${{ github.token }}` | Token for GHCR and the GitHub Packages API. |
| `registry-username` | no | `${{ github.actor }}` | Username for GHCR token exchange. |

Invalid inputs fail before any network call.

## Outputs

| Name | Description |
|---|---|
| `exists` | `true` or `false`. |
| `digest` | `sha256:...` when `exists=true`, else empty. |

## Permissions

```yaml
permissions:
  packages: read
```

`packages: read` also covers the Packages API fallback below.

## Behavior

1. Exchanges `registry-token` for a pull-scoped bearer token (credentials sent to `curl` on stdin, bearer masked).
2. Sends `HEAD /v2/<path>/manifests/<tag>` accepting OCI index, OCI manifest, Docker manifest list and Docker manifest v2.
3. `200` sets `exists=true` and `digest` from `Docker-Content-Digest`. `404` sets `exists=false`.
4. `403` from the token exchange or the manifest `HEAD` only (GHCR can answer `403` for a package that was never created): resolves the owner as org or user (`GET /users/{owner}` `.type`), then calls `GET /orgs|users/{owner}/packages/container/{name}` with the same token.
   - API `404` sets `exists=false` with empty `digest`.
   - API `200` fails: the package exists but the token lacks access.
   - Any other API status fails.
5. `429` and `5xx` are retried once after 5 seconds, then fail.
6. Every other status (including `401`) fails. The block never reports `false` for an auth, rate-limit or server error outside the `403` rule above.

## Example

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      packages: read
    steps:
      - id: exists
        uses: Pernix-Labs/pernix-ci/actions/image-exists@<commit-sha> # vX.Y.Z
        with:
          image: ghcr.io/pernix-labs/my-svc
          tag: sha-${{ github.sha }}
      - if: steps.exists.outputs.exists == 'true'
        env:
          DIGEST: ${{ steps.exists.outputs.digest }}
        run: echo "Image already built at ${DIGEST}"
```
