# image-retention

Deletes expired versions of GHCR container packages so storage stays low. Each version is classified by its tags. The newest stable versions are kept, prerelease and sha-only versions expire by age. Run it on a schedule.

## Precondition: Admin on each package

The token must have Admin on every package in `packages`. With `GITHUB_TOKEN`, the caller repository has Admin by default on packages its own workflows first pushed. For any other package, grant it once:

1. Open the package settings page: `https://github.com/orgs/<owner>/packages/container/<pkg>/settings` (org) or `https://github.com/users/<owner>/packages/container/<pkg>/settings` (user).
2. Under **Manage Actions access**, click **Add repository** and select the caller repository.
3. Set its role to **Admin**.

Without Admin, the first `DELETE` returns `403` and the block fails with this message:

```text
Cannot delete versions of <pkg>: <repo> lacks Admin on the package. Open <settings URL> -> Manage Actions access -> grant <repo> Admin.
```

## Inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `packages` | yes | | Newline list of GHCR package names without owner or tag, e.g. `my-svc`. Blank lines and duplicates are ignored. |
| `owner` | no | `${{ github.repository_owner }}` | Package owner, org or user. |
| `max-age-days` | no | `14` | Delete sha-only (or untagged) versions older than this. |
| `prerelease-max-age-days` | no | `14` | Delete prerelease versions older than this. |
| `keep-versions` | no | `5` | Newest stable versions kept per package. Prereleases do not count toward it. |
| `stable-tag-pattern` | no | `^v?[0-9]+\.[0-9]+\.[0-9]+$` | Regex. Any matching tag makes the version stable. |
| `prerelease-tag-pattern` | no | `^v?[0-9]+\.[0-9]+\.[0-9]+-[0-9A-Za-z.-]+$` | Regex. Any matching tag makes a non-stable version prerelease. |
| `dry-run` | no | `false` | `true` lists planned deletions and deletes nothing. |
| `reference-time` | no | empty (now) | Time ages are measured from, ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ`. |
| `registry-token` | no | `${{ github.token }}` | Token for GHCR and the GitHub Packages API. Needs `packages: write` and Admin on each package. |
| `registry-username` | no | `${{ github.actor }}` | Username for GHCR token exchange. |

Invalid inputs fail before any network call.

`reference-time` exists for tests and backfills. The self-test seeds versions "now" and evaluates them at now+30d, so the age rules are checked without waiting 14 days. Leave it empty in scheduled runs.

## Outputs

| Name | Description |
|---|---|
| `deleted-count` | Versions deleted. With `dry-run=true`, versions planned for deletion. |
| `kept-count` | Versions kept. |
| `deleted-versions` | JSON array of `{package, id, tags}` for deleted (or planned) versions. |

On failure the outputs report progress up to the failing call.

## Permissions

```yaml
permissions:
  packages: write
```

## Behavior

1. Resolves the owner kind with `GET /users/<owner>` and uses `/orgs/<owner>` or `/users/<owner>` for all Packages API calls.
2. Lists all versions of each package (`gh api --paginate`).
3. Classifies each version on its tags. Stable if any tag matches `stable-tag-pattern`, else prerelease if any tag matches `prerelease-tag-pattern`, else sha-only (sha tags or untagged).
4. Marks deletions. Stable: everything beyond the newest `keep-versions` by `created_at`. Prerelease: older than `prerelease-max-age-days`. Sha-only: older than `max-age-days`. Age is `reference-time - created_at`.
5. Last-version guard: GitHub rejects deleting a package's last version. If every version is marked, the newest is kept with a notice.
6. Child protection: for every retained version (including one kept by the guard), `GET`s its manifest from the registry. If it is an index, every `manifests[].digest` (platform images, attestations) is kept too.
7. Unless `dry-run`, re-reads each marked version, re-classifies it, and skips it with a notice if its class changed since listing (for example promoted meanwhile). Then `DELETE`s it.
8. Writes a table per package to the step summary: result, class, tags, age, reason, version id.

A `403` at `DELETE` fails with the remediation message above. Any other API error fails. Both print the versions deleted so far and write the outputs. `429` and `5xx` responses are retried once after 5 seconds.

### Ordering uses `created_at`

`created_at` is when the manifest was first pushed, not when it was tagged. Promoting an old `sha-<sha>` image to `1.2.3` gives a stable version that sorts as old. Under keep-N it can be deleted before a stable version that was built later but released earlier.

## Example

```yaml
on:
  schedule:
    - cron: '17 3 * * *'

jobs:
  retention:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: pernix-labs/pernix-ci/actions/image-retention@<sha>
        with:
          packages: |
            my-svc
            my-worker
```
