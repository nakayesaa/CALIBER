import type { ReactNode } from 'react';

export function VerificationDocument({ title, subtitle, fields, footer, children }: {
  title: string; subtitle: string; fields: string[][]; footer: ReactNode; children: ReactNode;
}) {
  return <section className="production-report-wrap" aria-label={title}>
    <div className="production-report-toolbar"><span>Scope evidence · versioned verification report</span><div><small>PDF: turn off browser Headers and footers.</small><button type="button" onClick={() => window.print()}>Save as PDF</button></div></div>
    <article className="production-document action-report-paper" aria-label={title}>
      <header className="action-report-heading"><h2>{title}</h2><p>{subtitle}</p></header>
      <dl className="capa-document-control">{fields.map(([label, value]) => <div className="capa-document-field" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {children}
      <footer className="action-report-footnote">{footer}</footer>
    </article>
  </section>;
}

export function VerificationReportSection({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return <section className="capa-report-section"><header><span>{number}</span><h3>{title}</h3></header><div>{children}</div></section>;
}
