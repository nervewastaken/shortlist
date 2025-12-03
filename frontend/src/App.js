import React, { useState, useEffect } from 'react';
import './App.css';
import Dashboard from './components/Dashboard';
import Profile from './components/Profile';
import Matches from './components/Matches';
import CalendarEvents from './components/CalendarEvents';
import Stats from './components/Stats';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    try {
      const response = await fetch('/api/profile');
      const data = await response.json();
      setProfile(data);
    } catch (error) {
      console.error('Error fetching profile:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner"></div>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="App">
      <header className="app-header">
        <h1>📋 Shortlist</h1>
        <p className="subtitle">Campus Placement Email Monitor</p>
      </header>

      <nav className="app-nav">
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          📊 Dashboard
        </button>
        <button
          className={activeTab === 'profile' ? 'active' : ''}
          onClick={() => setActiveTab('profile')}
        >
          👤 Profile
        </button>
        <button
          className={activeTab === 'matches' ? 'active' : ''}
          onClick={() => setActiveTab('matches')}
        >
          🎯 Matches
        </button>
        <button
          className={activeTab === 'calendar' ? 'active' : ''}
          onClick={() => setActiveTab('calendar')}
        >
          📅 Calendar
        </button>
        <button
          className={activeTab === 'stats' ? 'active' : ''}
          onClick={() => setActiveTab('stats')}
        >
          📈 Stats
        </button>
      </nav>

      <main className="app-main">
        {activeTab === 'dashboard' && <Dashboard profile={profile} />}
        {activeTab === 'profile' && <Profile profile={profile} onUpdate={fetchProfile} />}
        {activeTab === 'matches' && <Matches />}
        {activeTab === 'calendar' && <CalendarEvents />}
        {activeTab === 'stats' && <Stats />}
      </main>
    </div>
  );
}

export default App;

