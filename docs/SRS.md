# Shortlist — Agile Software Requirements Specification (SRS)

- Version: 0.1 (Draft)
- Date: 2025-09-08
- Repository: Shortlist (local)
- Quick Start: `README.md:1`

## Overview

Shortlist watches your Gmail inbox for campus placement shortlisting/assessment emails and automatically creates clean, well‑timed Google Calendar events when it finds a confirmed match. It consolidates signals from the email subject/body and from attachments (CSV/XLS/XLSX/PDF), and logs decisions for transparency.

- Time zone: `Asia/Kolkata`
- Run: `python -m app.runner`

## Goals

- Detect placement‑related emails reliably (subject/body + attachments).
- Match emails to the student via name and registration number.
- Create accurate calendar events with concise titles and durations.
- Keep a transparent audit trail (`data/match_*.json`).

## Non‑Goals

- Multi‑user or server deployment.
- Historical backfilling of entire inbox.
- Event de‑duplication beyond current heuristics.

## Stakeholders & Personas

- Student (primary user): wants automatic event creation for tests/interviews.
- University CDC (sender): no system access; mails originate here.
- Maintainer (developer/user): configures credentials and updates packages.

## Scope

- In: Gmail read, placement classification, attachment parsing, event creation for confirmed matches, state/logging, optional GPT inference.
- Out: Multi‑account switching, web UI, organization‑wide deployment.

## System Context

- Inputs: Gmail messages and attachments (CSV/XLS/XLSX/PDF).
- Processing: Classification → Matching → Extraction → Decision → Logging.
- Outputs: Google Calendar events; `data/match_*.json`; `state.json` counters.
- External: Google APIs (Gmail/Calendar), OpenAI API (optional).
- Execution: Local CLI; Python 3.10+.

## Assumptions & Constraints

- Single user, primary calendar only.
- OAuth 2.0 (Desktop) flow; token stored as `token.json`.
- Calendar events only for `CONFIRMED_MATCH`.
- GPT usage is optional; falls back to heuristics for placement detection.
- Time zone fixed to `Asia/Kolkata` (can be made configurable in future).

## Definitions

- Match Types: `CONFIRMED_MATCH`, `POSSIBILITY`, `PARTIAL_MATCH`, `NO_MATCH`.
- Placement Email: Communication about shortlisting/assessments/interviews/drives.

---

## Functional Requirements

### Authentication & Profile

- Unified OAuth
  - Obtain and persist `token.json` with Gmail read + Calendar events scopes.
  - Implementation: `app/login.py:1`
- Profile enrichment
  - Derive `name` and `registration_number` from Gmail account display name when possible.
  - Prompt once for personal email and phone; save to `profile.json`.
- Acceptance
  - On first run, browser sign‑in completes and writes `token.json`.
  - `profile.json` persists derived and user‑entered fields; later runs reuse it.

### Inbox Monitoring

- Poll newest inbox message about every 30 seconds; fetch full payload.
  - Implementation: `app/runner.py:35`
- Maintain `state.json.last_message_id` to avoid reprocessing.
  - Implementation: `app/state_utils.py:1`
- Acceptance
  - New messages are processed once and the pointer advances.

### Placement Classification

- Whitelist: Always accept senders in `CDC_SENDER_WHITELIST`.
  - Implementation: `app/placement_classifier.py:1`
- GPT path (optional): If `OPENAIKEY` present, classify via `gpt-4o-mini` (YES/NO).
  - Fallback: keyword + company‑like token heuristic.
- Acceptance
- Whitelisted sender → placement, regardless of content.
  - Without GPT, placement keywords + company pattern → accepted; otherwise rejected.

### Content‑Based Matching (Subject/Body)

- Name match: order‑preserving loose match of profile name in text.
- Registration match: exact presence of profile reg number.
- Email equality is intentionally ignored as a positive signal.
  - Implementation: `app/match_logic.py:1`
- Decision
  - Name+Reg → `CONFIRMED_MATCH`
  - Name only → `POSSIBILITY`
  - Reg only → `PARTIAL_MATCH`

### Attachment Parsing

- Document files (CSV/XLS/XLSX): scan all cells/sheets for names, reg numbers, emails.
  - Implementation: `app/parsers/doc_parser.py:1`
