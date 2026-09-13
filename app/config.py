"""Configuration loading for the Pipeline Health Dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.models import DeploymentProvenance, ImageBuildRef, PipelineSpec, RepositorySpec, RunProvenance


VALID_ROLES = {"image-build", "deployment", "smoke-test", "pr-validation", "pipeline"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    repositories: tuple[RepositorySpec, ...]


@dataclass(frozen=True)
class DashboardConfig:
    organization_url: str
    projects: tuple[ProjectConfig, ...]
    pipelines: tuple[PipelineSpec, ...]
    deployments: tuple[DeploymentProvenance, ...]
    run_provenance: tuple[RunProvenance, ...]


def _required(mapping: dict[str, Any], field_name: str, context: str) -> Any:
    value = mapping.get(field_name)
    if value in (None, ""):
        raise ConfigError(f"{context} requires {field_name!r}.")
    return value


def _image_build(value: dict[str, Any] | None, context: str) -> ImageBuildRef | None:
    if value is None:
        return None
    return ImageBuildRef(
        project=str(_required(value, "project", context)),
        pipeline_definition_id=int(_required(value, "pipeline_definition_id", context)),
        run_id=int(_required(value, "run_id", context)),
        version=value.get("version"),
    )


def load_config(path: Path) -> DashboardConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"Could not load configuration {path}: {error}") from error

    organization_url = str(_required(payload, "organization_url", "configuration")).rstrip("/")
    raw_projects = payload.get("projects", [])
    if not raw_projects:
        raise ConfigError("configuration requires at least one project.")

    projects: list[ProjectConfig] = []
    pipelines: list[PipelineSpec] = []
    pipeline_identities: set[tuple[str, int]] = set()
    for raw_project in raw_projects:
        project_name = str(_required(raw_project, "name", "project"))
        repositories = tuple(RepositorySpec(name=str(_required(repo, "name", f"project {project_name} repository"))) for repo in raw_project.get("repositories", []))
        projects.append(ProjectConfig(name=project_name, repositories=repositories))
        for raw_pipeline in raw_project.get("pipelines", []):
            pipeline_name = str(_required(raw_pipeline, "name", f"pipeline in {project_name}"))
            definition_id = int(_required(raw_pipeline, "definition_id", f"pipeline {pipeline_name}"))
            identity = (project_name, definition_id)
            if identity in pipeline_identities:
                raise ConfigError(f"pipeline {project_name!r} definition ID {definition_id} is duplicated.")
            role = str(_required(raw_pipeline, "role", f"pipeline {pipeline_name}"))
            if role not in VALID_ROLES:
                raise ConfigError(f"pipeline {pipeline_name!r} has invalid role {role!r}; expected one of {sorted(VALID_ROLES)}.")
            pipeline_identities.add(identity)
            pipelines.append(
                PipelineSpec(
                    project=project_name,
                    name=pipeline_name,
                    definition_id=definition_id,
                    role=role,
                    repository=raw_pipeline.get("repository"),
                    agent_pool=raw_pipeline.get("agent_pool"),
                )
            )

    deployments = tuple(
        DeploymentProvenance(
            deployment_id=str(_required(raw, "deployment_id", "deployment")),
            environment=str(_required(raw, "environment", "deployment")),
            agent_pool=raw.get("agent_pool"),
            image_version=raw.get("image_version"),
            deployed_at=raw.get("deployed_at"),
            image_build=_image_build(raw.get("image_build"), "deployment image_build"),
        )
        for raw in payload.get("provenance", {}).get("deployments", [])
    )
    run_provenance = tuple(
        RunProvenance(
            project=str(_required(raw, "project", "run provenance")),
            pipeline_definition_id=int(_required(raw, "pipeline_definition_id", "run provenance")),
            run_id=int(_required(raw, "run_id", "run provenance")),
            agent_pool=raw.get("agent_pool"),
            image_version=raw.get("image_version"),
            deployment_id=raw.get("deployment_id"),
            image_build=_image_build(raw.get("image_build"), "run provenance image_build"),
        )
        for raw in payload.get("provenance", {}).get("pipeline_runs", [])
    )
    return DashboardConfig(organization_url, tuple(projects), tuple(pipelines), deployments, run_provenance)
