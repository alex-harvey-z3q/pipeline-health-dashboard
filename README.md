# Pipeline Health Dashboard

A lightweight, server-side Azure DevOps dashboard for shared build-agent and
pipeline-template health. It is deliberately an observer: it does not deploy
agents, trigger smoke tests, or change pull requests.

## Repo CI Status

- One health record for each configured repository
- All discovered ordinary CI pipelines for the repository's Azure DevOps
  default branch
- Each contributing pipeline's latest run status, test totals, and Azure DevOps
  link
- The runtime agent pool reported for the selected build

The dashboard reports Azure DevOps and build-runtime state only. It does not
maintain a separate mapping for images, deployments, or release traceability.

Repository health is intentionally concise:

- `Healthy`: the latest default-branch run completed successfully.
- `Failing`: the latest default-branch run completed with an unsuccessful result.
- `Running`: the latest default-branch run is in progress.
- `Unknown`: Azure DevOps cannot supply a usable CI result.

The dashboard discovers each repository's `defaultBranch` from Azure DevOps;
it never assumes that the branch is named `main`. It also discovers Build
Definitions associated with the repository's Azure DevOps repository ID. It
shows distinct status messages for an unknown default branch, no discovered
default-branch CI pipeline, no builds on the discovered branch, and Azure
DevOps query failures.

Smoke tests appear in their own dashboard section. Pull-request validation is
not queried or shown on the central dashboard, keeping it focused on the
current operational state of each repository's default branch.

## Reusable Template PRs

For a repository such as `Templates` that contains reusable Azure DevOps
workflows, an optional operational section highlights open PRs that actually
modify files below configured template directories. It is separate from Repo
CI Status and is not a general pull-request browser.

Enable it on the relevant repository and list one or more repository-relative
directory prefixes to watch:

```yaml
repositories:
  - name: Templates
    reusable_template_prs:
      enabled: true
      max_age_days: 14
      path_prefixes:
        - /pipelines/templates/
```

The dashboard lists active PRs once, retains only those targeting the
repository's Azure DevOps default branch, and fetches changed paths from the
latest PR iteration. A PR appears when at least one changed path starts with a
configured prefix. Leading slashes are normalized before comparison, and the
prefixes are normalized to end in `/`, so matching is deterministic and does
not use PR titles, branches, filenames, or fuzzy rules. Multiple prefixes are
supported.

For each matching PR, the dashboard derives a compact affected-area summary:
the first directory under the longest matching prefix (for example `docker/`),
or the filename for a file directly below that prefix. Full matched paths are
available in the API response but are intentionally not expanded in the main
card.

PR age is the number of completed 24-hour periods since Azure DevOps recorded
its creation time. A PR is `Fresh` at or below `max_age_days`, and `Stale` when
it exceeds that threshold. The PR link always opens the Azure DevOps web UI.
Validation status is intentionally not shown here because the dashboard does
not currently have a reliable automatic PR-to-validation-run association.

## Local Run

Requires Python 3.11 or later.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp example-config.yml config.yml
# Edit config.yml and replace every REPLACE value.
export AZDO_PAT="your-pat"
make run
```

Open `http://127.0.0.1:8080`. The default loopback binding keeps the dashboard
private on a workstation. `AZDO_PERSONAL_ACCESS_TOKEN` is also supported for
users who prefer that environment variable name. The PAT is read only by the
backend and is never delivered to the browser.

The PAT needs Build read, Code read, and Test read scope, with access to every
configured project.

## Configuration

Copy `example-config.yml` to `config.yml`. Each pipeline requires a display
name, Azure DevOps definition ID, and a role. The `(project, definition_id)`
pair is its stable identity.

- `smoke-test`: post-deployment validation, shown in the Smoke Tests section.
- `deployment`: deployment or release pipeline, shown as a supporting pipeline.
- `image-build`: image creation pipeline, shown as a supporting pipeline.
- `pr-validation`: pull-request validation. It is retained as a configuration
  role for a future dedicated view, but is not queried or shown on the landing
  dashboard.

Ordinary repository CI is auto-discovered. The dashboard queries the Azure
DevOps repository API for `defaultBranch` and repository ID, asks the Build
Definitions API for definitions associated with that ID, then uses the exact
default-branch ref as the Build API `branchName`. It does not use pipeline-name
heuristics.

Pipelines configured with `deployment`, `smoke-test`, `pr-validation`, or
`image-build` are specialist pipelines. Their definition IDs are excluded from
Repo CI Status even when they run against the repository's default branch.

A repository can have multiple ordinary CI definitions. Repo CI Status is
`Healthy` only when all of their latest default-branch runs succeeded; it is
`Failing` when any failed or was cancelled, and `Running` when none failed and
at least one is in progress. Each contributing pipeline is shown in the row.

For an ambiguous repository, optionally narrow discovery with
`ci_definition_ids` on its repository configuration:

```yaml
repositories:
  - name: Templates
    ci_definition_ids: [1234, 5678]
```

The override selects from definitions Azure DevOps associates with that
repository; it does not fall back to name matching or unrelated definitions.

`pr-validation` entries may use `repository` to associate validation builds
with pull requests in a future dedicated view. When such a view links to a
pull request, it uses Azure DevOps's browser URL (`_links.web.href`) or builds
the standard Azure DevOps pull-request page URL; it never links to a REST JSON
endpoint.

### Runtime Agent Pools

Agent pools are properties of individual runs, not pipeline configuration. The
dashboard retrieves the latest build for each configured pipeline and reports
the pool recorded by Azure DevOps for that build. It uses the build's
`queue.pool.name` when available, otherwise its `queue.name`.

The API exposes this value as `agent_pool` on each run. The dashboard displays
`Unknown` when Azure DevOps has no pool information for that run. This makes a
pool change visible without requiring a configuration update.

## Testing

```sh
make check
```

Tests mock Azure DevOps responses and cover configuration parsing, build/test
normalisation, default-branch filtering, repository-ID definition discovery,
specialist-pipeline exclusion, aggregate health calculation, runtime pool
discovery, independent test-data failure handling,
pull-request browser-link construction, and partial API failure isolation.

## Known Gaps

- Real pipeline definition IDs still need to be supplied in `config.yml`.
- Azure DevOps exposes a reported build queue/pool, but does not reliably expose
  image-to-deployment relationships. Image and deployment traceability is not
  implemented until it can be derived automatically from runtime data.
- Container orchestration, ingress, and Kubernetes identity integration are
  intentionally deferred until their target environment and access requirements
  are known.
