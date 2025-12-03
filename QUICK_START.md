# Quick Start Guide - Shortlist Frontend

## Prerequisites

1. **Python 3.10+** installed
2. **Node.js 16+** installed (check with `node --version`)
3. **Google OAuth credentials** (`credentials.json` in project root)
4. **Python dependencies** installed

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
# From project root
pip install -r requirements.txt
```

### 2. Install Frontend Dependencies

```bash
# From project root
cd frontend
npm install
```

### 3. Run the Application

You need **TWO terminals** running simultaneously:

#### Terminal 1 - Backend API

```bash
# From project root
python -m app.api
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

#### Terminal 2 - Frontend

```bash
# From project root
cd frontend
npm start
```

You should see:
```
Compiled successfully!
webpack compiled successfully
```

The browser will automatically open to `http://localhost:3000`

## Windows PowerShell Commands

### Terminal 1 (Backend):
```powershell
python -m app.api
```

### Terminal 2 (Frontend):
```powershell
cd frontend
npm start
```

## What You'll See

1. **Backend API** running on `http://localhost:5000`
2. **Frontend** running on `http://localhost:3000`
3. Browser opens automatically to the frontend

## Troubleshooting

### Backend won't start
- Make sure `credentials.json` exists in project root
- Check Python dependencies: `pip install -r requirements.txt`
- Verify Python version: `python --version` (should be 3.10+)

### Frontend won't start
- Check Node.js version: `node --version` (should be 16+)
- Delete `node_modules` and reinstall:
  ```powershell
  cd frontend
  Remove-Item -Recurse -Force node_modules
  npm install
  ```

### Port already in use
- Backend (5000): Change port in `app/api.py` (last line)
- Frontend (3000): React will prompt to use a different port

### API connection errors
- Make sure backend is running on port 5000
- Check browser console for errors
- Verify `proxy` setting in `frontend/package.json`

## First Time Setup

If this is your first time running the app:

1. **OAuth Setup**: The backend will open a browser for Google OAuth authentication
2. **Profile Setup**: You'll be prompted to enter personal email and phone number
3. **Process Emails**: Run the runner once to process emails:
   ```bash
   python -m app.runner
   ```
   (Press Ctrl+C to stop after it processes some emails)

## Using the Frontend

Once both are running:

- **Dashboard**: Overview and quick actions
- **Profile**: View your profile information
- **Matches**: Browse detected email matches
- **Calendar**: View upcoming calendar events
- **Stats**: Detailed statistics

## Stopping the Application

- **Backend**: Press `Ctrl+C` in Terminal 1
- **Frontend**: Press `Ctrl+C` in Terminal 2

