"""Prepared heat-exchanger hypotheses grounded in the opening evidence package."""

from __future__ import annotations

import json

from services.api.app.schemas.rca import RCAGeneration, RCAProviderResult


class PreparedHERCAProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> RCAProviderResult:
        del system_prompt
        payload = json.loads(user_prompt)
        signals = [item for item in payload["allowed_evidence_ids"] if item.startswith("signal:")]
        evidence = signals or payload["allowed_evidence_ids"][:1]
        analogues = payload["allowed_incident_ids"][:3]
        hypotheses = []
        for rank, category, title, mechanism, rationale in [
            (
                1,
                "FOULING",
                "Possible tube-side fouling",
                "Deposits can increase hydraulic resistance and reduce heat transfer.",
                "The opening condition indicators warrant checking hydraulic and thermal performance together. Fouling remains a hypothesis until inspection evidence is available.",
            ),
            (
                2,
                "UNDETERMINED",
                "Changed process conditions or measurement error",
                "Feed properties, flow, thermal boundary conditions, or instrument error can change exchanger indicators without deposits.",
                "The opening measurements alone cannot distinguish deposits from changed duty or a measurement problem.",
            ),
        ]:
            hypotheses.append(
                {
                    "hypothesis_id": f"hyp-he-{category.lower()}",
                    "rank": rank,
                    "category": category,
                    "title": title,
                    "mechanism": mechanism,
                    "confidence": 0.5,
                    "rationale": rationale
                    + " The prepared confidence value is an uncalibrated ranking placeholder, not a probability.",
                    "supporting_evidence_ids": evidence,
                    "contradicting_evidence_ids": [],
                    "analogue_incident_ids": analogues,
                    "missing_evidence": [
                        "As-found bundle inspection",
                        "Flow and temperature instrument checks",
                        "Feed quality and upstream operating history",
                    ],
                    "disconfirming_condition": "Reject fouling if inspection finds a clean bundle and corrected operating conditions or instrumentation explain the deviation."
                    if rank == 1
                    else "Reject this alternative only after measurements and operating conditions are verified and deposits explain the observed trend.",
                }
            )
        generation = RCAGeneration.model_validate(
            {
                "executive_summary": "HE-3301 condition measurements support a thermal and hydraulic performance investigation. Fouling is a plausible mechanism; the opening package does not establish a physical root cause.",
                "hypotheses": hypotheses,
                "investigation_steps": [
                    {
                        "step_id": "he-trend-review",
                        "priority": "IMMEDIATE",
                        "instruction": "Cross-check pressure drop, thermal duty and flow against the operating record.",
                        "rationale": "Separate process changes from exchanger deterioration.",
                        "expected_evidence": "Time-aligned trend and instrument comparison.",
                        "owner_role": "Process Engineer",
                        "safety_gate": False,
                    },
                    {
                        "step_id": "he-inspection",
                        "priority": "HIGH",
                        "instruction": "Inspect the exchanger bundle under the approved maintenance procedure.",
                        "rationale": "Physical evidence tests the fouling hypothesis.",
                        "expected_evidence": "As-found inspection and deposit description.",
                        "owner_role": "Static Equipment Engineer",
                        "safety_gate": True,
                    },
                ],
                "operating_guidance": "Agree operating restrictions with the shift supervisor; compare post-cleaning condition readings before accepting effectiveness.",
                "requires_human_review": True,
            }
        )
        return RCAProviderResult(
            provider="prepared-case",
            model="he-3301-prepared-rca-v1",
            response_id="prepared-he-3301-001",
            generation=generation,
        )
