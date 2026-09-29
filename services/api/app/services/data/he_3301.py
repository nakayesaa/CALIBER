"""Load the validated HE artifact without silently falling back to another asset."""

from pathlib import Path

from services.api.app.schemas.equipment import EquipmentInvestigation


def load_he_3301(root: Path) -> EquipmentInvestigation:
    path = root / "data/normalized/he_3301/equipment.json"
    result = EquipmentInvestigation.model_validate_json(path.read_text(encoding="utf-8"))
    if result.asset.asset_id != "asset-he-3301":
        raise ValueError("HE artifact asset identity does not match HE-3301")
    return result
