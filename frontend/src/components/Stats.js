import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Stats.css';

function Stats() {
  const [stats, setStats] = useState(null);
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const response = await axios.get('/api/state');
      setStats(response.data.stats);
      setState(response.data.state);
    } catch (error) {
      console.error('Error fetching stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading statistics...</div>;
  }

  if (!stats) {
    return <div className="error">Failed to load statistics</div>;
  }

  const totalMatches = stats.confirmed_count + stats.possibilities_count + stats.partial_count;
  const confirmedPercentage = totalMatches > 0 
    ? ((stats.confirmed_count / totalMatches) * 100).toFixed(1) 
    : 0;

  return (
    <div className="stats">
      <div className="card">
        <h2>Statistics Overview</h2>
        <p className="stats-description">
          Comprehensive statistics about your email matches and system activity.
        </p>
      </div>

      <div className="stats-grid-large">
        <div className="stat-card-large total">
          <div className="stat-icon-large">📊</div>
          <div className="stat-value-large">{totalMatches}</div>
          <div className="stat-label-large">Total Matches</div>
        </div>
        <div className="stat-card-large confirmed">
          <div className="stat-icon-large">🎯</div>
          <div className="stat-value-large">{stats.confirmed_count}</div>
          <div className="stat-label-large">Confirmed</div>
          <div className="stat-percentage">{confirmedPercentage}%</div>
        </div>
        <div className="stat-card-large possibility">
          <div className="stat-icon-large">🤔</div>
          <div className="stat-value-large">{stats.possibilities_count}</div>
          <div className="stat-label-large">Possibilities</div>
        </div>
        <div className="stat-card-large partial">
          <div className="stat-icon-large">📧</div>
          <div className="stat-value-large">{stats.partial_count}</div>
          <div className="stat-label-large">Partial</div>
        </div>
      </div>

      <div className="card">
        <h3>Match Distribution</h3>
        <div className="distribution-chart">
          <div className="chart-bar">
            <div className="chart-label">
              <span>Confirmed</span>
              <span>{stats.confirmed_count}</span>
            </div>
            <div className="chart-bar-container">
              <div 
                className="chart-bar-fill confirmed"
                style={{ width: `${totalMatches > 0 ? (stats.confirmed_count / totalMatches) * 100 : 0}%` }}
              ></div>
            </div>
          </div>
          <div className="chart-bar">
            <div className="chart-label">
              <span>Possibilities</span>
              <span>{stats.possibilities_count}</span>
            </div>
            <div className="chart-bar-container">
              <div 
                className="chart-bar-fill possibility"
                style={{ width: `${totalMatches > 0 ? (stats.possibilities_count / totalMatches) * 100 : 0}%` }}
              ></div>
            </div>
          </div>
          <div className="chart-bar">
            <div className="chart-label">
              <span>Partial</span>
              <span>{stats.partial_count}</span>
            </div>
            <div className="chart-bar-container">
              <div 
                className="chart-bar-fill partial"
                style={{ width: `${totalMatches > 0 ? (stats.partial_count / totalMatches) * 100 : 0}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>System Information</h3>
        <div className="info-grid">
          <div className="info-item">
            <strong>Last Processed Email ID:</strong>
            <span>{state?.last_message_id || 'None'}</span>
          </div>
          <div className="info-item">
            <strong>Total Confirmed Matches:</strong>
            <span>{stats.confirmed_count}</span>
          </div>
          <div className="info-item">
            <strong>Total Possibilities:</strong>
            <span>{stats.possibilities_count}</span>
          </div>
          <div className="info-item">
            <strong>Total Partial Matches:</strong>
            <span>{stats.partial_count}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Stats;

