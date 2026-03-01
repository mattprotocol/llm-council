import { useState } from 'react';
import './UsageBanner.css';

function formatCost(cost) {
  if (cost === undefined || cost === null) return '$0.00';
  if (cost > 0 && cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(3)}`;
}

function formatTokens(tokens) {
  if (!tokens) return '0';
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return tokens.toString();
}

export default function UsageBanner({ usage, isStreaming }) {
  const [expanded, setExpanded] = useState(false);

  if (!usage) return null;

  const total = usage.total || usage.running_total || {};
  const byStage = usage.by_stage || {};
  const hasCost = total.cost > 0 || total.total_tokens > 0;

  if (!hasCost && !isStreaming) return null;

  const stageOrder = ['classification', 'routing', 'direct', 'stage1', 'stage2', 'stage3', 'title'];
  const stageLabels = {
    classification: 'Classification',
    routing: 'Routing',
    direct: 'Direct Response',
    stage1: 'Stage 1',
    stage2: 'Stage 2',
    stage3: 'Stage 3',
    title: 'Title Gen',
  };

  return (
    <div className={`usage-banner ${isStreaming ? 'streaming' : ''}`}>
      <div className="usage-summary" onClick={() => setExpanded(!expanded)}>
        <span className="usage-cost">{formatCost(total.cost)}</span>
        <span className="usage-separator">|</span>
        <span className="usage-tokens">{formatTokens(total.total_tokens)} tokens</span>
        <span className="usage-separator">|</span>
        <span className="usage-calls">{total.calls || 0} calls</span>
        {Object.keys(byStage).length > 0 && (
          <span className="usage-expand">{expanded ? '▾' : '▸'} Details</span>
        )}
        {isStreaming && <span className="usage-live-dot" />}
      </div>
      {expanded && Object.keys(byStage).length > 0 && (
        <div className="usage-breakdown">
          <table className="usage-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Cost</th>
                <th>Tokens</th>
                <th>Calls</th>
              </tr>
            </thead>
            <tbody>
              {stageOrder
                .filter(s => byStage[s])
                .map(stage => (
                  <tr key={stage}>
                    <td className="stage-name">{stageLabels[stage] || stage}</td>
                    <td className="stage-cost">{formatCost(byStage[stage].cost)}</td>
                    <td className="stage-tokens">{formatTokens(byStage[stage].total_tokens)}</td>
                    <td className="stage-calls">{byStage[stage].calls}</td>
                  </tr>
                ))}
            </tbody>
            <tfoot>
              <tr className="usage-total-row">
                <td>Total</td>
                <td>{formatCost(total.cost)}</td>
                <td>{formatTokens(total.total_tokens)}</td>
                <td>{total.calls || 0}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
