import { useMemo } from 'react';
import './CouncilGrid.css';

/**
 * Visual grid showing each council member's state during deliberation.
 * Derives member state from stage1/stage2 progress and streaming data.
 *
 * States: idle → thinking → done → ranking → ranked
 */
export default function CouncilGrid({ stage1, stage2, streaming, progress, panel, executionMode }) {
  const members = useMemo(() => {
    if (!panel || panel.length === 0) return [];

    return panel.map((p) => {
      const model = p.model || p.advisor_id || '';
      const shortName = model.split('/')[1] || model;
      const role = p.role || p.name || '';

      // Determine state from streaming/progress data
      let state = 'idle';
      let stageLabel = '';

      // Check stage1 state
      const s1Streaming = streaming?.stage1?.[model];
      const s1Complete = stage1?.find(r => r.model === model);

      if (s1Streaming?.isStreaming && !s1Complete) {
        state = 'thinking';
        stageLabel = 'Responding...';
      } else if (s1Complete) {
        state = 'done';
        stageLabel = 'Response ready';
      }

      // Check stage2 state (only if past stage1)
      if (executionMode !== 'chat' && s1Complete) {
        const s2Streaming = streaming?.stage2?.[model];
        const s2Complete = stage2?.find(r => r.model === model);

        if (s2Streaming?.isStreaming && !s2Complete) {
          state = 'ranking';
          stageLabel = 'Ranking peers...';
        } else if (s2Complete) {
          state = 'ranked';
          stageLabel = 'Ranking done';
        }
      }

      return { model, shortName, role, state, stageLabel };
    });
  }, [panel, stage1, stage2, streaming, executionMode]);

  if (members.length === 0) return null;

  return (
    <div className="council-grid">
      {members.map((m) => (
        <div key={m.model} className={`grid-card ${m.state}`}>
          <div className="card-avatar">
            {m.state === 'thinking' || m.state === 'ranking' ? (
              <div className="card-spinner" />
            ) : m.state === 'done' || m.state === 'ranked' ? (
              <span className="card-check">{'\u2713'}</span>
            ) : (
              <span className="card-dot">{'\u25CB'}</span>
            )}
          </div>
          <div className="card-name" title={m.model}>{m.shortName}</div>
          {m.role && <div className="card-role">{m.role}</div>}
          {m.stageLabel && <div className="card-stage">{m.stageLabel}</div>}
        </div>
      ))}
    </div>
  );
}
