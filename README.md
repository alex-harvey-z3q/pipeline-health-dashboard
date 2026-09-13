# Pipeline Health Dashboard

A lightweight, server-side Azure DevOps dashboard for shared build-agent and
pipeline-template health. It is deliberately an observer: it does not deploy
agents, trigger smoke tests, or change pull requests.

## What It Shows

- Overview of configured pipelines across Azure DevOps projects
- Latest run, branch, status/result, timestamps, agent pool, test totals, and
  Azure DevOps links
- Active pull requests in configured repositories and their validation runs,
  associated through the Azure DevOps PR merge ref

The dashboard reports Azure DevOps and build-runtime state only. It does not
maintain a separate mapping for images, deployments, or release traceability.

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

`pr-validation` entries can specify a repository. Active PRs are queried from
the repositories declared for a project; the validation is associated only when
Azure DevOps reports a build on `refs/pull/<PR ID>/merge`.

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
normalisation, PR merge-ref association, runtime pool discovery, and partial
API failure isolation.

## Known Gaps

- Real pipeline definition IDs still need to be supplied in `config.yml`.
- Azure DevOps exposes a reported build queue/pool, but does not reliably expose
  image-to-deployment relationships. Image and deployment traceability is not
  implemented until it can be derived automatically from runtime data.
- Container orchestration, ingress, and Kubernetes identity integration are
  intentionally deferred until their target environment and access requirements
  are known.
