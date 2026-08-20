from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from leai.ai.base import BaseLLMClient
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


@dataclass
class WorkflowStep:
    """Represents an execution step inside an autonomous workflow."""

    step_number: int
    name: str
    description: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    duration_seconds: float = 0.0
    output_summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Consolidated result produced by a workflow run."""

    workflow_name: str
    target: str
    success: bool
    summary: str
    total_duration_seconds: float
    steps: list[WorkflowStep] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    report_markdown: str = ""

    def export_report(self, output_path: Path | None = None) -> Path:
        """Exports the generated workflow report to a Markdown file."""
        target_file = output_path or Path(f"leai_workflow_{self.workflow_name}_{self.target}.md")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(self.report_markdown, encoding="utf-8")
        return target_file


class BaseWorkflow(ABC):
    """Abstract base class for declarative, multi-step autonomous workflows in LEAI."""

    def __init__(
        self,
        name: str,
        description: str,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
    ):
        self.name = name
        self.description = description
        self.schemas = schemas
        self.config = config
        self.client = client
        self.steps: list[WorkflowStep] = []

    @abstractmethod
    def run(
        self,
        target: str,
        on_step_start: Callable[[WorkflowStep], None] | None = None,
        on_step_end: Callable[[WorkflowStep], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> WorkflowResult:
        """Executes the workflow against the specified target object."""
