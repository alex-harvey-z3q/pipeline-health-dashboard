"""Domain models shared by Azure DevOps collection and presentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineSpec:
    key: str
    project: str
    name: str
    definition_id: int
    role: str
    repository: str | None = None
    agent_pool: str | None = None


@dataclass(frozen=True)
class RepositorySpec:
    name: str


@dataclass(frozen=True)
class ImageBuildRef:
    pipeline_key: str
    run_id: int
    version: str | None = None


@dataclass(frozen=True)
class DeploymentProvenance:
    deployment_id: str
    environment: str
    agent_pool: str | None
    image_version: str | None
    deployed_at: str | None
    image_build: ImageBuildRef | None = None


@dataclass(frozen=True)
class RunProvenance:
    project: str
    pipeline_key: str
    run_id: int
    agent_pool: str | None = None
    image_version: str | None = None
    image_build: ImageBuildRef | None = None
    deployment_id: str | None = None


@dataclass(frozen=True)
class TestSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    not_executed: int = 0

    @classmethod
    def from_runs(cls, runs: list[dict[str, Any]]) -> "TestSummary":
        return cls(
            total=sum(int(run.get("totalTests", 0)) for run in runs),
            passed=sum(int(run.get("passedTests", 0)) for run in runs),
            failed=sum(int(run.get("failedTests", 0)) + int(run.get("unanalyzedTests", 0)) for run in runs),
            not_executed=sum(int(run.get("notApplicableTests", 0)) + int(run.get("incompleteTests", 0)) for run in runs),
        )


@dataclass
class PipelineHealth:
    pipeline: PipelineSpec
    run_id: int | None = None
    run_number: str | None = None
    status: str = "notStarted"
    result: str | None = None
    branch: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    run_url: str | None = None
    reported_agent_pool: str | None = None
    tests: TestSummary = field(default_factory=TestSummary)
    provenance: RunProvenance | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pipeline"] = asdict(self.pipeline)
        return data


@dataclass
class PullRequestHealth:
    project: str
    repository: str
    pr_id: int
    title: str
    source_branch: str
    target_branch: str
    url: str | None
    validations: list[PipelineHealth] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "repository": self.repository,
            "pr_id": self.pr_id,
            "title": self.title,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "url": self.url,
            "validations": [validation.as_dict() for validation in self.validations],
            "error": self.error,
        }
