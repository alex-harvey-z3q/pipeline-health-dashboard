# Pipeline Health Dashboard

A lightweight, server-side Azure DevOps dashboard for shared build-agent and
pipeline-template health. It is deliberately an observer: it does not deploy
agents, trigger smoke tests, or change pull requests.

## Landing View

- One health record for each configured repository
- The latest associated build for `refs/heads/main`
- Main-branch run status, start and completion times, test totals, and a link
  to Azure DevOps
- The runtime agent pool reported for the selected build

The dashboard reports Azure DevOps and build-runtime state only. It does not
maintain a separate mapping for images, deployments, or release traceability.

Repository health is intentionally concise:

- `Healthy`: the latest main-branch run completed successfully.
- `Failing`: the latest main-branch run completed with an unsuccessful result.
- `Running`: the latest main-branch run is in progress.
- `Unknown`: no associated main-branch run is available, or Azure DevOps did
  not return usable run data.

Smoke-test and PR-validation details remain available in their secondary
dashboard sections. They do not contribute separate rows to the landing view.

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
pair is its stable identity:

- `image-build`
- `deployment`
- `smoke-test`
- `pr-validation`
- `pipeline`

Set `repository` on every pipeline that should contribute to main-branch
repository health. It must match a repository declared in the same project.
Pipelines without a repository association are not used for the landing view.
The dashboard queries the Azure DevOps Build API with `branchName` set to
`refs/heads/main`, so feature-branch and PR-validation builds are not fetched
for repository health.

`pr-validation` entries also use `repository` to associate validation builds
with active pull requests. They remain in the PR Validation section and are
queried using Azure DevOps's `refs/pull/<PR ID>/merge` ref.

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
normalisation, main-branch filtering, repository association, health-state
calculation, PR merge-ref association, runtime pool discovery, and partial API
failure isolation.

## Known Gaps

- Real pipeline definition IDs still need to be supplied in `config.yml`.
- Azure DevOps exposes a reported build queue/pool, but does not reliably expose
  image-to-deployment relationships. Image and deployment traceability is not
  implemented until it can be derived automatically from runtime data.
- Container orchestration, ingress, and Kubernetes identity integration are
  intentionally deferred until their target environment and access requirements
  are known.
