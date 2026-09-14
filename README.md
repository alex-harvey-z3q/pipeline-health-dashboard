# Pipeline Health Dashboard

A lightweight, server-side Azure DevOps dashboard for shared build-agent and
pipeline-template health. It is deliberately an observer: it does not deploy
agents, trigger smoke tests, or change pull requests.

## Repo CI Status

- One health record for each configured repository
- The latest associated build for the repository's Azure DevOps default branch
- Default-branch run status, start and completion times, test totals, and a link
  to Azure DevOps
- The runtime agent pool reported for the selected build

The dashboard reports Azure DevOps and build-runtime state only. It does not
maintain a separate mapping for images, deployments, or release traceability.

Repository health is intentionally concise:

- `Healthy`: the latest default-branch run completed successfully.
- `Failing`: the latest default-branch run completed with an unsuccessful result.
- `Running`: the latest default-branch run is in progress.
- `Unknown`: Azure DevOps cannot supply a usable CI result.

The dashboard discovers each repository's `defaultBranch` from Azure DevOps;
it never assumes that the branch is named `main`. It shows distinct status
messages for no configured CI pipeline, an unknown default branch, no builds
on the discovered branch, and Azure DevOps query failures.

Smoke tests appear in their own dashboard section. Pull-request validation is
not queried or shown on the central dashboard, keeping it focused on the
current operational state of each repository's default branch.

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

- `pipeline`: normal repository CI. This is the only role used to determine
  central repository health on the Azure DevOps default branch.
- `smoke-test`: post-deployment validation, shown in the Smoke Tests section.
- `deployment`: deployment or release pipeline, shown as a supporting pipeline.
- `image-build`: image creation pipeline, shown as a supporting pipeline.
- `pr-validation`: pull-request validation. It is retained as a configuration
  role for a future dedicated view, but is not queried or shown on the landing
  dashboard.

Set `repository` on every pipeline that should contribute to default-branch
repository health. It must match a repository declared in the same project.
Each monitored repository needs at least one associated `role: pipeline` entry
to have meaningful landing-page health; otherwise it is shown as `Unknown`.
The dashboard queries the Azure DevOps repository API for `defaultBranch`, then
uses that exact ref as the Build API `branchName`. Feature-branch,
PR-validation, smoke-test, deployment, and image-build runs cannot determine
repository health.

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
normalisation, default-branch filtering, repository association, health-state
calculation, runtime pool discovery, independent test-data failure handling,
pull-request browser-link construction, and partial API failure isolation.

## Known Gaps

- Real pipeline definition IDs still need to be supplied in `config.yml`.
- Azure DevOps exposes a reported build queue/pool, but does not reliably expose
  image-to-deployment relationships. Image and deployment traceability is not
  implemented until it can be derived automatically from runtime data.
- Container orchestration, ingress, and Kubernetes identity integration are
  intentionally deferred until their target environment and access requirements
  are known.
