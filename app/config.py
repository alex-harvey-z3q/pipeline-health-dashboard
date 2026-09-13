"""Configuration loading for the Pipeline Health Dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.models import PipelineSpec, RepositorySpec


VALID_ROLES = {"image-build", "deployment", "smoke-test", "pr-validation", "pipeline"}
PIPELINE_FIELDS = {"name", "definition_id", "role", "repository"}
CONFIGURATION_FIELDS = {"organization_url", "projects"}


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


def _required(mapping: dict[str, Any], field_name: str, context: str) -> Any:
    value = mapping.get(field_name)
    if value in (None, ""):
        raise ConfigError(f"{context} requires {field_name!r}.")
    return value


def load_config(path: Path) -> DashboardConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"Could not load configuration {path}: {error}") from error

    unexpected_fields = set(payload) - CONFIGURATION_FIELDS
    if unexpected_fields:
        raise ConfigError(f"configuration has unsupported fields: {sorted(unexpected_fields)}.")

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
        repository_names = {repository.name for repository in repositories}
        projects.append(ProjectConfig(name=project_name, repositories=repositories))
        for raw_pipeline in raw_project.get("pipelines", []):
            unexpected_fields = set(raw_pipeline) - PIPELINE_FIELDS
            if unexpected_fields:
                raise ConfigError(
                    f"pipeline in {project_name} has unsupported fields: {sorted(unexpected_fields)}."
                )
            pipeline_name = str(_required(raw_pipeline, "name", f"pipeline in {project_name}"))
            definition_id = int(_required(raw_pipeline, "definition_id", f"pipeline {pipeline_name}"))
            identity = (project_name, definition_id)
            if identity in pipeline_identities:
                raise ConfigError(f"pipeline {project_name!r} definition ID {definition_id} is duplicated.")
            role = str(_required(raw_pipeline, "role", f"pipeline {pipeline_name}"))
            if role not in VALID_ROLES:
                raise ConfigError(f"pipeline {pipeline_name!r} has invalid role {role!r}; expected one of {sorted(VALID_ROLES)}.")
            repository = raw_pipeline.get("repository")
            if repository is not None and repository not in repository_names:
                raise ConfigError(
                    f"pipeline {pipeline_name!r} references repository {repository!r}, which is not configured for project {project_name!r}."
                )
            pipeline_identities.add(identity)
            pipelines.append(
                PipelineSpec(
                    project=project_name,
                    name=pipeline_name,
                    definition_id=definition_id,
                    role=role,
                    repository=repository,
                )
            )

    return DashboardConfig(organization_url, tuple(projects), tuple(pipelines))
