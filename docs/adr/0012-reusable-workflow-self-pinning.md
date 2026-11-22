# ADR 0012: Reusable workflow self-pinning via `job.workflow_sha`

## Status

Accepted (2026-11-22). Spec: `docs/specs/2026-11-22-ci-release-flow`, D1, RK1.

## Context

- F3: GitHub `uses:` takes no expressions. A reusable workflow cannot statically name its own commit, and an external caller cannot reference a pernix-ci PR's own commit.
- R1 / Req 4.14: a reusable workflow must run blocks (`actions/<block>`) from the same pernix-ci commit as the reusable workflow itself.
- D1 proposed self-pinning via the `job.workflow_sha` job context (GitHub changelog 2026-09-03). RK1 required a real cross-repo run before any reusable workflow is written. IF the value was empty, absent or wrong THEN the design switches to a caller-passed `pernix-ci-ref` input.

## Decision

Mode `job-workflow-sha`. Every pernix-ci reusable-workflow job that uses blocks checks out `Pernix-Labs/pernix-ci` at `${{ job.workflow_sha }}` into `pernix-ci/` and calls blocks by local path `./pernix-ci/actions/<block>`. No `pernix-ci-ref` input exists.

## Evidence

Run: https://github.com/Pernix-Labs/pernix-outbox-relay/actions/runs/45067970650 (conclusion `success`, 2026-11-22).

Setup:

- `Pernix-Labs/pernix-ci` temp branch `probe/rk1-workflow-sha`, HEAD `7b9368eec335e3c5c6b615a566b5bf0884ce8dad`, holding reusable `.github/workflows/probe-workflow-sha.yml` (`on: workflow_call`).
- `Pernix-Labs/pernix-outbox-relay` temp branch `probe/rk1-workflow-sha`, HEAD `53538720b9383ae8faa3aef7f2f6a9e2cad2f18b`, caller triggered `on: push` to that branch with `uses: Pernix-Labs/pernix-ci/.github/workflows/probe-workflow-sha.yml@probe/rk1-workflow-sha`.

Observed values inside the called job:

| Context | Value |
|---|---|
| `job.workflow_sha` | `7b9368eec335e3c5c6b615a566b5bf0884ce8dad` (pernix-ci probe HEAD) |
| `job.workflow_ref` | `Pernix-Labs/pernix-ci/.github/workflows/probe-workflow-sha.yml@refs/heads/probe/rk1-workflow-sha` |
| `job.workflow_repository` | `Pernix-Labs/pernix-ci` |
| `github.workflow_sha` | `53538720b9383ae8faa3aef7f2f6a9e2cad2f18b` (caller commit) |
| `github.sha` | `53538720b9383ae8faa3aef7f2f6a9e2cad2f18b` (caller commit) |

`actions/checkout` with `repository: Pernix-Labs/pernix-ci`, `ref: ${{ job.workflow_sha }}`, `path: pernix-ci` succeeded. `git -C pernix-ci rev-parse HEAD` printed `7b9368eec335e3c5c6b615a566b5bf0884ce8dad` and `ls pernix-ci/actions` listed the blocks. Pass criteria met.

`github.workflow_sha` resolves to the caller's commit, not the called workflow's, so it cannot replace `job.workflow_sha`.

Both probe branches were deleted after the run. The probe had `contents: read` only and built no images, so no GHCR artifacts exist.

## Consequences

Every reusable-workflow job that uses blocks (tasks 8, 9) starts with these two steps, before any `./pernix-ci/actions/<block>` call:

```yaml
      - name: Guard pernix-ci self-pin
        env:
          PERNIX_CI_SHA: ${{ job.workflow_sha }}
        run: |
          if [ -z "${PERNIX_CI_SHA}" ]; then
            echo "::error::pernix-ci reusable workflows require github.com job.workflow_sha"
            exit 1
          fi
      - name: Checkout pernix-ci
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: Pernix-Labs/pernix-ci
          ref: ${{ job.workflow_sha }}
          path: pernix-ci
          persist-credentials: false
```

The guard fails closed where the context is empty (GHES, unsupported runner).

Per task:

- Task 8 (`ci.yml`) and task 9 (`cd.yml`, `image-retention.yml`): guard + checkout in every block-using job. No `pernix-ci-ref` input.
- Task 10 (templates): the `uses: Pernix-Labs/pernix-ci/.github/workflows/<wf>.yml@<ref>` line is the only pin. Templates pass no pernix-ci ref.
- Task 11 (self-tests): call the reusable workflows by local path. No ref input to pass. The probe covered the cross-repo call only. The same-repo `pull_request` case is confirmed by PR #3 (https://github.com/Pernix-Labs/pernix-ci/pull/3): `test-release-ci.yml` and `test-release-cd.yml` call the reusable workflows by local path, and the guard and checkout at `job.workflow_sha` passed on every run.

Rejected (D1):

- OIDC `job_workflow_sha` claim: needs `id-token: write`, violates Req 5.6.
- Caller-passed `pernix-ci-ref` input: duplicates the `uses:` ref and cannot be verified against it. Was the RK1 fallback, not needed.
- Literal pinned refs updated at release: cannot pin a PR's own commit (F3).
