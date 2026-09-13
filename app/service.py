"""Dashboard collection service with per-source failure isolation."""

from __future__ import annotations

import concurrent.futures
from typing import Any

from app.azdo.builds import execution_pool_name, latest_build
from app.azdo.client import AzureDevOpsClient, AzureDevOpsError
from app.azdo.pull_requests import active_pull_requests, validation_branch
from app.azdo.tests import test_summary
from app.config import DashboardConfig
from app.models import PipelineHealth, PipelineSpec, PullRequestHealth, RepositoryHealth


MAIN_BRANCH = "refs/heads/main"


def pipeline_health(client: AzureDevOpsClient, pipeline: PipelineSpec, branch: str | None = None) -> PipelineHealth:
    try:
        build = latest_build(client, pipeline.project, pipeline.definition_id, branch)
        if not build:
            return PipelineHealth(pipeline=pipeline)
        return PipelineHealth(
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
            tests=test_summary(client, pipeline.project, build["uri"]),
        )
    except (AzureDevOpsError, KeyError, TypeError) as error:
        return PipelineHealth(pipeline=pipeline, status="error", error=str(error))


def _collect_pr(client: AzureDevOpsClient, project: str, repository: str, pipeline_specs: tuple[PipelineSpec, ...]) -> list[PullRequestHealth]:
    try:
        pull_requests = active_pull_requests(client, project, repository)
    except AzureDevOpsError as error:
        return [PullRequestHealth(project, repository, 0, "Unable to query pull requests", "", "", None, error=str(error))]

    items: list[PullRequestHealth] = []
    for pr in pull_requests:
        pr_id = int(pr["pullRequestId"])
        validations = [pipeline_health(client, pipeline, validation_branch(pr_id)) for pipeline in pipeline_specs]
        items.append(PullRequestHealth(project, repository, pr_id, pr.get("title", "Untitled pull request"), pr.get("sourceRefName", ""), pr.get("targetRefName", ""), pr.get("url"), validations))
    return items


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


def repository_healths(config: DashboardConfig, runs: list[PipelineHealth]) -> list[RepositoryHealth]:
    health: list[RepositoryHealth] = []
    for project in config.projects:
        for repository in project.repositories:
            associated_runs = [
                run
                for run in runs
                if run.run_id is not None
                and run.pipeline.project == project.name
                and run.pipeline.repository == repository.name
            ]
            latest_run = _most_recent_run(associated_runs)
            health.append(
                RepositoryHealth(
                    project=project.name,
                    repository=repository.name,
                    health=repository_health_state(latest_run),
                    latest_run=latest_run,
                )
            )
    return health


def collect_dashboard(config: DashboardConfig, client: AzureDevOpsClient) -> dict[str, Any]:
    main_branch_pipelines = tuple(
        pipeline
        for pipeline in config.pipelines
        if pipeline.repository is not None and pipeline.role != "pr-validation"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(main_branch_pipelines))) as executor:
        main_branch_runs = list(
            executor.map(lambda pipeline: pipeline_health(client, pipeline, MAIN_BRANCH), main_branch_pipelines)
        )
    repositories = repository_healths(config, main_branch_runs)

    smoke_pipelines = tuple(pipeline for pipeline in config.pipelines if pipeline.role == "smoke-test")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(smoke_pipelines))) as executor:
        smoke_test_items = list(executor.map(lambda pipeline: pipeline_health(client, pipeline), smoke_pipelines))

    targets = [(project.name, repository.name) for project in config.projects for repository in project.repositories]
    pull_request_items: list[PullRequestHealth] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(targets))) as executor:
        futures = [
            executor.submit(
                _collect_pr,
                client,
                project,
                repository,
                tuple(
                    pipeline
                    for pipeline in config.pipelines
                    if pipeline.role == "pr-validation"
                    and pipeline.project == project
                    and pipeline.repository == repository
                ),
            )
            for project, repository in targets
        ]
        for future in futures:
            pull_request_items.extend(future.result())

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
        "pull_requests": [item.as_dict() for item in pull_request_items],
    }
