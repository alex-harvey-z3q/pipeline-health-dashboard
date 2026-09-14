"""Dashboard collection service with per-source failure isolation."""

from __future__ import annotations

import concurrent.futures
from typing import Any

from app.azdo.builds import execution_pool_name, latest_build
from app.azdo.client import AzureDevOpsClient, AzureDevOpsError
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


def _most_recent_run(runs: list[PipelineHealth]) -> PipelineHealth | None:
    if not runs:
        return None
    return max(runs, key=lambda run: (run.completed_at or run.started_at or "", run.run_id or 0))


def repository_health(
    client: AzureDevOpsClient,
    project: str,
    repository: str,
    ci_pipelines: tuple[PipelineSpec, ...],
) -> RepositoryHealth:
    """Collect CI health for one repository's Azure DevOps default branch."""
    try:
        metadata = get_repository(client, project, repository)
    except AzureDevOpsError as error:
        return RepositoryHealth(
            project=project,
            repository=repository,
            status_reason="Unable to query Azure DevOps",
            error=str(error),
            ci_pipeline=ci_pipelines[0] if ci_pipelines else None,
        )

    default_branch = metadata.get("defaultBranch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        return RepositoryHealth(
            project=project,
            repository=repository,
            status_reason="Default branch unknown",
            ci_pipeline=ci_pipelines[0] if ci_pipelines else None,
        )

    if not ci_pipelines:
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason="No CI pipeline configured",
        )

    runs = [pipeline_health(client, pipeline, default_branch) for pipeline in ci_pipelines]
    successful_queries = [run for run in runs if run.run_id is not None]
    latest_run = _most_recent_run(successful_queries)
    if latest_run:
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            health=repository_health_state(latest_run),
            ci_pipeline=latest_run.pipeline,
            latest_run=latest_run,
        )

    failed_query = next((run for run in runs if run.status == "error"), None)
    if failed_query:
        return RepositoryHealth(
            project=project,
            repository=repository,
            default_branch=default_branch,
            status_reason="Unable to query Azure DevOps",
            error=failed_query.error,
            ci_pipeline=failed_query.pipeline,
        )
    return RepositoryHealth(
        project=project,
        repository=repository,
        default_branch=default_branch,
        status_reason=f"No builds found on {default_branch.removeprefix('refs/heads/')}",
        ci_pipeline=ci_pipelines[0],
    )


def collect_dashboard(config: DashboardConfig, client: AzureDevOpsClient) -> dict[str, Any]:
    repository_targets = [
        (
            project.name,
            repository.name,
            tuple(
                pipeline
                for pipeline in config.pipelines
                if pipeline.role == "pipeline"
                and pipeline.project == project.name
                and pipeline.repository == repository.name
            ),
        )
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
