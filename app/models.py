"""Domain models shared by Azure DevOps collection and presentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineSpec:
    project: str
    name: str
    definition_id: int
    role: str
    repository: str | None = None


@dataclass(frozen=True)
class RepositorySpec:
    name: str


@dataclass(frozen=True)
class TestSummary:
    available: bool = True
    total: int = 0
    passed: int = 0
    failed: int = 0
    not_executed: int = 0
    error: str | None = None

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
    agent_pool: str = "Unknown"
    tests: TestSummary = field(default_factory=TestSummary)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pipeline"] = asdict(self.pipeline)
        return data


@dataclass
class RepositoryHealth:
    project: str
    repository: str
    default_branch: str | None = None
    health: str = "unknown"
    status_reason: str | None = None
    error: str | None = None
    ci_pipeline: PipelineSpec | None = None
    latest_run: PipelineHealth | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "repository": self.repository,
            "default_branch": self.default_branch,
            "branch": self.default_branch.removeprefix("refs/heads/") if self.default_branch else None,
            "health": self.health,
            "status_reason": self.status_reason,
            "error": self.error,
            "ci_pipeline": asdict(self.ci_pipeline) if self.ci_pipeline else None,
            "latest_run": self.latest_run.as_dict() if self.latest_run else None,
        }
