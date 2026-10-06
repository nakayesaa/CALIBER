/** Read-only guidance when the GM has no submitted case to inspect. */
export function GmFlowReference() {
  const sections = [
    ['gm-equipment', 'Review verified equipment evidence', 'The submitted packet should contain operator-verified condition readings, engineering limits, and inspection references. Check discrepancies and missing evidence before relying on the proposed response.'],
    ['gm-production', 'Review verified production impact', 'The production report should preserve its time window, units, baseline, and source. Distinguish calculated feed shortfall from source-reported production loss and downtime.'],
    ['gm-rca', 'Separate probable causes from findings', 'Review supporting, contradicting, and outstanding evidence. A model-supported hypothesis is not a confirmed physical mechanism; operator verification of data does not prove causality.'],
    ['gm-actions', 'Assess the proposed follow-up', 'Check that proposed corrective and preventive actions address the reported mechanism, include completion evidence, and identify the responsible role. A proposal is not assigned work.'],
    ['gm-decision', 'Record a management decision', 'For a real submitted case, approve the proposed response or return it with specific revisions and a rationale. This reference does not submit or save a decision.'],
    ['gm-handoff', 'Keep assignment separate from approval', 'After the required approval, the supervisor assigns the owner, deadline, guidance, and evidence requirements. Execution and effectiveness verification remain separate; approval does not automatically assign work.'],
  ];
  return <div className="gm-flow-reference">
    <section className="production-review-card" role="note">
      <h2>Flow reference · no submitted case</h2>
      <p>No management report is available in this inbox. These guidance cards explain the review requirements, not actual KO-3201 findings, verification statuses, or decisions.</p>
    </section>
    {sections.map(([anchor, title, text]) => <section className="production-review-card" data-flow={anchor} key={anchor}>
      <span>Flow reference · no submitted case</span>
      <h2>{title}</h2><p>{text}</p>
    </section>)}
  </div>;
}
