"""
Deterministic local conversation title generator for Sovereign AI Workbench.
Pure local rule-based heuristic — zero cloud/external API calls.
"""

import re

# Domain specific patterns for industrial / engineering tasks
DOMAIN_PATTERNS = [
    (r"\bvibration\b.*\b(?:threshold|limit|iso|velocity)\b", "Vibration Velocity Thresholds"),
    (r"\b(?:telemetry|equipment readings?|sensor data)\b.*\b(?:analysis|analyze|trend|abnormal)\b", "Equipment Telemetry Analysis"),
    (r"\b(?:inspection report|maintenance inspection)\b.*\b(?:review|summarize|risk|finding)\b", "Inspection Report Review"),
    (r"\b(?:pressure drop|hydraulic)\b", "Pressure Drop Calculation"),
    (r"\bpump\b.*\b(?:efficiency|curve|head)\b", "Pump Efficiency Calculation"),
    (r"\biso\s*10816\b", "ISO 10816 Standard Assessment"),
    (r"\b(?:sop|standard operating procedure)\b", "SOP Compliance Review"),
    (r"\bbearing\b.*\b(?:temperature|failure|vibration)\b", "Bearing Condition Assessment"),
    (r"\bcompressor\b.*\b(?:temperature|stage|vibration)\b", "Compressor Health Evaluation"),
    (r"\bheat exchanger\b", "Heat Exchanger Analysis"),
    (r"\bcoding\b|\bpython\b|\bsandbox\b", "Sandbox Code Execution"),
]

# Filler prefixes to strip
FILLER_PREFIXES = [
    r"^what\s+(?:are\s+the|is\s+the|does\s+the)\s+",
    r"^can\s+you\s+(?:please\s+)?(?:summarize|analyze|explain|give|show|find)?\s*",
    r"^could\s+you\s+(?:please\s+)?(?:summarize|analyze|explain|give|show|find)?\s*",
    r"^please\s+(?:summarize|analyze|review|provide|calculate)?\s*",
    r"^summarize\s+(?:the|this)?\s*",
    r"^analyze\s+(?:the|this|uploaded)?\s*",
    r"^review\s+(?:the|this|uploaded)?\s*",
    r"^tell\s+me\s+(?:about\s+)?(?:the)?\s*",
    r"^explain\s+(?:the)?\s*",
    r"^how\s+(?:do|to|can)\s+",
    r"^give\s+me\s+(?:the)?\s*",
]


def generate_conversation_title(message: str) -> str:
    """
    Generate a clean, concise (<= 40 chars) title for a conversation
    based on the initial user message.
    """
    if not message:
        return "New Chat"

    msg_clean = message.strip().replace("\n", " ")
    msg_lower = msg_clean.lower()

    # 1. Match domain-specific industrial patterns first
    for pattern, title in DOMAIN_PATTERNS:
        if re.search(pattern, msg_lower):
            return title

    # 2. Strip conversational boilerplate
    stripped = msg_lower
    for prefix in FILLER_PREFIXES:
        stripped = re.sub(prefix, "", stripped, flags=re.IGNORECASE).strip()

    # Remove trailing punctuation or question marks
    stripped = re.sub(r"[?!.,:;]+$", "", stripped).strip()

    if not stripped:
        return "New Chat"

    # Take first 4-5 words
    words = [w for w in stripped.split() if len(w) > 1]
    if not words:
        words = stripped.split()

    candidate = " ".join(words[:4]).title()

    # Keep under 38 characters
    if len(candidate) > 38:
        candidate = candidate[:35].rstrip() + "..."

    return candidate if candidate else "New Chat"
