"""
Orchestrator for Sovereign AI Workbench.

Receives a user task, determines which agents to run (from a workflow
definition), executes them in dependency order, and collects results.

Architecture:
    User request + files + workflow name
        → Orchestrator.run()
            → topological sort of AgentTasks
            → for each task:
                  build AgentContext (with upstream AgentResults)
                  call adapter(context)
                  collect AgentResult
            → return WorkflowResult

All processing is local. No cloud APIs are called by the orchestrator
itself. Individual agents may use the local LLM via Ollama.
"""

import logging
import time
from datetime import datetime, timezone

from agents.orchestrator.state import AgentContext, AgentResult, AgentTask
from agents.orchestrator.registry import get_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predefined workflows
# ---------------------------------------------------------------------------

DATA_ANALYSIS_WORKFLOW = [
    AgentTask(
        agent_name="data_analysis",
        instruction="Analyze the attached data files and produce "
                    "descriptive statistics, trends, and charts.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a report from the data analysis results.",
        depends_on=["data_analysis"],
    ),
]

VISION_WORKFLOW = [
    AgentTask(
        agent_name="vision",
        instruction="Analyze the attached images or PDF pages.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a report from the vision analysis results.",
        depends_on=["vision"],
    ),
]

# Map of workflow names to their task lists
WORKFLOWS: dict[str, list[AgentTask]] = {
    "data_analysis": DATA_ANALYSIS_WORKFLOW,
    "vision": VISION_WORKFLOW,
}


# ---------------------------------------------------------------------------
# WorkflowResult — structured output from a complete workflow run
# ---------------------------------------------------------------------------

class WorkflowResult:
    """
    Collects the outcome of an entire workflow execution.

    Attributes:
        workflow_name: Which workflow was executed.
        status:        "completed", "partial", or "failed".
        steps:         Ordered list of execution step summaries.
        results:       Agent results keyed by agent_name.
        artifacts:     Aggregated file paths from all agents.
        warnings:      Aggregated warnings from all agents.
        errors:        Aggregated errors from all agents.
        duration_ms:   Total execution time in milliseconds.
    """

    def __init__(self, workflow_name: str):
        self.workflow_name = workflow_name
        self.status = "pending"
        self.steps: list[dict] = []
        self.results: dict[str, AgentResult] = {}
        self.artifacts: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.duration_ms: float = 0

    def to_dict(self) -> dict:
        """Serialize to a plain dict for the API response."""
        return {
            "workflow_name": self.workflow_name,
            "status": self.status,
            "steps": self.steps,
            "agent_results": {
                name: result.model_dump(mode="json")
                for name, result in self.results.items()
            },
            "artifacts": self.artifacts,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 1),
        }


# ---------------------------------------------------------------------------
# Topological sort — respects depends_on ordering
# ---------------------------------------------------------------------------

