# Shortlist Frontend

Modern React frontend application for the Shortlist campus placement email monitoring system.

## Features

- 📊 **Dashboard**: Overview with quick actions and statistics
- 👤 **Profile**: View and manage your profile information
- 🎯 **Matches**: Browse all detected email matches (Confirmed, Possibilities, Partial)
- 📅 **Calendar**: View upcoming calendar events created from confirmed matches
- 📈 **Stats**: Detailed statistics and match distribution

## Setup

### Prerequisites

- Node.js 16+ and npm
- Python backend running on port 5000

### Installation

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The frontend will be available at `http://localhost:3000`

## Development

The frontend uses:
- **React 18** for UI components
- **Axios** for API calls
- **date-fns** for date formatting
- **CSS3** for styling with modern gradients and animations

### Project Structure

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── components/
│   │   ├── Dashboard.js
│   │   ├── Profile.js
│   │   ├── Matches.js
│   │   ├── CalendarEvents.js
│   │   └── Stats.js
│   ├── App.js
│   ├── App.css
│   ├── index.js
│   └── index.css
└── package.json
```

## API Integration

The frontend communicates with the Flask backend API at `http://localhost:5000`. The proxy is configured in `package.json` to forward requests during development.

### API Endpoints Used

- `GET /api/profile` - Get user profile
- `GET /api/state` - Get current state and statistics
- `GET /api/matches` - Get all matches
- `POST /api/check-email` - Manually trigger email check
- `GET /api/calendar-events` - Get upcoming calendar events

## Building for Production

To create a production build:

```bash
npm run build
```

This creates an optimized build in the `build/` directory.

## Notes

- The frontend expects the backend to be running on port 5000
- CORS is enabled in the Flask backend to allow frontend requests
- The app uses a modern, responsive design that works on desktop and mobile devices