- PDFs: extract text and evaluate for names/reg/emails.
  - Implementation: `app/parsers/pdf_parser.py:1`
- Aggregation per email: Combine per‑attachment results into an “overall attachment match”.
  - Implementation: `app/parsers/__init__.py:1`
- Acceptance
  - If a sheet row contains both the student’s name and reg, the attachment yields `CONFIRMED_MATCH`.
  - Unsupported files are reported without crashing processing.

### Overall Match Decision

- Overall match = best among content match and attachments overall match.
  - Implementation: `app/runner.py:95`, `app/match_utils.py:1`
- Acceptance
  - Attachments can upgrade a weaker content match to `CONFIRMED_MATCH`.

### Logging & State

- Persist per‑match JSON log files in `data/` with profile/email snapshots.
  - Implementation: `app/state_utils.py:1`
- Maintain in‑memory counters (confirmed/possible/partial) and cap last 100 entries.
- Acceptance
  - After processing, a `match_*.json` log exists with match type and snapshots.

### Calendar Event Creation

- Trigger: Only for `CONFIRMED_MATCH` and when date/time is extracted.
  - Implementation: `app/calendar_service.py:1`
- Extraction
  - GPT‑only extraction of date/time/location/link from both Subject and Body (if GPT available); no heuristic fallback currently.
- Event Details
  - Summary: “Company - Kind” derived from subject (e.g., “Okta - Online Test”).
  - Duration: default 1h; detect “duration: 2 hours”/“120 minutes”; round to 15 min; cap 4h.
  - Description: Gmail permalink, join link, venue/location, full subject, duration if !=1h.
  - Time zone: `Asia/Kolkata`.
- Acceptance
  - When GPT yields a valid date/time, an event is inserted into the primary calendar with clean summary and description.

### Console UX

- Icons and concise prints for matches and attachment analysis.
  - Implementation: `app/runner.py:28`
- Acceptance
  - After processing a message, totals and attachment breakdown are printed.

---

## User Stories (with Acceptance Criteria)

- As a student, I can authorize Gmail + Calendar once so subsequent runs work without re‑auth.
  - AC: First run writes `token.json`; later runs reuse it.
- As a student, I want my name/reg auto‑derived from my Gmail identity to reduce manual setup.
  - AC: `profile.json` includes `name` and `registration_number` when they appear in display name.
- As a student, I want placement emails detected even when wording varies.
  - AC: Whitelisted CDC emails or GPT returns YES → accepted as placement.
- As a student, I want the system to recognize when an attached shortlist includes me.
  - AC: Detect my reg and name signals in CSV/XLSX/PDF and set match accordingly.
- As a student, I want calendar events only when details are sufficient.
  - AC: Event only for `CONFIRMED_MATCH` and when date/time was extracted; else print a clear skip reason.
- As a student, I want an audit trail of decisions.
  - AC: A `data/match_*.json` record is written per processed match.

---

## Data & Persistence

- Files
  - `token.json`: unified OAuth token (Gmail+Calendar).
  - `profile.json`: user profile (name, reg, Gmail, personal email, phone).
  - `state.json`: last processed message id; counters per match type.
  - `data/match_*.json`: per‑match logs (profile/email snapshot, match type, attachments summary).
- Retention
  - State counters keep only last 100 entries per category; logs in `data/` are append‑only.
- Secrets
  - `credentials.json`, `.env.local`/`.env` for `OPENAIKEY`; all ignored by Git.

## External Interfaces

- Gmail API
  - Scope: `https://www.googleapis.com/auth/gmail.readonly`
  - Ops: list newest message; get full message; fetch attachments.
- Google Calendar API
  - Scope: `https://www.googleapis.com/auth/calendar.events`
  - Ops: insert event into `primary` calendar.
- OpenAI API (optional)
  - Model: `gpt-4o-mini` for classification and date/time extraction.
  - Env: `OPENAIKEY` (loaded from `.env.local`/`.env` if present).
- CLI
  - Command: `python -m app.runner`
  - Python: 3.10+

## Security & Privacy

- Data minimization: Process locally; no server component.
- Tokens: Persisted to repo root, excluded from Git by `.gitignore`.
- Secrets: `.env(.local)` ignored by Git; do not commit keys.
- Logs: Contain limited body preview; stored locally under `data/`.

