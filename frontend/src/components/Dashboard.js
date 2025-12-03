import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Dashboard.css';

function Dashboard({ profile }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const response = await axios.get('/api/state');
      setStats(response.data.stats);
    } catch (error) {
      console.error('Error fetching stats:', error);
      setMessage({ type: 'error', text: 'Failed to load statistics' });
    } finally {
      setLoading(false);
    }
  };

  const handleCheckEmail = async () => {
    setChecking(true);
    setMessage(null);
    try {
      const response = await axios.post('/api/check-email');
      if (response.data.success) {
        setMessage({ type: 'success', text: response.data.message });
        fetchStats(); // Refresh stats
      } else {
        setMessage({ type: 'info', text: response.data.message });
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.message || 'Failed to check email' });
    } finally {
      setChecking(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading dashboard...</div>;
  }

  return (
    <div className="dashboard">
      <div className="card">
        <h2>Welcome, {profile?.name || profile?.gmail_address || 'User'}!</h2>
        <p className="welcome-text">
          Monitor your campus placement shortlisting emails and track your matches.
        </p>
      </div>

      {message && (
        <div className={`message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="card">
        <h3>Quick Actions</h3>
        <button
          className="btn btn-primary"
          onClick={handleCheckEmail}
          disabled={checking}
        >
          {checking ? 'Checking...' : '🔍 Check Latest Email'}
        </button>
      </div>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card confirmed">
            <div className="stat-icon">🎯</div>
            <div className="stat-value">{stats.confirmed_count}</div>
            <div className="stat-label">Confirmed Matches</div>
          </div>
          <div className="stat-card possibility">
            <div className="stat-icon">🤔</div>
            <div className="stat-value">{stats.possibilities_count}</div>
            <div className="stat-label">Possibilities</div>
          </div>
          <div className="stat-card partial">
            <div className="stat-icon">📧</div>
            <div className="stat-value">{stats.partial_count}</div>
            <div className="stat-label">Partial Matches</div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>How it works</h3>
        <ul className="info-list">
          <li>📧 The system monitors your Gmail inbox for placement emails</li>
          <li>🎯 Matches are detected based on your name and registration number</li>
          <li>📅 Confirmed matches automatically create calendar events</li>
          <li>📊 View detailed statistics and matches in the respective tabs</li>
        </ul>
      </div>
    </div>
  );
}

export default Dashboard;

