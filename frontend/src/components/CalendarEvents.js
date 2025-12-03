import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';
import './CalendarEvents.css';

function CalendarEvents() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    try {
      const response = await axios.get('/api/calendar-events');
      if (response.data.events) {
        setEvents(response.data.events);
      } else {
        setError(response.data.message || 'Failed to load calendar events');
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to load calendar events');
      console.error('Error fetching calendar events:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatEventDate = (dateString) => {
    if (!dateString) return 'Date TBD';
    try {
      const date = parseISO(dateString);
      return format(date, 'PPp');
    } catch {
      return dateString;
    }
  };

  if (loading) {
    return <div className="loading">Loading calendar events...</div>;
  }

  if (error) {
    return (
      <div className="calendar-events">
        <div className="card">
          <div className="error">
            {error}
            <br />
            <small>Make sure you have authorized calendar access and have created some events.</small>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="calendar-events">
      <div className="card">
        <h2>Upcoming Calendar Events</h2>
        <p className="events-description">
          Calendar events automatically created from confirmed shortlisting emails.
        </p>
      </div>

      {events.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">📅</div>
            <h3>No upcoming events</h3>
            <p>Calendar events will appear here once confirmed matches create them.</p>
          </div>
        </div>
      ) : (
        <div className="events-list">
          {events.map((event) => (
            <div key={event.id} className="event-item">
              <div className="event-header">
                <h3>{event.summary}</h3>
                <span className="event-date">{formatEventDate(event.start)}</span>
              </div>
              {event.location && (
                <div className="event-detail">
                  <strong>📍 Location:</strong> {event.location}
                </div>
              )}
              {event.description && (
                <div className="event-description">
                  {event.description.split('\n').map((line, idx) => (
                    <div key={idx}>{line}</div>
                  ))}
                </div>
              )}
              {event.htmlLink && (
                <a
                  href={event.htmlLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="view-calendar-link"
                >
                  Open in Google Calendar →
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CalendarEvents;

