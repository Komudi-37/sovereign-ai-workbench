"""
Agent registry for Sovereign AI Workbench.

Maps agent names to their adapter callables. Each adapter has the signature:

    def adapter(context: AgentContext) -> AgentResult

Adapters are imported lazily to avoid pulling heavy dependencies
(numpy, pandas, Pillow, etc.) at FastAPI startup time.

To add a new agent:
    1. Implement the adapter function.
    2. Add a lazy loader below.
    3. Register it in AGENT_REGISTRY.
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy loaders — import the adapter only when actually needed
# ---------------------------------------------------------------------------

def _load_data_analysis():
    """Lazy-load the data analysis adapter."""
    from agents.data_analysis.analyser import data_analysis_adapter
    return data_analysis_adapter


def _load_vision():
    """Lazy-load the vision adapter."""
    from agents.vision.image_analyzer import vision_adapter
    return vision_adapter


def _load_report():
    """Lazy-load the report adapter."""
    from agents.report.report_agent import report_adapter
    return report_adapter


# ---------------------------------------------------------------------------
# Registry — maps agent names to lazy loaders or None (placeholder)
# ---------------------------------------------------------------------------

# Each value is either:
#   - A callable that returns the adapter function (lazy loader)
#   - None, meaning the agent is registered but not yet implemented
AGENT_REGISTRY: dict[str, Callable | None] = {
    "data_analysis": _load_data_analysis,
    "vision":        _load_vision,
    "report":        _load_report,
    "ocr":           None,   # placeholder — not yet implemented
    "rag":           None,   # placeholder — not yet implemented
}


def get_agent(name: str) -> Callable | None:
    """
    Look up an agent adapter by name.

    Returns:
        The adapter callable, or None if the agent is a placeholder.

    Raises:
        KeyError: If the agent name is not registered at all.
    """
    if name not in AGENT_REGISTRY:
        raise KeyError(
            f"Unknown agent: '{name}'. "
            f"Registered agents: {sorted(AGENT_REGISTRY.keys())}"
        )

    loader = AGENT_REGISTRY[name]

    if loader is None:
        logger.warning("Agent '%s' is registered but not yet implemented", name)
        return None

    # Call the lazy loader to get the actual adapter function
    try:
        adapter = loader()
    except ImportError as exc:
        logger.error(
            "Agent '%s' failed to load — missing dependency: %s", name, exc
        )
        raise RuntimeError(
            f"Agent '{name}' cannot be loaded — missing dependency: {exc}. "
            f"Install its requirements first."
        ) from exc

    logger.debug("Loaded agent adapter: %s", name)
    return adapter


def list_agents() -> dict[str, str]:
    """
    List all registered agents and their availability.

    Returns:
        Dict of {agent_name: "available" | "placeholder"}.
    """
    return {
        name: "available" if loader is not None else "placeholder"
        for name, loader in AGENT_REGISTRY.items()
    }
