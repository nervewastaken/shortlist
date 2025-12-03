# Frontend Application Setup Guide

This guide will help you set up and run the frontend application for the Shortlist project.

## Overview

The frontend is a React application that provides a web interface for:
- Viewing your profile and match statistics
- Browsing detected email matches
- Viewing calendar events
- Manually triggering email checks

## Prerequisites

1. **Node.js and npm**: Install Node.js 16 or higher from [nodejs.org](https://nodejs.org/)
2. **Python Backend**: Make sure the Flask API backend is set up (see main README)

## Quick Start

### 1. Install Frontend Dependencies

Navigate to the frontend directory and install dependencies:

```bash
cd frontend
npm install
```

### 2. Start the Backend API

In a separate terminal, start the Flask API:

```bash
# From project root
python -m app.api
```

The API will run on `http://localhost:5000`

### 3. Start the Frontend

In the frontend directory:

```bash
npm start
```

The frontend will automatically open in your browser at `http://localhost:3000`

## Running Both Services

### Option 1: Separate Terminals (Recommended)

**Terminal 1 - Backend:**
```bash
python -m app.api
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm start
```

### Option 2: Using a Process Manager

You can use tools like `concurrently` or `foreman` to run both services together.

## Features

### Dashboard
- Quick overview of your matches
- Statistics cards showing confirmed, possibilities, and partial matches
- Manual email check button

### Profile
- View your profile information
- See name, registration number, email addresses
- Display information extracted from Google account

### Matches
- Browse all detected matches
- Filter by match type (Confirmed, Possibilities, Partial)
- View email details and open emails in Gmail

### Calendar
- View upcoming calendar events
- Events automatically created from confirmed matches
- Open events in Google Calendar

### Stats
- Detailed statistics
- Match distribution charts
- System information

## Troubleshooting

### Frontend won't start
- Make sure Node.js is installed: `node --version`
- Delete `node_modules` and `package-lock.json`, then run `npm install` again

### API connection errors
- Ensure the Flask backend is running on port 5000
- Check browser console for CORS errors
- Verify the proxy setting in `frontend/package.json`

### No data showing
- Make sure you've run the backend runner at least once to process emails
- Check that `state.json` and `profile.json` exist in the project root
- Verify API endpoints are working by visiting `http://localhost:5000/api/health`

## Development

### Making Changes

The frontend uses React with hot-reloading. Changes to source files will automatically refresh the browser.

### Project Structure

```
frontend/
├── public/          # Static files
├── src/
│   ├── components/  # React components
│   ├── App.js       # Main app component
│   └── index.js     # Entry point
└── package.json     # Dependencies
```

### Building for Production

To create an optimized production build:

```bash
cd frontend
npm run build
```

The build output will be in `frontend/build/` directory.

## API Endpoints

The frontend communicates with these backend endpoints:

- `GET /api/profile` - User profile
- `GET /api/state` - Current state and stats
- `GET /api/matches` - All matches
- `POST /api/check-email` - Trigger email check
- `GET /api/calendar-events` - Calendar events
- `GET /api/health` - Health check

## Notes

- The frontend uses a proxy configuration to forward API requests to the backend during development
- CORS is enabled in the Flask backend to allow frontend requests
- The UI is responsive and works on both desktop and mobile devices

