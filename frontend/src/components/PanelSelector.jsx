import { useState } from 'react';
import './PanelSelector.css';

export default function PanelSelector({
  panel,
  availableAdvisors,
  availableModels,
  question,
  onConfirm,
  onCancel,
  autoAccept,
  onAutoAcceptChange,
}) {
  const [editedPanel, setEditedPanel] = useState(panel);
  const [showSwap, setShowSwap] = useState(null); // index of advisor being swapped

  const handleRemoveAdvisor = (index) => {
    if (editedPanel.length <= 3) return; // minimum 3
    setEditedPanel(editedPanel.filter((_, i) => i !== index));
  };

  const handleSwapAdvisor = (index, newAdvisorId) => {
    const advisor = availableAdvisors.find(a => a.id === newAdvisorId);
    if (!advisor) return;
    const updated = [...editedPanel];
    updated[index] = {
      ...updated[index],
      advisor_id: advisor.id,
      reasoning: 'manually selected',
    };
    setEditedPanel(updated);
    setShowSwap(null);
  };

  const handleChangeModel = (index, newModel) => {
    const updated = [...editedPanel];
    updated[index] = { ...updated[index], model: newModel };
    setEditedPanel(updated);
  };

  const handleAddAdvisor = (advisorId) => {
    if (editedPanel.length >= 5) return; // maximum 5
    const advisor = availableAdvisors.find(a => a.id === advisorId);
    if (!advisor) return;
    // Pick a model not yet used if possible
    const usedModels = editedPanel.map(p => p.model);
    const unusedModel = availableModels.find(m => !usedModels.includes(m)) || availableModels[0];
    setEditedPanel([
      ...editedPanel,
      { advisor_id: advisor.id, model: unusedModel, reasoning: 'manually added' },
    ]);
  };

  const selectedIds = new Set(editedPanel.map(p => p.advisor_id));
  const unselectedAdvisors = availableAdvisors.filter(a => !selectedIds.has(a.id));

  const getAdvisorName = (advisorId) => {
    const a = availableAdvisors.find(a => a.id === advisorId);
    return a?.name || advisorId;
  };

  const getAdvisorRole = (advisorId) => {
    const a = availableAdvisors.find(a => a.id === advisorId);
    return a?.role || '';
  };

  return (
    <div className="panel-selector-overlay">
      <div className="panel-selector">
        <div className="panel-header">
          <h3>Advisory Panel</h3>
          <p className="panel-question">"{question?.slice(0, 100)}{question?.length > 100 ? '...' : ''}"</p>
        </div>

        <div className="panel-members">
          {editedPanel.map((member, index) => (
            <div key={member.advisor_id} className="panel-member">
              <div className="member-info">
                <div className="member-name">
                  {getAdvisorName(member.advisor_id)}
                  <button
                    className="swap-btn"
                    onClick={() => setShowSwap(showSwap === index ? null : index)}
                    title="Swap advisor"
                  >
                    &#x21c4;
                  </button>
                  {editedPanel.length > 3 && (
                    <button
                      className="remove-btn"
                      onClick={() => handleRemoveAdvisor(index)}
                      title="Remove advisor"
                    >
                      &times;
                    </button>
                  )}
                </div>
                <div className="member-role">{getAdvisorRole(member.advisor_id)}</div>
                {member.reasoning && member.reasoning !== 'fallback selection' && member.reasoning !== 'manually selected' && member.reasoning !== 'manually added' && (
                  <div className="member-reasoning">{member.reasoning}</div>
                )}
              </div>
              <select
                className="model-select"
                value={member.model}
                onChange={(e) => handleChangeModel(index, e.target.value)}
              >
                {availableModels.map(m => (
                  <option key={m} value={m}>{m.split('/')[1] || m}</option>
                ))}
              </select>

              {showSwap === index && (
                <div className="swap-dropdown">
                  {unselectedAdvisors.map(a => (
                    <button
                      key={a.id}
                      className="swap-option"
                      onClick={() => handleSwapAdvisor(index, a.id)}
                    >
                      <span className="swap-name">{a.name}</span>
                      <span className="swap-role">{a.role}</span>
                      {a.tags && <span className="swap-tags">{a.tags.slice(0, 3).join(', ')}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {editedPanel.length < 5 && unselectedAdvisors.length > 0 && (
          <div className="add-advisor">
            <select
              className="add-advisor-select"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) handleAddAdvisor(e.target.value);
                e.target.value = '';
              }}
            >
              <option value="" disabled>+ Add advisor...</option>
              {unselectedAdvisors.map(a => (
                <option key={a.id} value={a.id}>{a.name} — {a.role}</option>
              ))}
            </select>
          </div>
        )}

        <div className="panel-actions">
          <label className="auto-accept-toggle">
            <input
              type="checkbox"
              checked={autoAccept}
              onChange={(e) => onAutoAcceptChange(e.target.checked)}
            />
            Auto-accept panels
          </label>
          <div className="panel-buttons">
            <button className="cancel-btn" onClick={onCancel}>Cancel</button>
            <button className="confirm-btn" onClick={() => onConfirm(editedPanel)}>
              Deliberate ({editedPanel.length} advisors)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
