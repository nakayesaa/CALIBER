"""Pure normalization helpers used by source-specific ingestion."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.api.app.schemas.canonical import WorkflowStatus

WHITESPACE = re.compile(r"\s+")
NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")


def canonical_header(value: Any) -> str:
    """Normalize visual Excel headers without losing their semantic wording."""

    return WHITESPACE.sub(" ", str(value).strip())


def optional_text(value: Any) -> str | None:
    """Normalize common empty spreadsheet values to ``None``."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text.lower() in {"", "n/a", "na", "none", "nan", "-"}:
        return None
    return text


def slug_label(value: Any, *, fallback: str = "UNKNOWN") -> str:
    """Convert source vocabulary to a deterministic uppercase label."""

    text = optional_text(value)
    if text is None:
        return fallback
    label = NON_ALPHANUMERIC.sub("_", text.upper()).strip("_")
    return label or fallback


def localize_source_timestamp(value: Any, timezone_name: str) -> datetime:
    """Parse a source-local timestamp and attach the documented assumption."""

    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip())
    zone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def normalize_workflow_status(value: Any) -> WorkflowStatus:
    """Map the supplied overall-status vocabulary to API-safe labels."""

    source = canonical_header(value).upper()
    mapping = {
        "NEW REGISTERED": WorkflowStatus.NEW_REGISTERED,
        "RCA PROCESS": WorkflowStatus.RCA_PROCESS,
        "CA/PA EXECUTION": WorkflowStatus.CA_PA_EXECUTION,
        "MONITORING RESULT": WorkflowStatus.MONITORING_RESULT,
        "RISK CLOSED": WorkflowStatus.RISK_CLOSED,
        "RISK CANCELED": WorkflowStatus.RISK_CANCELED,
        "RISK CANCELLED": WorkflowStatus.RISK_CANCELED,
    }
    try:
        return mapping[source]
    except KeyError as exc:
        raise ValueError(f"Unsupported workflow status: {value!r}") from exc

