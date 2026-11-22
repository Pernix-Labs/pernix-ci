# image-promote

Adds tags to an existing GHCR manifest, for example `sha-<sha>` → `1.2.3`, `v1.2.3`. The manifest bytes are copied registry-side with the OCI Distribution API, so every new tag has the same digest as the source. No rebuild, no layer transfer. Multi-arch indexes are copied as indexes.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `image` | yes | | Full image name without tag, e.g. `ghcr.io/pernix-labs/my-svc`. Must match `^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$`. |
| `source-tag` | yes | | Existing tag to promote, e.g. `sha-<40 hex>`. |
| `tags` | yes | | Newline list of target tags. Each must match OCI tag grammar `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`. Blank lines and duplicates are ignored. |
| `allow-overwrite` | no | `false` | `true` moves a target tag that already points to a different digest. |
| `registry-token` | no | `${{ github.token }}` | Token for GHCR. Needs `packages: write`. |
| `registry-username` | no | `${{ github.actor }}` | Username for GHCR token exchange. |

Invalid inputs fail before any network call.

## Outputs

| Name | Description |
|---|---|
| `digest` | Source manifest digest (`sha256:...`). Every target tag resolves to it. |
| `tags` | Newline list of target tags now at `digest`. |

## Permissions

```yaml
permissions:
  packages: write
```

## Behavior

1. Validates all inputs, including every target tag.
2. Exchanges `registry-token` for a `pull,push` bearer token (credentials sent to `curl` on stdin, bearer masked).
3. `GET`s the source manifest accepting OCI index, OCI manifest, Docker manifest list and Docker manifest v2, so the registry never down-converts an index. Keeps the raw bytes and `Content-Type`. The digest is the sha256 of those bytes and must match `Docker-Content-Digest`. A missing source fails with no tags created.
4. `HEAD`s every target before the first write:
   - Not found: will be created.
   - Same digest as source: skipped (re-runs are idempotent).
   - Different digest: fails listing every conflicting tag and digest, unless `allow-overwrite=true`. No tag is written when any target conflicts.
5. `PUT`s the identical bytes with the source `Content-Type` to each target tag.
6. `HEAD`s every target and fails if its digest differs from the source.

`429` and `5xx` responses are retried once after 5 seconds, then fail. Every other unexpected status fails.

## Example

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - id: promote
        uses: Pernix-Labs/pernix-ci/actions/image-promote@<commit-sha> # vX.Y.Z
        with:
          image: ghcr.io/pernix-labs/my-svc
          source-tag: sha-${{ github.sha }}
          tags: |
            1.2.3
            v1.2.3
      - env:
          DIGEST: ${{ steps.promote.outputs.digest }}
        run: echo "Released ${DIGEST}"
```
