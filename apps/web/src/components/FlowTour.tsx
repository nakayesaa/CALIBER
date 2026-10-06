import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { cardPosition, FLOW_STEPS } from '../lib/flowTour';
import './flow-tour.css';

export function FlowTour({ index, page, onNext, onBack, onExit }: { index: number; page: string; onNext: () => void; onBack: () => void; onExit: () => void }) {
  const step = FLOW_STEPS[index];
  const dialog = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<DOMRect | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [position, setPosition] = useState({ left: 12, top: 12 });
  useEffect(() => {
    const toolbar = document.querySelector<HTMLElement>('.demo-session');
    if (!toolbar) return;
    const wasInert = toolbar.inert;
    toolbar.inert = true;
    return () => { toolbar.inert = wasInert; };
  }, []);
  useEffect(() => {
    setBox(null); setWaiting(false);
    let current: HTMLElement | null = null;
    const update = () => {
      const target = Array.from(document.querySelectorAll<HTMLElement>(step.selector)).find(node => {
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      });
      if (target !== current && target) { current = target; target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }); }
      const rect = target?.getBoundingClientRect();
      setBox(rect && rect.width > 0 && rect.height > 0 ? rect : null);
    };
    const observer = new MutationObserver(update);
    const app = document.querySelector('[data-flow-app]');
    if (app) observer.observe(app, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'data-flow'] });
    const timer = window.setTimeout(() => setWaiting(true), 8000);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    update();
    return () => { observer.disconnect(); window.clearTimeout(timer); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true); };
  }, [step, page]);
  useLayoutEffect(() => {
    const measure = () => {
      const node = dialog.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      setPosition(box ? cardPosition(box, innerWidth, innerHeight, rect.width, rect.height) : { left: Math.max(12, (innerWidth - rect.width) / 2), top: Math.max(12, (innerHeight - rect.height) / 2) });
    };
    const observer = new ResizeObserver(measure);
    if (dialog.current) observer.observe(dialog.current);
    measure();
    return () => observer.disconnect();
  }, [box]);
  useEffect(() => {
    const initialFocus = dialog.current?.querySelector<HTMLElement>('[data-flow-next]:not(:disabled)') ?? dialog.current?.querySelector<HTMLElement>('button');
    initialFocus?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onExit(); }
      if (event.key !== 'Tab') return;
      const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      event.preventDefault();
      buttons[(current + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length]?.focus();
    };
    document.addEventListener('keydown', keydown, true);
    return () => document.removeEventListener('keydown', keydown, true);
  }, [index, onExit, box !== null]);
  return <div className="flow-tour-layer">
    <div className="flow-tour-shield" aria-hidden="true" />
    {box && <div className="flow-tour-spotlight" aria-hidden="true" style={{ left: box.left - 6, top: box.top - 6, width: box.width + 12, height: box.height + 12 }} />}
    {!box && <div className="flow-tour-waiting-mask" aria-hidden="true" />}
    <div ref={dialog} className="flow-tour-card" role="dialog" aria-modal="true" aria-labelledby="flow-tour-title" aria-describedby="flow-tour-description" style={position}>
      <div className="flow-tour-top"><span>FLOW · KO-3201</span><button type="button" onClick={onExit} aria-label="Exit Flow tour">×</button></div>
      <p className="flow-tour-counter">Step {index + 1} of {FLOW_STEPS.length} · Guided walkthrough</p>
      <h2 id="flow-tour-title">{step.title}</h2>
      <p id="flow-tour-description">{step.text}</p>
      {!box && <p className="flow-tour-status" role="status">{waiting ? 'This view is not ready. You can exit, check the connection, and start Flow again.' : 'Waiting for the view to load…'}</p>}
      <div className="flow-tour-progress" aria-hidden="true">{FLOW_STEPS.map((_, i) => <span key={i} className={i <= index ? 'active' : ''} />)}</div>
      <footer><button type="button" onClick={index ? onBack : onExit}>{index ? 'Back' : 'Exit tour'}</button><button type="button" data-flow-next disabled={!box} onClick={onNext}>{step.next} <span aria-hidden="true">→</span></button></footer>
    </div>
  </div>;
}
