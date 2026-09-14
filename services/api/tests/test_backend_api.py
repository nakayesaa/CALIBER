"""End-to-end HTTP tests for the backend vertical slice."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.app.main import create_app
from services.api.app.schemas.rca import RCAGeneration, RCAProviderResult
from services.api.app.services.backend import BackendService


ROOT = Path(__file__).resolve().parents[3]
ALERT_ID = "alert-asset-ko-3201-0001"


class FakeRCAProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> RCAProviderResult:
        assert "manufacturing reliability engineer" in system_prompt
        assert "incident-0002" not in user_prompt
        generation = RCAGeneration.model_validate(
            {
                "executive_summary": "Investigate lubrication contamination and bearing condition.",
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis-1",
                        "rank": 1,
                        "category": "LUBRICATION_CONTAMINATION",
                        "title": "Lubrication contamination",
                        "mechanism": "Water can impair the bearing oil film.",
                        "confidence": 0.7,
                        "rationale": "Water is breached with bearing-related model drivers.",
                        "supporting_evidence_ids": ["signal:water_in_oil"],
                        "contradicting_evidence_ids": [],
                        "analogue_incident_ids": ["incident-0213"],
                        "missing_evidence": ["Independent oil analysis"],
                        "disconfirming_condition": (
                            "Independent testing finds no water contamination."
                        ),
                    }
                ],
                "investigation_steps": [
                    {
                        "step_id": "step-1",
                        "priority": "IMMEDIATE",
                        "instruction": "Collect an independent oil sample.",
                        "rationale": "Verify the online indication.",
                        "expected_evidence": "Traceable water concentration result.",
                        "owner_role": "Reliability Engineer",
                        "safety_gate": True,
                    }
                ],
                "operating_guidance": "Escalate the operating decision to operations.",
                "requires_human_review": True,
            }
        )
        return RCAProviderResult(
            provider="test",
            model="test-model",
            response_id="response-test",
            generation=generation,
            input_tokens=100,
            output_tokens=80,
        )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    required = [
        "data/normalized/ko_3201",
        "data/synthetic/ko_3201/v1",
        "data/features/ko_3201/v1",
        "data/scored/ko_3201/v1",
        "data/alerts/ko_3201/v1",
        "data/retrieval/ko_3201/v1",
    ]
    if not all((ROOT / relative).is_dir() for relative in required):
        pytest.skip("KO-3201 generated artifacts are not available")
    for relative in required:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
    catalog = tmp_path / "data/catalog"
    catalog.mkdir(parents=True)
    for name in [
        "ko_3201_rca_generation.yaml",
        "ko_3201_action_policy.yaml",
        "ko_3201_production_impact.yaml",
        "ko_3201_feature_config.yaml",
        "source_manifest.yaml",
    ]:
        shutil.copy2(ROOT / "data/catalog" / name, catalog / name)
    shutil.copy2(ROOT / "data/catalog/signal_mapping.csv", catalog / "signal_mapping.csv")

    monkeypatch.setenv("CALIBER_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    backend = BackendService(
        tmp_path,
        provider_factory=lambda config: FakeRCAProvider(),
    )
    return TestClient(create_app(tmp_path, backend))


def test_read_models_cover_dashboard_drilldown(client: TestClient) -> None:
    status_response = client.get("/api/v1/status")
    assets_response = client.get("/api/v1/assets")
    overview_response = client.get("/api/v1/assets/asset-ko-3201/overview")
    telemetry_response = client.get(
        "/api/v1/assets/asset-ko-3201/telemetry",
        params={"max_points": 20},
    )
    alert_response = client.get(f"/api/v1/alerts/{ALERT_ID}")
    effectiveness_response = client.get(
        "/api/v1/assets/asset-ko-3201/effectiveness"
    )
    driver_response = client.get(f"/api/v1/alerts/{ALERT_ID}/driver-analysis")

    assert status_response.status_code == 200
    assert status_response.json()["api_status"] == "ready"
    assert assets_response.json()[0]["tag"] == "KO-3201"
    assert overview_response.json()["alert_count"] == 1
    impact = overview_response.json()["production_impact"]
    assert impact["provenance"] == "CALCULATED"
    assert impact["offline_hours"] == pytest.approx(32.0)
    assert impact["estimated_shortfall_tonnes"] == pytest.approx(1762.803, abs=0.01)
    assert impact["baseline"]["expected_feed_tph"] == pytest.approx(55.1075)
    assert impact["baseline"]["healthy_sample_count"] == 1159
    assert impact["baseline"]["confidence"] == "HIGH"
    assert telemetry_response.json()["total_points"] == 4368
    assert telemetry_response.json()["returned_points"] == 20
    first_point = telemetry_response.json()["points"][0]
    operating_fields = {
        "feed_rate_tph",
        "discharge_pressure_barg",
        "motor_current_a",
        "plant_rate_tph",
    }
    assert operating_fields <= first_point.keys()
    assert len(alert_response.json()["similar_incidents"]) == 8
    assert [
        transition["new_state"]
        for transition in alert_response.json()["state_transitions"]
    ] == ["WARNING", "HIGH", "CRITICAL", "CLOSED"]
    assert alert_response.json()["opening_snapshot"]["breached_signals"] == [
        "water_in_oil"
    ]
    assert effectiveness_response.status_code == 200
    effectiveness = effectiveness_response.json()
    assert effectiveness["result"] == "INITIAL_EFFECTIVE"
    assert effectiveness["recovery_confirmed"] is True
    assert effectiveness["approval_status"] == "PENDING_REVIEW"
    assert effectiveness["closure_eligible"] is False
    assert effectiveness["monitoring_periods"] == 5
    assert len(effectiveness["metrics"]) == 4
    assert all(metric["outcome"] == "IMPROVED" for metric in effectiveness["metrics"])
    assert driver_response.status_code == 200
    driver_analysis = driver_response.json()
    assert driver_analysis["method"] == "GROUPED_COUNTERFACTUAL_BASELINE_REPLACEMENT"
    assert len(driver_analysis["contributions"]) == 4
    assert sum(
        contribution["contribution_percent"]
        for contribution in driver_analysis["contributions"]
    ) == pytest.approx(100.0, abs=0.01)
    assert driver_analysis["contributions"][0]["signal_key"] == "water_in_oil"


def test_rca_review_and_action_workflow(client: TestClient) -> None:
    generated = client.post(
        f"/api/v1/alerts/{ALERT_ID}/rca",
        json={"requested_by": "demo-user"},
    )
    assert generated.status_code == 200
    rca = generated.json()
    assert rca["status"] == "AI_DRAFT"
    assert rca["requested_by"] == "demo-user"

    blocked_plan = client.post(
        f"/api/v1/rca/{rca['rca_id']}/action-plans",
        json={"hypothesis_id": "hypothesis-1"},
    )
    assert blocked_plan.status_code == 409
    assert "approved RCA" in blocked_plan.json()["detail"]

    invalid_approval = client.patch(
        f"/api/v1/rca/{rca['rca_id']}/status",
        json={"status": "APPROVED", "actor": "engineer-1", "note": "Skip"},
    )
    assert invalid_approval.status_code == 409

    under_review = client.patch(
        f"/api/v1/rca/{rca['rca_id']}/status",
        json={
            "status": "UNDER_REVIEW",
            "actor": "engineer-1",
            "note": "Review started",
        },
    )
    assert under_review.status_code == 200
    approved = client.patch(
        f"/api/v1/rca/{rca['rca_id']}/status",
        json={
            "status": "APPROVED",
            "actor": "engineer-1",
            "note": "Evidence accepted",
        },
    )
    assert approved.status_code == 200
    assert len(approved.json()["status_history"]) == 2

    plan_response = client.post(
        f"/api/v1/rca/{rca['rca_id']}/action-plans",
        json={"hypothesis_id": "hypothesis-1"},
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert [action["action_type"] for action in plan["actions"]] == [
        "CONTAINMENT",
        "CORRECTIVE",
        "PREVENTIVE",
    ]

    action_id = plan["actions"][0]["action_id"]
    action_response = client.patch(
        f"/api/v1/actions/{action_id}/status",
        json={
            "status": "APPROVED",
            "actor": "operations-1",
            "note": "Authorized",
        },
    )
    assert action_response.status_code == 200
    changed = next(
        action
        for action in action_response.json()["actions"]
        if action["action_id"] == action_id
    )
    assert changed["status"] == "APPROVED"
    assert changed["status_history"][0]["actor"] == "operations-1"


def test_missing_resources_return_404(client: TestClient) -> None:
    assert client.get("/api/v1/assets/missing/overview").status_code == 404
    assert client.get("/api/v1/alerts/missing").status_code == 404
    assert client.get("/api/v1/action-plans/missing").status_code == 404
    assert client.get("/api/v1/data-sources/missing").status_code == 404
    assert client.get("/api/v1/traceability/claims/missing").status_code == 404


def test_traceability_connects_claims_to_governed_sources(client: TestClient) -> None:
    sources_response = client.get("/api/v1/data-sources")
    impact_response = client.get(
        "/api/v1/traceability/claims/production-shortfall"
    )
    rca_response = client.get("/api/v1/traceability/claims/rca-indication")
    recovery_response = client.get(
        "/api/v1/traceability/claims/recovery-effectiveness"
    )

    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 5
    production = next(
        source for source in sources if source["source_key"] == "production_ko_3201"
    )
    assert production["mapping_count"] == 7
    assert production["record_count"] == 720

    assert impact_response.status_code == 200
    impact = impact_response.json()
    assert impact["provenance"] == "CALCULATED"
    assert impact["value"] == "1,762.8"
    assert impact["sources"][0]["source_key"] == "production_ko_3201"
    assert len(impact["preview"]["rows"]) == 8

    assert rca_response.status_code == 200
    rca = rca_response.json()
    assert rca["provenance"] == "RECORDED"
    assert {source["source_key"] for source in rca["sources"]} == {
        "equipment_performance_ko_3201",
        "incident_database",
        "rca_ko_3201",
    }
    assert any(
        issue["flag"] == "SOURCE_DISAGREEMENT"
        for issue in rca["quality_issues"]
    )
    assert recovery_response.status_code == 200
    recovery = recovery_response.json()
    assert recovery["value"] == "Recovery confirmed"
    assert recovery["provenance"] == "CALCULATED"
    assert len(recovery["preview"]["rows"]) == 4
