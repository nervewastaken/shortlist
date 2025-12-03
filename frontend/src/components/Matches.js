import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format } from 'date-fns';
import './Matches.css';

function Matches() {
  const [matches, setMatches] = useState({ confirmed: [], possibilities: [], partial: [] });
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('confirmed');

  useEffect(() => {
    fetchMatches();
  }, []);

  const fetchMatches = async () => {
    try {
      const response = await axios.get('/api/matches');
      setMatches(response.data);
    } catch (error) {
      console.error('Error fetching matches:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    try {
      const date = new Date(timestamp * 1000);
      return format(date, 'PPp');
    } catch {
      return 'Unknown';
    }
  };

  const getMatchIcon = (type) => {
    switch (type) {
      case 'CONFIRMED_MATCH':
        return '🎯';
      case 'POSSIBILITY':
        return '🤔';
      case 'PARTIAL_MATCH':
        return '📧';
      default:
        return '❓';
    }
  };

  const renderMatchList = (matchList, type) => {
    if (!matchList || matchList.length === 0) {
      return <div className="empty-state">No {type.toLowerCase()} matches found.</div>;
    }

    return (
      <div className="matches-list">
        {matchList.map((match, index) => (
          <div key={index} className="match-item">
            <div className="match-header">
              <span className="match-icon">{getMatchIcon(type)}</span>
              <div className="match-title">
                <h4>{match.subject || 'No Subject'}</h4>
                <span className="match-time">{formatTimestamp(match.timestamp)}</span>
              </div>
            </div>
            <div className="match-details">
              <div className="match-detail-row">
                <strong>From:</strong> {match.from_display_name || match.from_email}
              </div>
              {match.parsed_name && (
                <div className="match-detail-row">
                  <strong>Parsed Name:</strong> {match.parsed_name}
                </div>
              )}
              {match.parsed_reg && (
                <div className="match-detail-row">
                  <strong>Parsed Reg:</strong> {match.parsed_reg}
                </div>
              )}
              {match.from_email && (
                <div className="match-detail-row">
                  <strong>Email:</strong> {match.from_email}
                </div>
              )}
            </div>
            <a
              href={`https://mail.google.com/mail/u/0/#inbox/${match.message_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="view-email-link"
            >
              View Email →
            </a>
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return <div className="loading">Loading matches...</div>;
  }

  return (
    <div className="matches">
      <div className="card">
        <h2>Email Matches</h2>
        <p className="matches-description">
          View all detected matches from your inbox, categorized by confidence level.
        </p>
      </div>

      <div className="matches-tabs">
        <button
          className={`tab-button ${activeTab === 'confirmed' ? 'active' : ''}`}
          onClick={() => setActiveTab('confirmed')}
        >
          🎯 Confirmed ({matches.confirmed.length})
        </button>
        <button
          className={`tab-button ${activeTab === 'possibilities' ? 'active' : ''}`}
          onClick={() => setActiveTab('possibilities')}
        >
          🤔 Possibilities ({matches.possibilities.length})
        </button>
        <button
          className={`tab-button ${activeTab === 'partial' ? 'active' : ''}`}
          onClick={() => setActiveTab('partial')}
        >
          📧 Partial ({matches.partial.length})
        </button>
      </div>

      <div className="card">
        {activeTab === 'confirmed' && renderMatchList(matches.confirmed, 'CONFIRMED_MATCH')}
        {activeTab === 'possibilities' && renderMatchList(matches.possibilities, 'POSSIBILITY')}
        {activeTab === 'partial' && renderMatchList(matches.partial, 'PARTIAL_MATCH')}
      </div>
    </div>
  );
}

export default Matches;

