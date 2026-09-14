"""Configuration loading for the Pipeline Health Dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.models import PipelineSpec, RepositorySpec, ReusableTemplate, ReusableTemplatePRConfig


VALID_ROLES = {"image-build", "deployment", "smoke-test", "pr-validation"}
PIPELINE_FIELDS = {"name", "definition_id", "role", "repository"}
REPOSITORY_FIELDS = {"name", "ci_definition_ids", "reusable_template_prs"}
REUSABLE_TEMPLATE_PRS_FIELDS = {"enabled", "max_age_days", "templates"}
REUSABLE_TEMPLATE_FIELDS = {"path", "name"}
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


def _reusable_template_pr_config(raw_config: Any, repository_name: str) -> ReusableTemplatePRConfig | None:
    if raw_config is None:
        return None
    if not isinstance(raw_config, dict):
        raise ConfigError(f"repository {repository_name!r} reusable_template_prs must be a mapping.")
    unexpected_fields = set(raw_config) - REUSABLE_TEMPLATE_PRS_FIELDS
    if unexpected_fields:
        raise ConfigError(
            f"repository {repository_name!r} reusable_template_prs has unsupported fields: {sorted(unexpected_fields)}."
        )
    enabled = raw_config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(f"repository {repository_name!r} reusable_template_prs enabled must be true or false.")
    max_age_days = raw_config.get("max_age_days", 14)
    if not isinstance(max_age_days, int) or max_age_days < 0:
        raise ConfigError(f"repository {repository_name!r} reusable_template_prs max_age_days must be a non-negative integer.")
    raw_templates = raw_config.get("templates", [])
    if not isinstance(raw_templates, list):
        raise ConfigError(f"repository {repository_name!r} reusable_template_prs templates must be a list.")
    templates: list[ReusableTemplate] = []
    for raw_template in raw_templates:
        if not isinstance(raw_template, dict):
            raise ConfigError(f"repository {repository_name!r} reusable template must be a mapping.")
        unexpected_fields = set(raw_template) - REUSABLE_TEMPLATE_FIELDS
        if unexpected_fields:
            raise ConfigError(
                f"repository {repository_name!r} reusable template has unsupported fields: {sorted(unexpected_fields)}."
            )
        path = str(_required(raw_template, "path", f"repository {repository_name} reusable template"))
        if not path.startswith("/"):
            raise ConfigError(f"repository {repository_name!r} reusable template path must start with '/'.")
        name = raw_template.get("name")
        templates.append(ReusableTemplate(path=path, name=str(name) if name is not None else None))
    if enabled and not templates:
        raise ConfigError(f"repository {repository_name!r} reusable_template_prs requires at least one template when enabled.")
    return ReusableTemplatePRConfig(enabled=enabled, max_age_days=max_age_days, templates=tuple(templates))


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
        repositories: list[RepositorySpec] = []
        for raw_repository in raw_project.get("repositories", []):
            unexpected_fields = set(raw_repository) - REPOSITORY_FIELDS
            if unexpected_fields:
                raise ConfigError(
                    f"repository in {project_name} has unsupported fields: {sorted(unexpected_fields)}."
                )
            repository_name = str(_required(raw_repository, "name", f"project {project_name} repository"))
            raw_definition_ids = raw_repository.get("ci_definition_ids", [])
            if not isinstance(raw_definition_ids, list):
                raise ConfigError(f"repository {repository_name!r} ci_definition_ids must be a list.")
            definition_ids = tuple(int(value) for value in raw_definition_ids)
            if len(set(definition_ids)) != len(definition_ids):
                raise ConfigError(f"repository {repository_name!r} has duplicate CI definition IDs.")
            reusable_template_prs = _reusable_template_pr_config(
                raw_repository.get("reusable_template_prs"), repository_name
            )
            repositories.append(
                RepositorySpec(
                    name=repository_name,
                    ci_definition_ids=definition_ids,
                    reusable_template_prs=reusable_template_prs,
                )
            )
        repositories = tuple(repositories)
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
