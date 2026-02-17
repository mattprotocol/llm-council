import { useState, useEffect } from 'react';
import './CouncilSelector.css';

function CouncilSelector({ councils, selectedCouncil, onSelectCouncil, isLoading }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const selected = councils.find(c => c.id === selectedCouncil) || councils[0];

  return (
    <div className="council-selector">
      <button
        className="council-selector-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        disabled={isLoading}
      >
        <div className="council-selector-current">
          <span className="council-name">{selected?.name || 'Select Council'}</span>
          <span className="council-description">{selected?.description || ''}</span>
        </div>
        <span className={`council-chevron ${isExpanded ? 'expanded' : ''}`}>▾</span>
      </button>

      {isExpanded && (
        <div className="council-dropdown">
          {councils.map(council => (
            <button
              key={council.id}
              className={`council-option ${council.id === selectedCouncil ? 'selected' : ''}`}
              onClick={() => {
                onSelectCouncil(council.id);
                setIsExpanded(false);
              }}
            >
              <div className="council-option-name">{council.name}</div>
              <div className="council-option-description">{council.description}</div>
              {council.personas && (
                <div className="council-option-personas">
                  {council.personas.map((p, i) => (
                    <span key={i} className="persona-tag">{p.role}</span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default CouncilSelector;
