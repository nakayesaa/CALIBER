"""Shared trace links must never silently resolve a different equipment's evidence."""

import pytest

from services.api.tests.test_backend_api import client as client
from services.api.tests.test_he_3301_api import HE
from services.api.tests.test_he_3301_api import he_client as he_client


@pytest.mark.parametrize("trace_id", [
    "health-trajectory", "event-progression", "condition-insights", "production-shortfall",
    "rca-indication", "capa-plan", "recovery-effectiveness",
])
def test_he_shared_claims_are_asset_scoped(he_client, trace_id):
    response = he_client.get(f"/api/v1/traceability/claims/{trace_id}?asset_id={HE}")
    assert response.status_code == 200, response.text
    claim = response.json()
    assert claim["title"].startswith("HE-3301")
    assert claim["sources"]
    assert all(source["source_key"].startswith("he_") for source in claim["sources"])
    assert "ko_3201" not in str(claim)
    if trace_id == "production-shortfall":
        record = claim["preview"]["rows"][0]
        assert record["sampled_off_hours"] == 13
        assert record["rca_reported_hours"] == 12
        assert record["rca_reported_loss_tonnes"] == 216
    if trace_id == "recovery-effectiveness":
        assert "PENDING_REVIEW" in " ".join(claim["calculation"])


def test_he_unknown_claim_and_asset_are_not_found(he_client):
    assert he_client.get(f"/api/v1/traceability/claims/unknown?asset_id={HE}").status_code == 404
    assert he_client.get("/api/v1/traceability/claims/health-trajectory?asset_id=unknown").status_code == 404
    default = he_client.get("/api/v1/traceability/claims/condition-insights")
    assert default.status_code == 200
    assert any("ko_3201" in source["source_key"] for source in default.json()["sources"])