## Performance & Reliability

- Poll interval: ~30 seconds (configurable in code).
- Robustness: Graceful degradation if GPT or PyPDF2 is missing (reduced functionality, no crash for unsupported attachments).
- Parsing: Subject preferred for “kind/company” titling; GPT extracts date/time.

## Quality Attributes

- Maintainability: Modular layout with focused modules and utilities.
- Extensibility: New parsers can implement `parse_attachment(...)` and be added in `app/parsers/__init__.py:1`.
- Observability: Console logs with icons; JSON logs in `data/`.

## Risks & Mitigations

- GPT dependency: Without GPT, event creation is skipped (no fallback parsing).
  - Mitigation (future): Add regex/heuristic time parsing fallback.
- Duplicate events: Reprocessing may create duplicates.
  - Mitigation (future): De‑dup by title+date or Gmail message hash.
- Fixed time zone: `Asia/Kolkata` only.
  - Mitigation (future): Configurable TZ via profile/config file.
- Whitelist spoofing: Sender spoof could bypass classifier.
  - Mitigation (future): Domain/DKIM checks.

## Release Plan

- MVP (current)
  - Unified OAuth, profile enrichment, polling and classification, attachment parsing, logging, event creation for confirmed matches with GPT extraction.
- Next (proposed)
  - Event de‑duplication; non‑GPT time parsing fallback; configurable poll interval and TZ; richer reports; tests for parsers; ICS export; Docker packaging.

## Backlog (Epics)

- Calendar de‑dup + update flow
- Heuristic time extraction fallback (non‑GPT)
- Additional parsers (DOCX/HTML)
- Config file (`shortlist.toml`) for TZ, poll interval, CDC list
- Observability: CSV/HTML summary report
- Safety: Sender domain verification/DKIM checks

## Acceptance Test Scenarios (Samples)

- Whitelist Shortcut
  - Given sender is in `CDC_SENDER_WHITELIST`, when message arrives, then classification = placement regardless of content.
- Attachment Confirmed Match
  - Given an XLSX with a row containing my reg and matching name, then attachments overall = `CONFIRMED_MATCH`.
- Event Creation Success
  - Given a confirmed match with subject containing “7th July 2025 by 9.00 am”, then an event is created titled “Company - Online Test”, start at the parsed time in `Asia/Kolkata`.
- GPT Missing
  - Given `OPENAIKEY` is unset, when a confirmed match arrives, then the system prints a GPT‑disabled notice and skips event creation.

## Codebase References

- `README.md:1` — project overview and setup
- `app/runner.py:1` — main loop, orchestration, and logging
- `app/login.py:1` — OAuth + profile enrichment
- `app/calendar_service.py:1` — event extraction and Calendar API integration
- `app/placement_classifier.py:1` — placement classifier (GPT + heuristic)
- `app/match_logic.py:1` — content matching logic
- `app/state_utils.py:1` — state and log persistence helpers
- `app/parsers/__init__.py:1` — attachment extraction and dispatch
- `app/parsers/doc_parser.py:1` — CSV/XLS/XLSX scanning logic
- `app/parsers/pdf_parser.py:1` — PDF text extraction and matching

---

## References

- Google APIs
  - Gmail API: https://developers.google.com/gmail/api
  - Google Calendar API: https://developers.google.com/calendar/api
  - Google API Python Client: https://github.com/googleapis/google-api-python-client
  - google‑auth‑oauthlib: https://github.com/googleapis/google-auth-library-python-oauthlib
- OpenAI
  - OpenAI API Docs: https://platform.openai.com/docs
  - openai Python SDK: https://github.com/openai/openai-python
- Python Packages
  - pandas: https://pandas.pydata.org/
  - openpyxl: https://openpyxl.readthedocs.io/en/stable/
  - PyPDF2: https://pypdf2.readthedocs.io/
  - python‑dateutil: https://dateutil.readthedocs.io/
- OAuth 2.0
  - OAuth 2.0 for Installed Apps: https://developers.google.com/identity/protocols/oauth2
- Misc
  - RFC 2822 Email format (context): https://www.rfc-editor.org/rfc/rfc2822

