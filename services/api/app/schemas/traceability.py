"""Contracts for governed source registry and claim-level traceability."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TraceabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


TraceValue = str | int | float | bool | None


class SourceFieldMapping(TraceabilityModel):
    source_field: str
    canonical_field: str
    unit: str
    cadence: str
    status: str


class SourceQualityIssue(TraceabilityModel):
    issue_id: str
    severity: str
    flag: str
    description: str
    resolution_status: str


class DataSourceSummary(TraceabilityModel):
    source_key: str
    title: str
    domain: str
    role: str
    cadence: str
    status: Literal["CONNECTED", "REVIEW_REQUIRED", "REFERENCE"]
    mapping_count: int
    quality_issue_count: int
    record_count: int | None
    modified_at: str
    source_url: str


class DataSourceDetail(TraceabilityModel):
    source: DataSourceSummary
    local_path: str
    parser: str
    checksum: str
    mappings: list[SourceFieldMapping]
    quality_issues: list[SourceQualityIssue]


class TraceSource(TraceabilityModel):
    source_key: str
    title: str
    location: str
    role: str
    mappings: list[SourceFieldMapping]


class TraceLineageStep(TraceabilityModel):
    sequence: int
    kind: Literal["SOURCE", "CANONICAL", "RULE", "MODEL", "AI", "VIEW"]
    label: str
    reference: str


class TraceRecordPreview(TraceabilityModel):
    columns: list[str]
    rows: list[dict[str, TraceValue]]


class TraceClaim(TraceabilityModel):
    trace_id: str
    title: str
    value: str
    unit: str | None
    provenance: Literal[
        "RECORDED",
        "STANDARDIZED",
        "CALCULATED",
        "MODEL_OUTPUT",
        "AI_SYNTHESIS",
        "HUMAN_VERIFIED",
    ]
    summary: str
    as_of: str
    calculation: list[str]
    lineage: list[TraceLineageStep]
    sources: list[TraceSource]
    quality_issues: list[SourceQualityIssue]
    preview: TraceRecordPreview | None
