# ADR 0003: Trivy CLI binary over `trivy-action`

## Status

Accepted (2026-11-22). Spec: [P5 ci-artifacts design](../specs/2026-11-22-ci-artifacts/design.md), D3, R4.

## Context

- `image-scan` must fail on HIGH/CRITICAL vulnerabilities and on any secret, while still writing reports and an optional SARIF upload first.
- Secret findings must not leak secret material into JSON, SARIF or the step summary.
- Security NFR: third-party actions pinned by sha, tool binaries pinned by version and SHA-256.
- `aquasecurity/trivy-action` pulls transitive actions and controls the output pipeline itself.

## Decision

`image-scan.sh` downloads the Trivy release tarball, verifies its pinned SHA-256 and runs one `trivy image --scanners vuln,secret --format json --exit-code 0`. `jq` strips secret `Match` and `Code`, `trivy convert` writes SARIF from the stripped JSON, and a later `enforce` step fails on the threshold.

## Consequences

- One Trivy run per scan. Reports and SARIF exist before enforcement fails.
- No transitive actions. Binary integrity checked by checksum.
- Trivy upgrades are manual: bump version and SHA-256 in `image-scan.sh`.
