"""Prepared KO-3201 RCA used to exercise the governed demo workflow."""

from __future__ import annotations

from services.api.app.schemas.rca import RCAGeneration, RCAProviderResult


class PreparedRCAProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> RCAProviderResult:
        del system_prompt, user_prompt
        generation = RCAGeneration.model_validate(
            {
                "executive_summary": (
                    "Water-in-oil was the earliest persistent condition driver, followed "
                    "by rising bearing temperature and radial vibration. The sequence is "
                    "most consistent with moisture contamination weakening the lubricant "
                    "film and accelerating bearing distress."
                ),
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp-lubrication-contamination",
                        "rank": 1,
                        "category": "LUBRICATION_CONTAMINATION",
                        "title": "Moisture ingress degraded the bearing oil film",
                        "mechanism": (
                            "Water contamination reduced lubricant film strength. Increasing "
                            "friction then raised bearing temperature and radial vibration."
                        ),
                        "confidence": 0.86,
                        "rationale": (
                            "Water-in-oil opened the warning and remained the primary model "
                            "driver. Later bearing indicators form a coherent degradation sequence."
                        ),
                        "supporting_evidence_ids": [
                            "signal:water_in_oil",
                            "signal:bearing_temperature",
                            "signal:radial_vibration",
                        ],
                        "contradicting_evidence_ids": [],
                        "analogue_incident_ids": ["incident-0213", "incident-0355"],
                        "missing_evidence": [
                            "Independent oil moisture result",
                            "Bearing inspection and vibration spectrum",
                        ],
                        "disconfirming_condition": (
                            "Reject if independent oil testing is within specification and "
                            "inspection finds no credible ingress path or bearing distress."
                        ),
                    },
                    {
                        "hypothesis_id": "hyp-bearing-degradation",
                        "rank": 2,
                        "category": "BEARING_DEGRADATION",
                        "title": "Existing bearing wear drove secondary oil deterioration",
                        "mechanism": (
                            "Progressive bearing damage increased vibration and temperature, "
                            "with oil condition degrading as a consequence."
                        ),
                        "confidence": 0.63,
                        "rationale": (
                            "The vibration and temperature pattern resembles prior bearing "
                            "failures, but water-in-oil appeared first."
                        ),
                        "supporting_evidence_ids": [
                            "signal:bearing_temperature",
                            "signal:radial_vibration",
                        ],
                        "contradicting_evidence_ids": ["signal:water_in_oil"],
                        "analogue_incident_ids": ["incident-0213", "incident-0355"],
                        "missing_evidence": ["Bearing clearance measurement"],
                        "disconfirming_condition": (
                            "Reject if spectrum, clearance, and surface inspection show no defect."
                        ),
                    },
                ],
                "investigation_steps": [
                    {
                        "step_id": "step-safe-isolation",
                        "priority": "IMMEDIATE",
                        "instruction": "Preserve the as-found condition and collect a controlled oil sample.",
                        "rationale": "Protects evidence needed to distinguish contamination from wear.",
                        "expected_evidence": "Isolation record and traceable oil sample.",
                        "owner_role": "Shift Supervisor",
                        "safety_gate": True,
                    },
                    {
                        "step_id": "step-oil-analysis",
                        "priority": "IMMEDIATE",
                        "instruction": "Test moisture, cleanliness, viscosity, and wear debris.",
                        "rationale": "Directly tests the leading contamination mechanism.",
                        "expected_evidence": "Independent laboratory oil report.",
                        "owner_role": "Reliability Engineer",
                        "safety_gate": False,
                    },
                    {
                        "step_id": "step-bearing-condition",
                        "priority": "HIGH",
                        "instruction": "Inspect the bearing and compare vibration spectrum to baseline.",
                        "rationale": "Determines whether permanent damage requires repair.",
                        "expected_evidence": "Inspection, clearance, spectrum, and phase results.",
                        "owner_role": "Rotating Equipment Engineer",
                        "safety_gate": True,
                    },
                ],
                "operating_guidance": (
                    "Do not return KO-3201 to normal duty until the contamination source is "
                    "controlled, oil quality is accepted, and a controlled run confirms stable condition."
                ),
                "requires_human_review": True,
            }
        )
        return RCAProviderResult(
            provider="prepared-case",
            model="ko-3201-prepared-rca-v1",
            response_id="prepared-ko-3201-001",
            generation=generation,
        )
