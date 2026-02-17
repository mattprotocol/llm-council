import { useState, useEffect } from 'react';
import './LeaderboardView.css';

function LeaderboardView({ councils, onClose }) {
  const [leaderboards, setLeaderboards] = useState({});
  const [selectedCouncil, setSelectedCouncil] = useState('all');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadLeaderboards();
  }, []);

  const loadLeaderboards = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/leaderboard');
      if (response.ok) {
        const data = await response.json();
        setLeaderboards(data);
      }
    } catch (err) {
      console.error('Failed to load leaderboards:', err);
    }
    setIsLoading(false);
  };

  const getDisplayData = () => {
    if (selectedCouncil === 'all') {
      // Aggregate across all councils
      const aggregated = {};
      for (const [councilId, entries] of Object.entries(leaderboards)) {
        for (const entry of entries) {
          if (!aggregated[entry.model]) {
            aggregated[entry.model] = {
              model: entry.model,
              wins: 0,
              participations: 0,
              total_score: 0,
            };
          }
          aggregated[entry.model].wins += entry.wins;
          aggregated[entry.model].participations += entry.participations;
          aggregated[entry.model].total_score += entry.avg_score * entry.participations;
        }
      }
      return Object.values(aggregated)
        .map(a => ({
          ...a,
          win_rate: a.participations > 0 ? (a.wins / a.participations * 100).toFixed(1) : 0,
          avg_score: a.participations > 0 ? (a.total_score / a.participations).toFixed(2) : 0,
        }))
        .sort((a, b) => b.win_rate - a.win_rate);
    }
    return leaderboards[selectedCouncil] || [];
  };

  const displayData = getDisplayData();

  return (
    <div className="leaderboard-view">
      <div className="leaderboard-header">
        <h2>Model Leaderboard</h2>
        <button className="leaderboard-close" onClick={onClose}>&#x2715;</button>
      </div>

      <div className="leaderboard-tabs">
        <button
          className={`lb-tab ${selectedCouncil === 'all' ? 'active' : ''}`}
          onClick={() => setSelectedCouncil('all')}
        >
          All
        </button>
        {councils.map(c => (
          <button
            key={c.id}
            className={`lb-tab ${selectedCouncil === c.id ? 'active' : ''}`}
            onClick={() => setSelectedCouncil(c.id)}
          >
            {c.name}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="leaderboard-loading">Loading...</div>
      ) : displayData.length === 0 ? (
        <div className="leaderboard-empty">No data yet. Start using councils to build the leaderboard.</div>
      ) : (
        <table className="leaderboard-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Model</th>
              <th>Win Rate</th>
              <th>Wins</th>
              <th>Games</th>
              <th>Avg Score</th>
            </tr>
          </thead>
          <tbody>
            {displayData.map((entry, i) => (
              <tr key={entry.model}>
                <td className="lb-rank">{i + 1}</td>
                <td className="lb-model">{entry.model.split('/').pop()}</td>
                <td className="lb-winrate">{entry.win_rate}%</td>
                <td>{entry.wins}</td>
                <td>{entry.participations}</td>
                <td>{entry.avg_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default LeaderboardView;
