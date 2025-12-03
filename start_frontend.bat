@echo off
REM Startup script for Shortlist Frontend (Windows)

echo Starting Shortlist Frontend...
echo.

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Node.js is not installed. Please install Node.js 16+ from https://nodejs.org/
    exit /b 1
)

REM Check if npm is installed
where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo npm is not installed. Please install npm.
    exit /b 1
)

REM Check if frontend directory exists
if not exist "frontend" (
    echo Frontend directory not found. Please run this from the project root.
    exit /b 1
)

REM Navigate to frontend directory
cd frontend

REM Check if node_modules exists
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
)

echo Starting frontend development server...
echo Frontend will be available at http://localhost:3000
echo Make sure the Flask API is running on http://localhost:5000
echo.

call npm start

