# image-scan

Scans a GHCR image with Trivy. By default it pulls the pushed image from the registry (`image-source: remote`, `--image-src remote`). With `image-source: docker` it reads an image already in the runner's Docker daemon (`--image-src docker`) under the same `ghcr.io/...` ref, so an image can be scanned before it is pushed. One Trivy run covers both the `vuln` and `secret` scanners.

- Fails if any vulnerability has a severity in `fail-severities` (default `HIGH,CRITICAL`).
- Fails if any secret is found in image layers, regardless of `fail-severities`.
- Vulnerabilities below the threshold are reported only.
- Reports (SARIF, step summary) and the optional SARIF upload always complete before the block fails.
- Trivy errors (vulnerability DB download from both `ghcr.io/aquasecurity/trivy-db` and `public.ecr.aws/aquasecurity/trivy-db` failed, registry auth, image pull) fail the block. A scan never passes silently.

Secret values never reach the SARIF file, the summary, or the logs. The block deletes `Match`, `Code`, and `Layer.CreatedBy` from every secret finding before it builds any report. Reports keep only the rule ID, title, severity, and file path. The raw Trivy JSON is deleted after stripping.

Trivy `v0.76.2` is pinned in `image-scan.sh` by version and sha256. The block downloads the release tarball and verifies its checksum before running it. The vulnerability DB is cached with `actions/cache` at `~/.cache/trivy/db`, key `trivy-db-<UTC date>`.

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `image-ref` | yes | | Image with tag or digest. Must be lowercase `ghcr.io/<owner>/<name>:<tag>` or `ghcr.io/<owner>/<name>@sha256:<digest>`. |
| `image-source` | no | `remote` | `remote` pulls `image-ref` from `ghcr.io`. `docker` reads `image-ref` from the local Docker daemon and passes no registry credentials. Any other value fails before the scan. |
| `fail-severities` | no | `HIGH,CRITICAL` | Comma-separated severities that fail the block. Allowed: `UNKNOWN`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `ignore-file` | no | empty | Path to a `.trivyignore` file. |
| `ignore-unfixed` | no | `false` | `true` skips vulnerabilities without a fixed version. |
| `upload-sarif` | no | `false` | `true` uploads the SARIF file to code scanning. |
| `sarif-category` | no | `image-scan` | Code scanning category for the upload. |
| `registry-token` | no | `${{ github.token }}` | Token for pulling the image from `ghcr.io`. Passed to Trivy as `TRIVY_PASSWORD`. Unused with `image-source: docker`. |
| `registry-username` | no | `${{ github.actor }}` | Username for `ghcr.io`. Passed to Trivy as `TRIVY_USERNAME`. Unused with `image-source: docker`. |

Invalid inputs fail with `::error::` naming the input before Trivy is installed.

## Outputs

| Name | Example |
|---|---|
| `critical-count` | `0` |
| `high-count` | `2` |
| `medium-count` | `5` |
| `low-count` | `1` |
| `secret-count` | `0` |
| `sarif-file` | `/home/runner/work/_temp/image-scan/results.sarif` |
| `result` | `pass` or `fail` |

Outputs are set even when the block fails, so a caller step with `continue-on-error: true` can read them.

The step summary shows counts per severity, the secret count on its own line, the top 20 vulnerabilities (ID, package, severity, installed and fixed version), and up to 20 secrets (rule ID and file path only). The same summary is written next to the SARIF file as `summary.md`.

`sarif-file` and `summary.md` live in `$RUNNER_TEMP/image-scan/`. A second scan in the same job overwrites them.

## Permissions

```yaml
permissions:
  packages: read
```

With `image-source: docker` the block needs no `packages` permission.

With `upload-sarif: true`:

```yaml
permissions:
  packages: read
  security-events: write
```

## Example

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      packages: read
      security-events: write
    steps:
      - id: scan
        uses: Pernix-Labs/pernix-ci/actions/image-scan@<commit-sha> # vX.Y.Z
        with:
          image-ref: ghcr.io/pernix-labs/my-service@sha256:<digest>
          upload-sarif: "true"

      - if: always()
        run: echo "Scan result $RESULT (critical $CRITICAL, high $HIGH, secrets $SECRETS)"
        env:
          RESULT: ${{ steps.scan.outputs.result }}
          CRITICAL: ${{ steps.scan.outputs.critical-count }}
          HIGH: ${{ steps.scan.outputs.high-count }}
          SECRETS: ${{ steps.scan.outputs.secret-count }}
```