def _topological_sort(tasks: list[AgentTask]) -> list[AgentTask]:
    """
    Sort tasks so that dependencies come before dependents.

    Raises:
        ValueError: If there are missing or circular dependencies.
    """
    task_map = {task.agent_name: task for task in tasks}
    all_names = set(task_map.keys())

    # Check for unknown dependencies
    for task in tasks:
        unknown = set(task.depends_on) - all_names
        if unknown:
            raise ValueError(
                f"Agent '{task.agent_name}' depends on unknown agents: "
                f"{sorted(unknown)}"
            )

    # Kahn's algorithm
    in_degree = {name: 0 for name in all_names}
    for task in tasks:
        for dep in task.depends_on:
            in_degree[task.agent_name] += 1

    queue = [name for name, degree in in_degree.items() if degree == 0]
    sorted_names: list[str] = []

    while queue:
        # Process in a stable order
        queue.sort()
        current = queue.pop(0)
        sorted_names.append(current)

        for task in tasks:
            if current in task.depends_on:
                in_degree[task.agent_name] -= 1
                if in_degree[task.agent_name] == 0:
                    queue.append(task.agent_name)

    if len(sorted_names) != len(all_names):
        remaining = all_names - set(sorted_names)
        raise ValueError(
            f"Circular dependency detected among: {sorted(remaining)}"
        )

    return [task_map[name] for name in sorted_names]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Executes a workflow by running agents in dependency order.

    Usage:
        orchestrator = Orchestrator()
        result = orchestrator.run(
            user_request="Analyze the attached CSV",
            files=["data.csv"],
            workflow_name="data_analysis",
        )
    """

    def run(
        self,
        user_request: str,
        files: list[str] | None = None,
        workflow_name: str = "data_analysis",
        tasks: list[AgentTask] | None = None,
    ) -> WorkflowResult:
        """
        Execute a workflow.

        Args:
            user_request:  The user's instruction.
            files:         Attached file paths.
            workflow_name: Name of a predefined workflow, or "custom"
                          if tasks are provided directly.
            tasks:         Optional custom task list (overrides workflow_name).

        Returns:
            WorkflowResult with all agent outputs, artifacts, and errors.
        """
        files = files or []
        start_time = time.monotonic()

        # Resolve workflow tasks
        if tasks is not None:
            workflow_tasks = tasks
            workflow_name = workflow_name or "custom"
        else:
            if workflow_name not in WORKFLOWS:
                raise ValueError(
                    f"Unknown workflow: '{workflow_name}'. "
                    f"Available: {sorted(WORKFLOWS.keys())}"
                )
            workflow_tasks = WORKFLOWS[workflow_name]

        result = WorkflowResult(workflow_name=workflow_name)

        logger.info(
            "WORKFLOW START — name: %s, agents: %s, files: %d",
            workflow_name,
            [t.agent_name for t in workflow_tasks],
            len(files),
        )

        # Sort tasks in dependency order
        try:
            sorted_tasks = _topological_sort(workflow_tasks)
        except ValueError as exc:
            logger.error("Workflow validation failed: %s", exc)
            result.status = "failed"
            result.errors.append(str(exc))
            result.duration_ms = (time.monotonic() - start_time) * 1000
            return result

        # Track which agents completed successfully
        completed_results: dict[str, AgentResult] = {}
        has_failures = False

        # Execute each agent in order
        for task in sorted_tasks:
            step_start = time.monotonic()
            step_info = {
                "agent": task.agent_name,
                "instruction": task.instruction,
                "depends_on": task.depends_on,
                "status": "pending",
                "started_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }

            logger.info("AGENT START — %s", task.agent_name)

            # Check if dependencies were satisfied
            missing_deps = [
                dep for dep in task.depends_on
                if dep not in completed_results
            ]

            if missing_deps:
                error_msg = (
                    f"Skipped '{task.agent_name}' — upstream agent(s) "
                    f"failed: {missing_deps}"
                )
                logger.warning("AGENT SKIPPED — %s: %s", task.agent_name, error_msg)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="skipped",
                    summary=error_msg,
                    errors=[error_msg],
                )
                step_info["status"] = "skipped"
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(error_msg)
                result.steps.append(step_info)
                continue

            # Look up the adapter
            try:
                adapter = get_agent(task.agent_name)
            except (KeyError, RuntimeError) as exc:
                error_msg = str(exc)
                logger.error("AGENT ERROR — %s: %s", task.agent_name, error_msg)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="failed",
                    errors=[error_msg],
                )
                step_info["status"] = "failed"
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(error_msg)
                result.steps.append(step_info)
                continue

            if adapter is None:
                error_msg = (
                    f"Agent '{task.agent_name}' is registered as a "
                    "placeholder and not yet implemented."
                )
                logger.warning("AGENT SKIPPED — %s: placeholder", task.agent_name)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="skipped",
                    summary=error_msg,
                    warnings=[error_msg],
                )
                step_info["status"] = "skipped"
                step_info["warning"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.warnings.append(error_msg)
                result.steps.append(step_info)
                continue

            # Build the context for this agent
            context = AgentContext(
                task=task,
                user_request=user_request,
                files=files,
                dependencies={
                    dep: completed_results[dep]
                    for dep in task.depends_on
                    if dep in completed_results
                },
            )

            # Execute the adapter
            try:
                agent_result = adapter(context)

                # Ensure agent_name is set
                if not agent_result.agent_name:
                    agent_result.agent_name = task.agent_name

                step_duration = (time.monotonic() - step_start) * 1000

                logger.info(
                    "AGENT COMPLETE — %s (%.0f ms, %d artifacts)",
                    task.agent_name,
                    step_duration,
                    len(agent_result.artifacts),
                )

                step_info["status"] = "completed"
                step_info["duration_ms"] = round(step_duration, 1)
                step_info["summary"] = agent_result.summary
                step_info["artifact_count"] = len(agent_result.artifacts)

                completed_results[task.agent_name] = agent_result
                result.results[task.agent_name] = agent_result
                result.artifacts.extend(agent_result.artifacts)
                result.warnings.extend(agent_result.warnings)

            except Exception as exc:
                step_duration = (time.monotonic() - step_start) * 1000
                error_msg = f"{type(exc).__name__}: {exc}"

                logger.error(
                    "AGENT ERROR — %s (%.0f ms): %s",
                    task.agent_name,
                    step_duration,
                    error_msg,
                )

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="failed",
                    summary=f"Agent failed: {error_msg}",
                    errors=[error_msg],
                )

                step_info["status"] = "failed"
                step_info["duration_ms"] = round(step_duration, 1)
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(
                    f"[{task.agent_name}] {error_msg}"
                )

            result.steps.append(step_info)

        # Determine overall status
        total_duration = (time.monotonic() - start_time) * 1000
        result.duration_ms = total_duration

        if not has_failures:
            result.status = "completed"
        elif completed_results:
            result.status = "partial"
        else:
            result.status = "failed"

        logger.info(
            "WORKFLOW COMPLETE — %s, status: %s, duration: %.0f ms, "
            "agents: %d completed / %d total",
            workflow_name,
            result.status,
            total_duration,
            len(completed_results),
            len(sorted_tasks),
        )

        return result
