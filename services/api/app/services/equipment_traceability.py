"""Expose the HE source register through the existing source inspector contract."""

from pathlib import Path

import yaml

from services.api.app.schemas.traceability import (
    DataSourceDetail,
    DataSourceSummary,
    SourceFieldMapping,
    SourceQualityIssue,
)
from services.api.app.services.data.he_3301 import load_he_3301


def equipment_source_details(root: Path) -> list[DataSourceDetail]:
    if not (root / "data/normalized/he_3301/equipment.json").is_file():
        return []
    equipment = load_he_3301(root)
    manifest = yaml.safe_load((root / "data/catalog/he_3301_sources.yaml").read_text())
    issues = [
        SourceQualityIssue(
            issue_id=f"he-quality-{index}",
            severity="WARNING",
            flag="SOURCE_REVIEW",
            description=description,
            resolution_status="REVIEW_REQUIRED",
        )
        for index, description in enumerate(equipment.quality_issues, 1)
    ]
    details = []
    for source in manifest["sources"]:
        key = source["source_key"]
        signals = [signal for signal in equipment.signals if signal.source_key == key]
        mappings = [
            SourceFieldMapping(
                source_field=signal.label,
                canonical_field=signal.key,
                unit=signal.unit,
                cadence=signal.cadence,
                status="MAPPED",
            )
            for signal in signals
            if signal.points
        ]
        summary = DataSourceSummary(
            source_key=key,
            title=source["title"],
            domain="Condition"
            if key == "he_performance"
            else "Production"
            if key == "he_production"
            else "RCA / Actions",
            role=source.get("role", "HE-3301 source evidence"),
            cadence=source.get("cadence", "EVENT"),
            status="REVIEW_REQUIRED",
            mapping_count=len(mappings),
            quality_issue_count=len(issues),
            record_count=source.get("record_count"),
            modified_at=source.get("modified_time", ""),
            source_url=source.get(
                "drive_url", f"https://drive.google.com/file/d/{source['drive_id']}/view"
            ),
        )
        details.append(
            DataSourceDetail(
                source=summary,
                local_path=source["local_path"],
                parser=source.get("parser", "he_3301_source_adapter"),
                checksum=source["sha256"],
                mappings=mappings,
                quality_issues=issues,
            )
        )
    return details
