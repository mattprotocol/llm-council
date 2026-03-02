import './ExecutionModeToggle.css';

const MODES = [
  { id: 'chat', label: 'Chat', desc: 'Stage 1 only — individual responses' },
  { id: 'ranked', label: 'Ranked', desc: 'Stages 1+2 — responses + peer ranking' },
  { id: 'full', label: 'Full', desc: 'All 3 stages — full deliberation' },
];

export default function ExecutionModeToggle({ mode, onChange, disabled }) {
  return (
    <div className="execution-mode-toggle">
      <span className="toggle-label">Mode:</span>
      <div className="toggle-group">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`toggle-btn ${mode === m.id ? 'active' : ''}`}
            onClick={() => onChange(m.id)}
            disabled={disabled}
            title={m.desc}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}
