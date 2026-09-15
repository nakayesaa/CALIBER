#!/usr/bin/env python3
"""Build a governed KO-3201 CA/PA proposal from an RCA record."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.api.app.schemas.actions import ActionItem
from services.api.app.schemas.rca import RCARecord
from services.api.app.services.actions.workflow import (
    build_action_plan,
    load_action_policy,
)
from services.api.app.services.file_io import atomic_write_json as write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--rca", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--hypothesis-id", type=str, default=None)
    return parser.parse_args()


def model_to_row(model: BaseModel) -> dict[str, Any]:
    row = model.model_dump(mode="json")
    for key, value in row.items():
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return row


def write_actions(path: Path, actions: list[ActionItem]) -> None:
    rows = [model_to_row(action) for action in actions]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ActionItem.model_fields))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def run(
    root: Path,
    rca_path: Path | None = None,
    output: Path | None = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    rca_path = (rca_path or root / "data/rca/ko_3201/v1/rca_record.json").resolve()
    output = (output or root / "data/actions/ko_3201/v1").resolve()
    if not rca_path.is_file():
        raise FileNotFoundError(f"Missing RCA record: {rca_path}")
    rca = RCARecord.model_validate_json(rca_path.read_text(encoding="utf-8"))
    policy = load_action_policy(root / "data/catalog/ko_3201_action_policy.yaml")
    selected = hypothesis_id or rca.generation.hypotheses[0].hypothesis_id
    plan = build_action_plan(rca, selected, policy, rca.evidence_as_of.date())
    write_json(output / "action_plan.json", plan)
    write_actions(output / "actions.csv", plan.actions)
    validation = {
        "status": "PASS",
        "plan_id": plan.plan_id,
        "selected_hypothesis_id": selected,
        "action_count": len(plan.actions),
        "action_types": [action.action_type for action in plan.actions],
        "initial_status": plan.status,
        "approval_gate": "RCA must be APPROVED before action approval",
    }
    write_json(output / "technical_validation.json", validation)
    return validation


def main() -> None:
    args = parse_args()
    report = run(args.root, args.rca, args.output, args.hypothesis_id)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
