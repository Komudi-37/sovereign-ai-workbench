"""
Network and Sovereignty Monitor Service for Sovereign AI Workbench.

Provides application-level monitoring, recording, and enforcement of:
- Allowed local connections (e.g. 127.0.0.1, localhost, ::1 to Ollama)
- Blocked external calls (e.g. attempted requests to cloud AI providers)
- Cloud API key detection in runtime environment (without exposing secret values)
- Sovereignty status and metrics for APIs and UI dashboard
- Audit log integration for sovereignty events
"""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sovereign Policy Constants
SOVEREIGN_MODE: bool = True
EXTERNAL_NETWORK_ALLOWED: bool = False
LOCAL_LLM_ONLY: bool = True

# Loopback hosts considered local
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}

# Known cloud AI domains and signatures to block/flag
KNOWN_CLOUD_AI_DOMAINS = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "googleapis.com",
    "openai.azure.com",
    "bedrock.amazonaws.com",
    "api.mistral.ai",
    "api.cohere.ai",
    "replicate.com",
    "together.xyz",
    "groq.com",
    "huggingface.co",
]

# Sensitive Cloud Credential Names to probe for
SENSITIVE_CREDENTIAL_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
]


class NetworkMonitorService:
    """
    Lightweight in-memory network activity and sovereignty monitor.
    Tracks allowed local calls and blocks/records external connection attempts.
    """

    def __init__(self, max_events: int = 200):
        self.max_events = max_events
        self.events: list[dict[str, Any]] = []
        self.external_calls_attempted: int = 0
        self.external_calls_blocked: int = 0
        self.local_calls: int = 0

    def is_local_host(self, host: str) -> bool:
        """Check if host string is a local loopback address."""
        if not host:
            return True
        h = host.lower().strip()
        # Remove surrounding brackets if IPv6
        if h.startswith("[") and h.endswith("]"):
            h = h[1:-1]
        elif h.startswith("[") and "]" in h:
            h = h[1:h.index("]")]
        # Strip port if present
        if ":" in h and not (h.startswith(":") or h == "::1"):
            h = h.split(":")[0]
        return h in LOCAL_HOSTS or h == "::1"

    def classify_destination(self, destination: str) -> str:
        """
        Classifies a destination as 'LOCAL' or 'EXTERNAL'.
        Handles URLs, host:port, or bare hostnames.
        """
        dest_clean = destination.strip()
        if "://" in dest_clean:
            parsed = urlparse(dest_clean)
            host = parsed.hostname or ""
        else:
            host = dest_clean.split(":")[0]

        if self.is_local_host(host):
            return "LOCAL"
        return "EXTERNAL"

    def record_connection(
        self,
        source: str,
        destination: str,
        port: int | str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        Evaluate and record a network connection attempt.
        If destination is EXTERNAL and EXTERNAL_NETWORK_ALLOWED is False,
        marks action as BLOCKED and increments block counter.
        Otherwise marks action as ALLOWED and increments local counter.
        """
        classification = self.classify_destination(destination)

        if classification == "LOCAL":
            action = "ALLOWED"
            self.local_calls += 1
            log_reason = reason or "Allowed local loopback connection"
        else:
            self.external_calls_attempted += 1
            if not EXTERNAL_NETWORK_ALLOWED:
                action = "BLOCKED"
                self.external_calls_blocked += 1
                base_block_msg = "Blocked by Sovereign Local-Only Policy"
                log_reason = f"{base_block_msg}: {reason}" if reason else base_block_msg
                # Audit log violation
                self._audit_sovereignty_violation(source, destination, log_reason)
            else:
                action = "ALLOWED"
                log_reason = reason or "External network call allowed"

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "destination": destination,
            "port": str(port) if port is not None else "",
            "classification": classification,
            "action": action,
            "reason": log_reason,
        }

        self.events.insert(0, event)
        if len(self.events) > self.max_events:
            self.events.pop()

        return event

    def detect_cloud_api_keys(self) -> dict[str, Any]:
        """
        Detect presence of cloud API keys without exposing secrets.
        Returns:
            {
                "detected": bool,
                "keys_detected": list[str],  # Names only, never values
                "count": int
            }
        """
        detected_names: list[str] = []

        for key in SENSITIVE_CREDENTIAL_KEYS:
            val = os.environ.get(key)
            if val and val.strip():
                detected_names.append(key)

        # Also search for obvious variant patterns (e.g. *API_KEY, *_SECRET)
        for env_k, env_v in os.environ.items():
            if env_k in detected_names:
                continue
            k_upper = env_k.upper()
            if any(provider in k_upper for provider in ["OPENAI", "ANTHROPIC", "GEMINI", "AZURE_OPENAI"]):
                if env_v and env_v.strip():
                    detected_names.append(env_k)

        return {
            "detected": len(detected_names) > 0,
            "keys_detected": detected_names,
            "count": len(detected_names),
        }

    def get_summary(self) -> dict[str, Any]:
        """
        Return comprehensive sovereignty monitor summary.
        """
        key_status = self.detect_cloud_api_keys()

        return {
            "sovereign_mode": SOVEREIGN_MODE,
            "external_network_allowed": EXTERNAL_NETWORK_ALLOWED,
            "local_llm_only": LOCAL_LLM_ONLY,
            "external_calls_attempted": self.external_calls_attempted,
            "external_calls_blocked": self.external_calls_blocked,
            "local_calls": self.local_calls,
            "cloud_api_keys_detected": key_status["detected"],
            "detected_key_names": key_status["keys_detected"],
            "recent_events_count": len(self.events),
        }

    def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return most recent network security events."""
        return self.events[:limit]

    def _audit_sovereignty_violation(self, source: str, destination: str, reason: str):
        """Record violation to the system audit database."""
        try:
            from app.services.audit import audit_log
            audit_log(
                action="EXTERNAL_CONNECTION_BLOCKED",
                agent_name=source,
                resource=destination,
                metadata={"reason": reason, "policy": "SOVEREIGN_MODE"},
            )
        except Exception as exc:
            logger.debug("Failed to record audit for sovereignty event: %s", exc)


# Global singleton instance
network_monitor = NetworkMonitorService()
