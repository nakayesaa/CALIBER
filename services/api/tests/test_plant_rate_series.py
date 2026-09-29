"""The plant-rate chart must use the observed KO-3201 production workbook rows."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/normalized/ko_3201/production_observations.csv"


@pytest.mark.skipif(not SOURCE.is_file(), reason="Canonical source artifact unavailable")
def test_zcu_daily_plant_rate_uses_all_720_observed_hours() -> None:
    response = TestClient(create_app(ROOT)).get(
        "/api/v1/assets/asset-ko-3201/production-rate"
    )

    assert response.status_code == 200
    series = response.json()
    assert series["plant_id"] == "ZCU"
    assert series["source_key"] == "production_ko_3201"
    assert series["source_rows"] == 720
    assert len(series["points"]) == 30
    assert {point["sample_count"] for point in series["points"]} == {24}
    assert series["points"][0]["date"] == "2026-04-01"
    assert series["points"][0]["average_rate_tph"] == pytest.approx(55.9769, abs=0.001)
    assert series["points"][-1]["date"] == "2026-04-30"
    assert series["points"][-1]["average_rate_tph"] == pytest.approx(21.2421, abs=0.001)
