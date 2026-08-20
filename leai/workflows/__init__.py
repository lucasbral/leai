from __future__ import annotations

from typing import Any, Type

from leai.ai.base import BaseLLMClient
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep
from leai.workflows.impact_analysis import ImpactAnalysisWorkflow
from leai.workflows.safe_refactor import SafeRefactorWorkflow

__all__ = [
    "WORKFLOW_REGISTRY",
    "BaseWorkflow",
    "WorkflowResult",
    "WorkflowStep",
    "ImpactAnalysisWorkflow",
    "SafeRefactorWorkflow",
    "get_workflow",
    "list_workflows",
]

WORKFLOW_REGISTRY: dict[str, Type[BaseWorkflow]] = {
    "impact-analysis": ImpactAnalysisWorkflow,
    "impact": ImpactAnalysisWorkflow,
    "safe-refactor": SafeRefactorWorkflow,
    "refactor": SafeRefactorWorkflow,
}


def list_workflows() -> list[dict[str, Any]]:
    """Returns a list of all registered workflows with descriptions."""
    seen = set()
    result = []
    for name, cls in WORKFLOW_REGISTRY.items():
        if cls not in seen:
            seen.add(cls)
            # Create a mock instance to read name & description
            instance = cls(schemas=[], config=LeaiConfig(), client=None)  # type: ignore
            result.append(
                {
                    "name": instance.name,
                    "description": instance.description,
                    "aliases": [k for k, v in WORKFLOW_REGISTRY.items() if v == cls and k != instance.name],
                }
            )
    return result


def get_workflow(
    name: str,
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    client: BaseLLMClient,
) -> BaseWorkflow | None:
    """Instantiates and returns the requested workflow."""
    cls = WORKFLOW_REGISTRY.get(name.strip().lower())
    if not cls:
        return None
    return cls(schemas=schemas, config=config, client=client)
