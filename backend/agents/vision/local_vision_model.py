from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.config import settings
from agents.vision.vision_model import SourceReference

logger = logging.getLogger(__name__)


class LocalVisionModel:
    def __init__(self):
        self.model = getattr(settings, "vision_model", "llava:7b")
        self.base_url = getattr(settings, "ollama_base_url", "http://localhost:11434")
        self.timeout = getattr(settings, "ollama_timeout", 120.0)
        self._check_model_availability()

    def _check_model_availability(self):
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]
                
                available = any(m == self.model or m.startswith(self.model + ":") for m in model_names)
                if not available:
                    raise RuntimeError(f"Vision model '{self.model}' is not available in Ollama. Install it with: ollama pull {self.model}")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            raise RuntimeError(f"Failed to connect to Ollama at {self.base_url}") from e

    def analyze(
        self,
        *,
        image_bytes: bytes,
        source: SourceReference,
        request: str,
        reference_context: str = "",
    ) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("Image bytes cannot be empty.")
            
        encoded = base64.b64encode(image_bytes).decode("ascii")

        prompt = (
            f"User request: {request}\n\n"
            f"Reference context: {reference_context}\n\n"
            "Analyze the image and extract the following structured visual information. "
            "Examine engineering elements, equipment tags, valves, pumps, vessels, piping, flow arrows, instruments, visible labels, "
            "and visible physical condition indicators.\n"
            "Do not hallucinate internal or invisible conditions. State uncertainty explicitly where visual resolution is limited.\n\n"
            "Return ONLY a JSON object with exactly these keys:\n"
            "- description: string (concise visual summary)\n"
            "- detected_text: string (any visible text, labels, or alphanumeric codes)\n"
            "- objects: array of strings (visible equipment and components)\n"
            "- findings: array of objects with keys {\"type\": string, \"label\": string, \"confidence\": float (0.0 to 1.0)}\n"
            "- warnings: array of strings (uncertainties, ambiguities, or visual caveats)\n"
            "- confidence: string (\"high\", \"medium\", or \"low\")"
        )

        try:
            from app.services.network_monitor import network_monitor
            network_monitor.record_connection(
                source="VisionAgent",
                destination=self.base_url,
                reason=f"Local visual analysis inference (model: {self.model})",
            )
        except Exception:
            pass

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "images": [encoded],
                        "stream": False,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                result_data = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to generate analysis using Ollama: {e}")

        response_text = result_data.get("response", "{}")
        try:
            parsed_json = json.loads(response_text)
            
            raw_findings = parsed_json.get("findings", [])
            normalized_findings = []
            if isinstance(raw_findings, list):
                for item in raw_findings:
                    if isinstance(item, dict):
                        normalized_findings.append({
                            "type": str(item.get("type", "feature")),
                            "label": str(item.get("label", item.get("name", ""))),
                            "confidence": float(item.get("confidence", 0.85)) if item.get("confidence") is not None else 0.85,
                        })
                    elif isinstance(item, str):
                        normalized_findings.append({
                            "type": "feature",
                            "label": item,
                            "confidence": 0.85,
                        })

            return {
                "description": str(parsed_json.get("description", "")),
                "detected_text": str(parsed_json.get("detected_text", "")),
                "objects": list(parsed_json.get("objects", [])),
                "findings": normalized_findings,
                "warnings": list(parsed_json.get("warnings", [])),
                "confidence": str(parsed_json.get("confidence", "medium")),
                "source_id": source.source_id,
                "file_name": source.file_name,
                "page_number": getattr(source, "page_number", None),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to parse structured output from Ollama: {e}\nResponse text: {response_text}")
