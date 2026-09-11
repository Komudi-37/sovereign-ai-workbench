"""
Agent registry for Sovereign AI Workbench.

Maps agent names to their adapter callables. Adapters are imported
lazily to avoid pulling heavy dependencies at startup time.
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy loaders
# ---------------------------------------------------------------------------

def _load_data_analysis():
    from agents.data_analysis.analyser import data_analysis_adapter
    return data_analysis_adapter

def _load_vision():
    from agents.vision.image_analyzer import vision_adapter
    return vision_adapter

def _load_report():
    from agents.report.report_agent import report_adapter
    return report_adapter

def _load_ocr():
    from agents.ocr.ocr_agent import ocr_adapter
    return ocr_adapter

def _load_rag():
    from agents.rag.rag_agent import rag_adapter
    return rag_adapter


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, Callable | None] = {
    "data_analysis": _load_data_analysis,
    "vision":        _load_vision,
    "report":        _load_report,
    "ocr":           _load_ocr,
    "rag":           _load_rag,
}


def get_agent(name: str) -> Callable | None:
    """Look up an agent adapter by name."""
    if name not in AGENT_REGISTRY:
        raise KeyError(
            f"Unknown agent: '{name}'. "
            f"Registered agents: {sorted(AGENT_REGISTRY.keys())}"
        )

    loader = AGENT_REGISTRY[name]

    if loader is None:
        logger.warning("Agent '%s' is registered but not yet implemented", name)
        return None

    try:
        adapter = loader()
    except ImportError as exc:
        logger.error("Agent '%s' failed to load — missing dependency: %s", name, exc)
        raise RuntimeError(
            f"Agent '{name}' cannot be loaded — missing dependency: {exc}. "
            f"Install its requirements first."
        ) from exc

    logger.debug("Loaded agent adapter: %s", name)
    return adapter


def list_agents() -> dict[str, str]:
    """List all registered agents and their availability."""
    return {
        name: "available" if loader is not None else "placeholder"
        for name, loader in AGENT_REGISTRY.items()
    }
