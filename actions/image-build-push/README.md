# image-build-push

Builds a container image with `docker buildx` and pushes exactly one tag, `<image>:sha-<sha>`, to GHCR.

- OCI labels: `org.opencontainers.image.revision=<sha>`, `org.opencontainers.image.version=<version>`, `org.opencontainers.image.source=<source-url>`.
- Build args: `BUILD_VERSION=<version>` and `BUILD_COMMIT=<sha>`, appended after `build-args` so they always win.
- Empty `version` becomes `0.0.0-sha.<first 7 chars of sha>` for both the build arg and the label.
- Layer cache: GitHub Actions cache backend, scope = image path (e.g. `pernix-labs/foo`), toggled by `cache`.
- No version tags and no `latest`. Version tagging belongs to `image-promote`.
- `provenance: false`, `sbom: false`. Single-platform builds produce a single image manifest.

The push happens only after the full build succeeds, so a failed build or push leaves no partial tag.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `image` | yes | | Full image name without tag. Must be lowercase `ghcr.io/<owner>/<name>`. |
| `context` | no | `.` | Build context directory. |
| `dockerfile` | no | `<context>/Dockerfile` | Dockerfile path. |
| `sha` | no | `${{ github.sha }}` | Full 40-char lowercase commit sha. |
| `version` | no | empty | SemVer 2.0 version (e.g. `1.2.3`, `1.2.3-rc.1`). No `v` prefix. |
| `build-args` | no | empty | Extra build args, newline-separated `KEY=VALUE`. |
| `platforms` | no | `linux/amd64` | Comma-separated target platforms. |
| `cache` | no | `true` | `true` or `false`. |
| `source-url` | no | `${{ github.server_url }}/${{ github.repository }}` | Value of the `source` label. |
| `registry-token` | no | `${{ github.token }}` | Token for `ghcr.io` login. |
| `registry-username` | no | `${{ github.actor }}` | Username for `ghcr.io` login. |

Invalid inputs fail with `::error::` naming the input before any login or build.

> **Warning:** `build-args` must not carry secrets. Values pass through an unmasked step output and are baked into the image history. BuildKit secrets (`--secret`) are out of scope for this block.

## Outputs

| Name | Example |
|---|---|
| `image` | `ghcr.io/pernix-labs/foo` |
| `tag` | `sha-<40 hex>` |
| `digest` | `sha256:<64 hex>` |
| `ref` | `ghcr.io/pernix-labs/foo@sha256:<64 hex>` |

## Permissions

```yaml
permissions:
  contents: read
  packages: write
```

## Docker credentials

The block runs `docker login ghcr.io` with `registry-token` via `--password-stdin`. Docker stores the credentials in `~/.docker/config.json`, and they stay there for the rest of the caller job. Later steps in the same job can pull and push `ghcr.io` with that token. This is accepted because runners are ephemeral and the caller job already holds the token. Run untrusted steps in a separate job if this matters.

## Example

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0

      - id: image
        uses: Pernix-Labs/pernix-ci/actions/image-build-push@<commit-sha> # vX.Y.Z
        with:
          image: ghcr.io/pernix-labs/my-service
          context: .
          dockerfile: src/MyService/Dockerfile
          build-args: |
            CONFIGURATION=Release

      - run: echo "Pushed $IMAGE_REF"
        env:
          IMAGE_REF: ${{ steps.image.outputs.ref }}
```
