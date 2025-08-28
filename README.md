# Shortlist

Shortlist watches your Gmail inbox for campus placement shortlisting/assessment emails and automatically:

- Detects confirmed shortlisting from message content and attachments
- Logs matches to `data/` and keeps a running `state.json`
- Creates Google Calendar events with a clean title (e.g., `Okta - Online Test`)
- Extracts date/time primarily from the subject (with robust parsing) and duration from the body
- Optionally uses a small GPT model to infer missing details (link/location/time) when the email is vague

Time zone defaults to `Asia/Kolkata`.


## Quick Start

1) Requirements

- Python 3.10+
- A Google Cloud project with:
  - Gmail API enabled
  - Google Calendar API enabled
  - OAuth 2.0 Client ID (Desktop)

2) Clone and install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3) Configure OAuth client

Place your OAuth client JSON as `credentials.json` at the repo root. For a Desktop client it typically looks like:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": [
      "http://localhost"
    ]
  }
}
```

4) Optional: GPT key (.env)

Create a `.env` (or export an env var) with your OpenAI API key to let the app infer missing event details:

```ini
# .env
OPENAIKEY=sk-your-openai-key
```

5) First sign-in (unified token)

On first run, the app opens a browser to authorize a single token (`token.json`) that covers both Gmail read and Calendar events. Subsequent runs reuse the same token without re-prompting.

```bash
python -m app.runner
```


## What it does

- Reads your Gmail inbox using the Gmail API and extracts message text/headers
- Scores content and attachments to determine a match tier (Confirmed/Possibility/Partial)
- For Confirmed matches, creates a Calendar event:
  - Title: `Company - Kind` (e.g., `Okta - Online Test`)
  - Time: parsed primarily from the subject line; supports formats like `7th July 2025 by 9.00 am`
  - Duration: detects phrases like `Test duration: 2 hours` or `120 minutes` (default 1 hour)
  - Location: hall/block codes (when present) or the first URL as a join link
  - Description: includes the Gmail permalink, join link, location, and original subject


## Repository overview

- `app/login.py` — Unified OAuth login (Gmail + Calendar scopes) and profile enrichment
- `app/runner.py` — Main loop that watches the inbox, classifies matches, and triggers events
- `app/calendar_service.py` — Event extraction and Calendar API integration
- `app/parsers/` — Attachment parsers used for extra match signals
- `requirements.txt` — Python dependencies
- `data/` — Match logs (`match_*.json`) and artifacts


## Scopes and tokens

- The app requests these scopes once and stores credentials in `token.json`:
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/calendar.events`
- Legacy `calendar_token.json` (calendar-only) is still read for compatibility but no longer written.
- Files with secrets are already ignored by `.gitignore` (`credentials.json`, `.env`, `token.json`, `calendar_token.json`, etc.).


## Troubleshooting

- Consent screen keeps appearing
  - Ensure both Gmail and Calendar APIs are enabled in the same Google Cloud project as your `credentials.json`.
  - If you previously created `token.json` without Calendar scope, the app upgrades it on the next run. If it fails, delete `token.json` and re-run.

- No event created
  - Only Confirmed matches create events. Check the console for `📅 Creating calendar event...` and a success/error line.
  - If time wasn’t detected, ensure the subject contains a clear date and time (e.g., `7th July 2025 by 9.00 am`). The app prefers subject time to avoid footer/header noise.
  - Provide `OPENAIKEY` if you want GPT-based inference when details are missing.

- Wrong time zone
  - The app uses `Asia/Kolkata`. If you need something else, adjust the hardcoded time zone in `app/calendar_service.py`.

- Duplicates
  - If the same email is processed multiple times, you might get duplicate events. A de-dup mechanism can be added by checking for an existing event with the same date+title.


## Development tips

- Dry-run sign-in only:

```bash
python -m app.login
```

- Verbose logging during event creation prints the parsed datetime, location, and link to help verify the extraction.


## Security

Never commit `credentials.json`, `token.json`, or `.env`. They are in `.gitignore` by default. Treat all tokens as secrets.

