"""Dashboard collection service with per-source failure isolation."""

from __future__ import annotations

import concurrent.futures
from typing import Any

from app.azdo.builds import execution_pool_name, latest_build
from app.azdo.client import AzureDevOpsClient, AzureDevOpsError
from app.azdo.definitions import repository_build_definitions
from app.azdo.repositories import get_repository
from app.azdo.tests import test_summary
from app.config import DashboardConfig
from app.models import PipelineHealth, PipelineSpec, RepositoryHealth, TestSummary


def pipeline_health(client: AzureDevOpsClient, pipeline: PipelineSpec, branch: str | None = None) -> PipelineHealth:
    try:
        build = latest_build(client, pipeline.project, pipeline.definition_id, branch)
    except (AzureDevOpsError, KeyError, TypeError) as error:
        return PipelineHealth(pipeline=pipeline, status="error", error=str(error))
    if not build:
        return PipelineHealth(pipeline=pipeline)

    health = PipelineHealth(
        pipeline=pipeline,
        run_id=build.get("id"),
        run_number=build.get("buildNumber"),
        status=build.get("status", "unknown"),
        result=build.get("result"),
        branch=build.get("sourceBranch") or branch,
        started_at=build.get("startTime"),
        completed_at=build.get("finishTime"),
        run_url=build.get("_links", {}).get("web", {}).get("href"),
        agent_pool=execution_pool_name(build),
    )
    try:
        health.tests = test_summary(client, pipeline.project, build["uri"])
    except (AzureDevOpsError, KeyError, TypeError, ValueError) as error:
        health.tests = TestSummary(available=False, error=str(error))
    return health


def repository_health_state(run: PipelineHealth | None) -> str:
    if run is None or run.run_id is None or run.status == "error":
        return "unknown"
    if run.status in {"inProgress", "notStarted", "postponed"}:
        return "running"
    if run.status == "completed":
        return "healthy" if run.result == "succeeded" else "failing"
    return "unknown"


def _definition_pipeline(project: str, repository: str, definition: dict[str, Any]) -> PipelineSpec | None:
    try:
        definition_id = int(definition["id"])
    except (KeyError, TypeError, ValueError):
        return None
    return PipelineSpec(
        project=project,
        name=str(definition.get("name") or f"Build definition {definition_id}"),
        definition_id=definition_id,
        role="pipeline",
        repository=repository,
    )


def _aggregate_repository_health(runs: list[PipelineHealth]) -> str:
    states = [repository_health_state(run) for run in runs]
    if "failing" in states:
        return "failing"
    if "running" in states:
        return "running"
    if "unknown" in states:
        return "unknown"
    return "healthy"


def repository_health(
    client: AzureDevOpsClient,
    project: str,
    repository_spec: Any,
    specialist_definition_ids: frozenset[int],
) -> RepositoryHealth:
    """Collect CI health for one repository's Azure DevOps default branch."""
    repository = repository_spec.name
    try:
        metadata = get_repository(client, project, repository)
    except AzureDevOpsError as error:
        return RepositoryHealth(
            project=project,
            repository=repository,
            status_reason="Unable to query Azure DevOps",
            error=str(error),
        )

    default_branch = metadata.get("defaultBranch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        return RepositoryHealth(
            project=project,
            repository=repository,
            status_reason="Default branch unknown",
        )

    repository_id = metadata.get("id")
    if not isinstance(repository_id, str) or not repository_id.strip():
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason="Unable to query Azure DevOps",
            error="Azure DevOps did not provide a repository ID for CI discovery.",
        )

    try:
        definitions = repository_build_definitions(client, project, repository_id)
    except AzureDevOpsError as error:
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason="Unable to query Azure DevOps",
            error=str(error),
        )

    candidates = [
        pipeline
        for definition in definitions
        if (pipeline := _definition_pipeline(project, repository, definition)) is not None
        and pipeline.definition_id not in specialist_definition_ids
    ]
    if repository_spec.ci_definition_ids:
        selected_ids = set(repository_spec.ci_definition_ids)
        candidates = [pipeline for pipeline in candidates if pipeline.definition_id in selected_ids]

    if not candidates:
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason="No default-branch CI pipeline discovered",
        )

    runs = [pipeline_health(client, pipeline, default_branch) for pipeline in candidates]
    errors = [run.error for run in runs if run.error]
    actual_runs = [run for run in runs if run.run_id is not None]
    if not actual_runs:
        if errors:
            return RepositoryHealth(
                project=project,
                repository=repository,
                default_branch=default_branch,
                status_reason="Unable to query Azure DevOps",
                error="; ".join(errors),
                ci_runs=runs,
            )
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason=f"No builds found on {default_branch.removeprefix('refs/heads/')}",
            ci_runs=runs,
        )

    aggregate_state = _aggregate_repository_health(runs)
    return RepositoryHealth(
        project=project,
        repository=repository,
        default_branch=default_branch,
        health=aggregate_state,
        status_reason="Unable to query Azure DevOps" if errors and aggregate_state == "unknown" else None,
        error="; ".join(errors) if errors and aggregate_state == "unknown" else None,
        ci_runs=runs,
    )


def collect_dashboard(config: DashboardConfig, client: AzureDevOpsClient) -> dict[str, Any]:
    specialist_definition_ids_by_project = {
        project.name: frozenset(
            pipeline.definition_id for pipeline in config.pipelines if pipeline.project == project.name
        )
        for project in config.projects
    }
    repository_targets = [
        (project.name, repository, specialist_definition_ids_by_project[project.name])
        for project in config.projects
        for repository in project.repositories
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(repository_targets))) as executor:
        repositories = list(
            executor.map(
                lambda target: repository_health(client, *target),
                repository_targets,
            )
        )

    smoke_pipelines = tuple(pipeline for pipeline in config.pipelines if pipeline.role == "smoke-test")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(smoke_pipelines))) as executor:
        smoke_test_items = list(executor.map(lambda pipeline: pipeline_health(client, pipeline), smoke_pipelines))

    supporting_pipeline_specs = tuple(
        pipeline for pipeline in config.pipelines if pipeline.role in {"image-build", "deployment"}
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(supporting_pipeline_specs))) as executor:
        supporting_pipeline_items = list(
            executor.map(lambda pipeline: pipeline_health(client, pipeline), supporting_pipeline_specs)
        )

    return {
        "summary": {
            "repositories_monitored": len(repositories),
            "healthy": sum(item.health == "healthy" for item in repositories),
            "failing": sum(item.health == "failing" for item in repositories),
            "running": sum(item.health == "running" for item in repositories),
            "unknown": sum(item.health == "unknown" for item in repositories),
        },
        "repositories": [item.as_dict() for item in sorted(repositories, key=lambda item: (item.project, item.repository))],
        "smoke_tests": [item.as_dict() for item in sorted(smoke_test_items, key=lambda item: (item.pipeline.project, item.pipeline.name))],
        "supporting_pipelines": [item.as_dict() for item in sorted(supporting_pipeline_items, key=lambda item: (item.pipeline.project, item.pipeline.name))],
    }
