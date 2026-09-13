"""Apply only explicit run-level provenance; never infer it from timing."""

from __future__ import annotations

from app.models import DeploymentProvenance, PipelineHealth, RunProvenance


def run_provenance_for(run: PipelineHealth, provenance: tuple[RunProvenance, ...]) -> RunProvenance | None:
    if run.run_id is None:
        return None
    for item in provenance:
        if item.project == run.pipeline.project and item.pipeline_key == run.pipeline.key and item.run_id == run.run_id:
            return item
    return None


def deployment_for(run: PipelineHealth, deployments: tuple[DeploymentProvenance, ...]) -> DeploymentProvenance | None:
    if not run.provenance or not run.provenance.deployment_id:
        return None
    return next((item for item in deployments if item.deployment_id == run.provenance.deployment_id), None)


def enrich(run: PipelineHealth, provenance: tuple[RunProvenance, ...]) -> PipelineHealth:
    run.provenance = run_provenance_for(run, provenance)
    return run
