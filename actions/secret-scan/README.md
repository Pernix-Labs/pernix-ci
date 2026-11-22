# secret-scan

Scans git history for secrets with the [gitleaks](https://github.com/gitleaks/gitleaks) CLI. Fails on any finding.

- gitleaks 8.30.1, linux x64 release binary, verified against a pinned SHA-256 in `scan.sh`. No license key, no secret inputs.
- Runs with `--redact`. Logs, annotations and the job summary show rule ID, file, line, commit and fingerprint only, never the secret value.
- The JSON report stays in `$RUNNER_TEMP` and is not uploaded.

## Inputs

| Input | Default | Description |
|---|---|---|
| `scan-mode` | `auto` | `auto` scans the event commit range (see below). `full-history` scans all history. |
| `config-path` | empty | gitleaks config file, relative to `working-directory`. Empty uses `<working-directory>/.gitleaks.toml` when present, else the gitleaks default rules. |
| `working-directory` | `.` | Root of the git repository to scan. |

## Outputs

| Output | Description |
|---|---|
| `findings-count` | Number of findings. |

## Scanned range (`scan-mode: auto`)

| Event | Range |
|---|---|
| `pull_request`, `pull_request_target` | `pull_request.base.sha..pull_request.head.sha` |
| `merge_group` | `merge_group.base_sha..merge_group.head_sha` |
| `push`, new branch (`before` all-zero) | full history of `github.sha` |
| `push`, `before` present | `before..github.sha` |
| `push`, `before` missing (force push) | full history of `github.sha` |
| any other event | full history |

## Permissions

```yaml
permissions:
  contents: read
```

## Checkout requirement

The block does not check out code. Check out with full history:

```yaml
- uses: actions/checkout@<sha>
  with:
    fetch-depth: 0
```

On a shallow clone the block fails with `set actions/checkout fetch-depth: 0` when the commits for the selected range are missing, or when the range is a full history. It never scans a truncated history and passes.

## Allowlists

gitleaks applies these files from the root of `working-directory`:

- `.gitleaks.toml`: custom rules and allowlists. Override the location with `config-path`.
- `.gitleaksignore`: one finding fingerprint per line. Copy the fingerprint from the job summary table, format `<commit>:<file>:<rule-id>:<line>`.

Both files are read from the checked-out tree, so a pull request can change its own allowlist. Treat changes to `.gitleaks.toml` and `.gitleaksignore` as security-sensitive in review. Add CODEOWNERS entries for them in the caller repo.

## Example

```yaml
jobs:
  secret-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<sha>
        with:
          fetch-depth: 0
          persist-credentials: false
      - id: scan
        uses: Pernix-Labs/pernix-ci/actions/secret-scan@<sha|vX.Y.Z>
      - if: always()
        env:
          FINDINGS: ${{ steps.scan.outputs.findings-count }}
        run: echo "findings: $FINDINGS"
```
