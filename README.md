# Pipeline Health Dashboard

A lightweight, server-side Azure DevOps dashboard for shared build-agent and
pipeline-template health. It is deliberately an observer: it does not deploy
agents, trigger smoke tests, or change pull requests.

## What It Shows

- Overview of configured pipelines across Azure DevOps projects
- Latest run, branch, status/result, timestamps, agent pool, test totals, and
  Azure DevOps links
- Explicitly configured agent-image deployment provenance and associated smoke
  tests
- Active pull requests in configured template repositories and their validation
  runs, associated through the Azure DevOps PR merge ref

The initial configuration is set up for these project and repository names:

- `Shared Platform Services` / `agent-infrastructure`
- `Shared Pipeline Templates` / `Examples`, `TestConfig`

Pipeline definition IDs, pool names, and deployment metadata are always
configuration, never application constants.

## Provenance Rule

The dashboard will **not** attribute a pipeline failure to an image merely
because the timestamps are close. A run displays an image, deployment, or
originating image build only when an exact `provenance.pipeline_runs` entry
matches its project, pipeline definition ID, and run ID. This explicit metadata can later
be published by the deployment system, a pipeline task, or a separate trusted
metadata service.

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
compatibility with the earlier PoC. The PAT is read only by the backend and is
never delivered to the browser.

The PAT needs Build read, Code read, and Test read scope. Access to both
configured projects is required.

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

The optional `provenance` section supports trusted, exact metadata:

```yaml
pipeline_runs:
  - project: Shared Platform Services
    pipeline_definition_id: 1003
    run_id: 12346
    deployment_id: deployment-2026-09-13-01
    agent_pool: shared-linux-pool
    image_version: 2026.09.13.1
    image_build:
      project: Shared Platform Services
      pipeline_definition_id: 1001
      run_id: 12345
      version: 2026.09.13.1
```

No metadata source is imposed for the MVP. A future source may populate this
contract from a deployment record, pipeline variables, Azure DevOps build
properties, or a service that records the image/pool deployment event.

## Testing

```sh
make check
```

Tests mock Azure DevOps responses and cover configuration parsing, build/test
normalisation, PR merge-ref association, explicit provenance matching, and
partial API failure isolation.

## Known Gaps

- Real pipeline definition IDs, pool names, and deployment metadata still need
  to be supplied in `config.yml`.
- Azure DevOps exposes a reported build queue/pool, but does not reliably expose
  the immutable agent image used by a run. Image attribution therefore remains
  deliberately empty until exact provenance is provided.
- Container orchestration, ingress, and Kubernetes identity integration are
  intentionally deferred until their target environment and access requirements
  are known.
