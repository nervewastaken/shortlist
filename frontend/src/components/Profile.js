import React from 'react';
import './Profile.css';

function Profile({ profile, onUpdate }) {
  if (!profile) {
    return <div className="loading">Loading profile...</div>;
  }

  return (
    <div className="profile">
      <div className="card">
        <h2>Your Profile</h2>
        
        <div className="profile-section">
          <h3>Personal Information</h3>
          <div className="profile-field">
            <label>Name</label>
            <div className="profile-value">
              {profile.name || <span className="empty">Not set</span>}
            </div>
          </div>
          
          <div className="profile-field">
            <label>Registration Number</label>
            <div className="profile-value">
              {profile.registration_number || <span className="empty">Not set</span>}
            </div>
          </div>
          
          <div className="profile-field">
            <label>Gmail Address</label>
            <div className="profile-value">{profile.gmail_address || 'Not available'}</div>
          </div>
          
          <div className="profile-field">
            <label>Personal Email</label>
            <div className="profile-value">
              {profile.personal_email || <span className="empty">Not set</span>}
            </div>
          </div>
          
          <div className="profile-field">
            <label>Phone Number</label>
            <div className="profile-value">
              {profile.phone_number || <span className="empty">Not set</span>}
            </div>
          </div>
        </div>

        <div className="profile-section">
          <h3>Account Information</h3>
          <div className="profile-field">
            <label>Google Display Name</label>
            <div className="profile-value">
              {profile.google_account_display_name || profile.gmail_display_name || 'Not available'}
            </div>
          </div>
        </div>

        <div className="info-box">
          <p><strong>Note:</strong> Your profile information is automatically extracted from your Google account and emails. 
          Name and registration number are parsed from email headers when available.</p>
        </div>
      </div>
    </div>
  );
}

export default Profile;

