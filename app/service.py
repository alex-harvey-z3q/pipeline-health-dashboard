"""Dashboard collection service with per-source failure isolation."""

from __future__ import annotations

import concurrent.futures
from dataclasses import asdict
from typing import Any

from app.azdo.builds import execution_pool_name, latest_build
from app.azdo.client import AzureDevOpsClient, AzureDevOpsError
from app.azdo.pull_requests import active_pull_requests, validation_branch
from app.azdo.tests import test_summary
from app.config import DashboardConfig
from app.correlation.provenance import enrich
from app.models import PipelineHealth, PipelineSpec, PullRequestHealth


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
            branch=build.get("sourceBranch"),
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


def collect_dashboard(config: DashboardConfig, client: AzureDevOpsClient) -> dict[str, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(config.pipelines))) as executor:
        pipeline_items = list(executor.map(lambda pipeline: pipeline_health(client, pipeline), config.pipelines))
    for item in pipeline_items:
        enrich(item, config.run_provenance)

    validation_pipelines = tuple(pipeline for pipeline in config.pipelines if pipeline.role == "pr-validation")
    targets = [(project.name, repository.name) for project in config.projects for repository in project.repositories]
    pull_request_items: list[PullRequestHealth] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(targets))) as executor:
        futures = [executor.submit(_collect_pr, client, project, repository, validation_pipelines) for project, repository in targets]
        for future in futures:
            pull_request_items.extend(future.result())

    failed = [item for item in pipeline_items if item.result in {"failed", "partiallySucceeded"}]
    smoke_failures = [item for item in failed if item.pipeline.role == "smoke-test"]
    pr_failures = [validation for pr in pull_request_items for validation in pr.validations if validation.result in {"failed", "partiallySucceeded"}]
    deployments = [asdict(deployment) for deployment in config.deployments]
    for deployment in deployments:
        deployment["smoke_tests"] = [
            item.as_dict() for item in pipeline_items if item.provenance and item.provenance.deployment_id == deployment["deployment_id"] and item.pipeline.role == "smoke-test"
        ]

    return {
        "summary": {
            "pipelines_monitored": len(pipeline_items),
            "succeeded": sum(item.result == "succeeded" for item in pipeline_items),
            "failed": len(failed),
            "running": sum(item.status in {"inProgress", "notStarted", "postponed"} for item in pipeline_items),
            "smoke_test_failures": len(smoke_failures),
            "pr_validation_failures": len(pr_failures),
        },
        "pipelines": [item.as_dict() for item in sorted(pipeline_items, key=lambda item: (item.pipeline.project, item.pipeline.name))],
        "deployments": deployments,
        "pull_requests": [item.as_dict() for item in pull_request_items],
    }
