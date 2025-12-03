"""Flask API backend for Shortlist frontend."""

from flask import Flask, jsonify, request
from flask_cors import CORS
from pathlib import Path
import json
import os
from typing import Dict, Any

from app.login import get_gmail_client_and_profile
from app.state_utils import load_state, save_state
from app.runner import newest_message_id, fetch_full
from app.email_utils import header, parse_from_header, split_name_and_reg, extract_text
from app.match_logic import evaluate_match, evaluate_content_match
from app.match_utils import best
from app.parsers import parse_email_attachments
from app.calendar_service import create_calendar_event, should_create_calendar_event, get_calendar_service
from app.state_utils import log_match_to_data, update_state_with_match
from app.log_stream import get_recent, log
from threading import Thread, Event

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
PROFILE_FILE = ROOT / "profile.json"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Background runner management
_runner_thread: Thread | None = None
_runner_stop = Event()


def _run_runner_loop():
    """Run the email watcher loop until stop is set."""
    from app.runner import run
    try:
        # The runner has its own infinite loop; stop flag can be integrated later if needed
        run()
    except Exception as e:
        log(f"Runner crashed: {e}")


def _load_json(path: Path, default: dict) -> dict:
    """Load JSON file with safe fallback."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get user profile information."""
    profile = _load_json(PROFILE_FILE, {})
    return jsonify(profile)


@app.route('/api/profile', methods=['POST'])
def update_profile():
    """Update basic profile fields."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        profile = _load_json(PROFILE_FILE, {})
        for key in ["name", "registration_number", "gmail_display_name", "personal_email", "phone_number"]:
            if key in body and isinstance(body[key], str):
                val = body[key].strip()
                profile[key] = val
        PROFILE_FILE.write_text(json.dumps(profile, indent=2))
        return jsonify({"success": True, "message": "Profile updated", "profile": profile})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/state', methods=['GET'])
def get_state():
    """Get current state including match statistics."""
    state = load_state(STATE_FILE)
    stats = {
        "confirmed_count": len(state.get("confirmed_matches", [])),
        "possibilities_count": len(state.get("possibilities", [])),
        "partial_count": len(state.get("partial_matches", [])),
        "last_message_id": state.get("last_message_id"),
    }
    return jsonify({
        "state": state,
        "stats": stats
    })


@app.route('/api/matches', methods=['GET'])
def get_matches():
    """Get all matches grouped by type."""
    state = load_state(STATE_FILE)
    return jsonify({
        "confirmed": state.get("confirmed_matches", []),
        "possibilities": state.get("possibilities", []),
        "partial": state.get("partial_matches", [])
    })


@app.route('/api/check-email', methods=['POST'])
def check_email():
    """Manually trigger email check for the newest email."""
    try:
        service, profile = get_gmail_client_and_profile()
        state = load_state(STATE_FILE)
        
        mid = newest_message_id(service)
        if not mid:
            return jsonify({"success": False, "message": "No new emails found"}), 404
        
        if mid == state.get("last_message_id"):
            return jsonify({"success": False, "message": "Email already processed"}), 200
        
        msg = fetch_full(service, mid)
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        
        from_raw = header(headers, "From")
        subject = header(headers, "Subject")
        display_name, addr = parse_from_header(from_raw)
        parsed_name, reg = split_name_and_reg(display_name)
        
        match_type_header = evaluate_match(profile, parsed_name, reg, addr)
        body = extract_text(payload)
        match_type_content = evaluate_content_match(profile, subject or "", body or "")
        match_type = best(match_type_header, match_type_content)
        
        attachment_results = parse_email_attachments(service, mid, profile)
        
        overall_match_type = match_type
        att_overall = attachment_results.get('overall_match_type', 'NO_MATCH')
        if att_overall != 'NO_MATCH':
            prev = overall_match_type
            upgraded = best(prev, att_overall)
            if upgraded != prev:
                overall_match_type = upgraded
        
        email_data = {
            "message_id": mid,
            "from_display_name": display_name,
            "from_email": addr,
            "parsed_name": parsed_name,
            "parsed_reg": reg,
            "subject": subject,
            "body_preview": body[:400] if body else "",
            "body_full": body or "",
            "match_type": overall_match_type,
            "attachments": attachment_results
        }
        
        if overall_match_type != "NO_MATCH":
            log_match_to_data(profile, email_data, DATA_DIR)
            update_state_with_match(state, email_data, overall_match_type)
            
            if should_create_calendar_event(email_data):
                event_created = create_calendar_event(subject, body, mid)
                email_data["calendar_event_created"] = event_created
            else:
                email_data["calendar_event_created"] = False
        
        state["last_message_id"] = mid
        save_state(state, STATE_FILE)
        
        return jsonify({
            "success": True,
            "email": email_data,
            "message": f"Processed email: {subject}"
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/calendar-events', methods=['GET'])
def get_calendar_events():
    """Get upcoming calendar events from Google Calendar."""
    try:
        service = get_calendar_service()
        from datetime import datetime, timedelta
        
        now = datetime.utcnow().isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted_events.append({
                "id": event.get('id'),
                "summary": event.get('summary', 'No Title'),
                "start": start,
                "location": event.get('location', ''),
                "description": event.get('description', ''),
                "htmlLink": event.get('htmlLink', '')
            })
        
        return jsonify({"events": formatted_events})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "events": []}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route('/api/runner/start', methods=['POST'])
def start_runner():
    """Start the background runner if not already running."""
    global _runner_thread
    if _runner_thread and _runner_thread.is_alive():
        return jsonify({"success": True, "message": "Runner already running"})
    _runner_thread = Thread(target=_run_runner_loop, daemon=True)
    _runner_thread.start()
    log("Runner thread started via API")
    return jsonify({"success": True, "message": "Runner started"})


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Return recent runner logs for display in a UI."""
    try:
        limit = int(request.args.get("limit", "200"))
        since_id_raw = request.args.get("since_id")
        since_id = int(since_id_raw) if since_id_raw is not None else None
        items = get_recent(limit=limit, since_id=since_id)
        return jsonify({
            "success": True,
            "items": [{"id": i, "line": line} for i, line in items],
            "count": len(items)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "items": [], "count": 0}), 500


@app.route('/api/runner/status', methods=['GET'])
def runner_status():
    """Return whether the runner thread is currently running."""
    running = bool(_runner_thread and _runner_thread.is_alive())
    return jsonify({"running": running})


@app.route('/api/backfill', methods=['POST'])
def backfill():
    """Trigger a backfill of latest N emails in a background thread."""
    try:
        body = request.get_json(silent=True) or {}
        count = int(body.get("count", 50))
        count = max(1, min(500, count))

        def _task():
            try:
                from app.runner import backfill_latest
                res = backfill_latest(count)
                log(f"Backfill summary: {res}")
            except Exception as e:
                log(f"Backfill crashed: {e}")

        Thread(target=_task, daemon=True).start()
        return jsonify({"success": True, "message": f"Backfill started for latest {count} emails"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/logs', methods=['GET'])
def logs_page():
    """Minimal UI to view logs in the browser."""
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Shortlist • Logs</title>
    <style>
      :root { color-scheme: light dark; }
      :root.light {
        --bg: #f7fafc; --panel:#ffffff; --border:#e5e7eb; --text:#0f172a; --muted:#475569; --accent:#2563eb;
      }
      :root.dark {
        --bg: #0b0f17; --panel:#121826; --border:#1f2937; --text:#e2e8f0; --muted:#94a3b8; --accent:#3b82f6;
      }
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; margin: 0; background: var(--bg); color: var(--text); }
      header { position: sticky; top: 0; z-index: 10; background: color-mix(in oklab, var(--bg) 90%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
      .wrap { max-width: 1100px; margin: 0 auto; padding: 12px; }
      .nav { display:flex; gap:10px; align-items:center; }
      .nav a { text-decoration:none; color: var(--text); opacity:.85; padding:8px 12px; border-radius:10px; border:1px solid var(--border); background: var(--panel); }
      .nav a.active { outline: 2px solid var(--accent); }
      .spacer { margin-left:auto; }
      #bar { display:flex; gap:8px; padding: 8px 0; align-items:center; }
      #status { margin-left: auto; opacity: .8; }
      #log { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; white-space: pre-wrap; padding: 12px; line-height: 1.35; }
      button { background: var(--accent); color: #fff; border: 0; padding: 8px 12px; border-radius: 8px; cursor: pointer; }
      button:disabled { opacity:.6; cursor: not-allowed; }
      input { width: 70px; background: var(--panel); color: var(--text); border:1px solid var(--border); border-radius:8px; padding:4px 6px; }
    </style>
  </head>
  <body>
    <header>
      <div class="wrap nav">
        <a href="/" >Home</a>
        <a href="/matches">Matches</a>
        <a href="/calendar">Calendar</a>
        <a href="/profile">Profile</a>
        <a href="/logs" class="active">Logs</a>
        <span class="spacer"></span>
        <button id="theme">Toggle theme</button>
      </div>
    </header>

    <div class="wrap" id="bar">
      <button id="startBtn">Start runner</button>
      <label class="muted">Limit <input id="limit" type="number" value="200" min="50" max="2000"/></label>
      <div id="status">idle</div>
    </div>
    <div class="wrap"><div id="log" class="card"></div></div>
    <script>
      const logEl = document.getElementById('log');
      const statusEl = document.getElementById('status');
      const limitEl = document.getElementById('limit');
      const startBtn = document.getElementById('startBtn');
      const themeBtn = document.getElementById('theme');
      let sinceId = null;

      // Theme toggle
      function applyTheme() {
        const t = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.classList.remove('light','dark');
        document.documentElement.classList.add(t);
      }
      themeBtn.addEventListener('click', () => {
        const now = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
        localStorage.setItem('theme', now);
        applyTheme();
      });
      applyTheme();

      async function startRunner() {
        try {
          startBtn.disabled = true;
          const r = await fetch('/api/runner/start', { method: 'POST' });
          const j = await r.json();
          statusEl.textContent = j.message || 'runner started';
        } catch (e) {
          statusEl.textContent = 'failed: ' + e;
        } finally {
          setTimeout(() => startBtn.disabled = false, 2000);
        }
      }

      async function poll() {
        try {
          const u = new URL(location.origin + '/api/logs');
          u.searchParams.set('limit', limitEl.value || '200');
          if (sinceId !== null) u.searchParams.set('since_id', String(sinceId));
          const r = await fetch(u);
          const j = await r.json();
          if (j.success) {
            if (j.items.length > 0) {
              const frag = document.createDocumentFragment();
              for (const it of j.items) {
                const div = document.createElement('div');
                div.textContent = it.line;
                frag.appendChild(div);
                sinceId = it.id;
              }
              logEl.appendChild(frag);
              window.scrollTo(0, document.body.scrollHeight);
            }
            statusEl.textContent = 'ok (' + j.count + ' new)';
          } else {
            statusEl.textContent = 'error: ' + j.message;
          }
        } catch (e) {
          statusEl.textContent = 'error: ' + e;
        } finally {
          setTimeout(poll, 1500);
        }
      }

      startBtn.addEventListener('click', startRunner);
      poll();
    </script>
  </body>
</html>
"""
    return html


@app.route('/', methods=['GET'])
def home_page():
    """Rich UI homepage to monitor processing and view output."""
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Shortlist Monitor</title>
    <style>
      :root { color-scheme: light dark; }
      :root.light { --bg:#f7fafc; --panel:#ffffff; --border:#e5e7eb; --muted:#475569; --text:#0f172a; --accent:#2563eb; --accent2:#16a34a; --warn:#ca8a04; }
      :root.dark { --bg:#0b0f17; --panel:#121826; --border:#1f2937; --muted:#94a3b8; --text:#e2e8f0; --accent:#3b82f6; --accent2:#22c55e; --warn:#eab308; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; background: var(--bg); color: var(--text); }
      header { position: sticky; top: 0; z-index: 10; background: color-mix(in oklab, var(--bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
      .wrap { max-width: 1100px; margin: 0 auto; padding: 16px; }
      h1 { font-size: 20px; margin: 0; }
      .controls { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; align-items: center; justify-content: space-between; }
      .btn { background: var(--accent); color: white; border: 0; padding: 10px 14px; border-radius: 10px; cursor: pointer; font-weight: 600; }
      .btn.secondary { background: color-mix(in oklab, var(--panel) 85%, var(--text)); color: var(--text); border: 1px solid var(--border); }
      .btn.good { background: var(--accent2); }
      .btn:disabled { opacity: .6; cursor: not-allowed; }
      .tabs { display:flex; gap:10px; align-items:center; flex-wrap: wrap; }
      .tab { text-decoration:none; color: var(--text); opacity:.9; padding:8px 12px; border-radius:10px; border:1px solid var(--border); background: var(--panel); }
      .tab.active { outline:2px solid var(--accent); }
      .grid { display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; padding: 16px; position: relative; }
      .bg-blob { position:absolute; inset:-10% -10% auto auto; width: 360px; height: 360px; border-radius: 50%; filter: blur(60px); opacity:.25; background: radial-gradient(closest-side, var(--accent), transparent); pointer-events:none; }
      .bg-blob.b2 { left:-10%; top:30%; right:auto; background: radial-gradient(closest-side, var(--accent2), transparent); }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px color-mix(in oklab, var(--bg) 75%, #000); transition: transform .2s ease, box-shadow .2s ease; }
      .card:hover { transform: translateY(-2px); box-shadow: 0 16px 40px color-mix(in oklab, var(--bg) 70%, #000); }
      .card h2 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 16px; background: color-mix(in oklab, var(--panel) 85%, var(--bg)); }
      .section { padding: 12px 14px; }
      .muted { color: var(--muted); }
      .stats { display: flex; gap: 16px; flex-wrap: wrap; }
      .stat { background: color-mix(in oklab, var(--panel) 85%, var(--bg)); border: 1px solid var(--border); padding: 12px 14px; border-radius: 12px; min-width: 140px; display:flex; gap:10px; align-items:center; }
      .stat .ico { font-size: 20px; }
      .k { font-size: 12px; color: var(--muted); }
      #logs { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; line-height: 1.35; max-height: 55vh; overflow: auto; padding: 12px 14px; }
      .flex { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
      ul { padding-left: 18px; margin: 8px 0; }
      li { margin: 4px 0; }
      .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid #1f2937; }
      .pill.ok { background: rgba(34,197,94,.12); border-color: rgba(34,197,94,.3); color: #86efac; }
      .pill.warn { background: rgba(234,179,8,.12); border-color: rgba(234,179,8,.3); color: #fde68a; }
      .pill.info { background: rgba(59,130,246,.12); border-color: rgba(59,130,246,.3); color: #93c5fd; }
      footer { text-align: center; color: var(--muted); padding: 16px; }
      @media (max-width: 900px) {
        .grid { grid-template-columns: 1fr; }
        #logs { max-height: 40vh; }
      }
    </style>
  </head>
  <body>
    <header>
      <div class="wrap">
        <div style="display:flex; align-items:center; gap:12px; justify-content: space-between;">
          <h1>Shortlist Monitor</h1>
          <div>
            <button id="theme" class="btn secondary">Toggle theme</button>
          </div>
        </div>
        <div class="tabs" style="margin-top:10px;">
          <a href="/" class="tab active">Home</a>
          <a href="/matches" class="tab">Matches</a>
          <a href="/calendar" class="tab">Calendar</a>
          <a href="/profile" class="tab">Profile</a>
          <a href="/logs" class="tab">Logs</a>
        </div>
        <div class="controls">
          <div class="flex">
            <button id="start" class="btn">Start Runner</button>
            <button id="check" class="btn secondary">Check Latest Email Once</button>
            <span id="runnerStatus" class="pill info">checking…</span>
          </div>
          <span class="muted" id="status"></span>
        </div>
      </div>
    </header>

    <div class="wrap grid">
      <div class="bg-blob"></div>
      <div class="bg-blob b2"></div>
      <div class="card">
        <h2>Activity Log</h2>
        <div class="section flex">
          <label class="muted">Limit
            <input id="limit" type="number" min="100" max="2000" value="400" style="width:80px;background:#0b1020;border:1px solid #1f2937;color:#e2e8f0;border-radius:8px;padding:6px 8px;margin-left:8px;">
          </label>
          <button id="clear" class="btn secondary">Clear</button>
          <span class="muted">Auto-scroll</span>
          <input type="checkbox" id="autoscroll" checked>
        </div>
        <div id="logs"></div>
      </div>

      <div class="card">
        <h2>Overview</h2>
        <div class="section">
          <div class="stats">
            <div class="stat"><div class="ico">🎯</div><div><div class="k">Confirmed</div><div id="statConfirmed" style="font-size:22px;font-weight:700;">0</div></div></div>
            <div class="stat"><div class="ico">🤔</div><div><div class="k">Possibilities</div><div id="statPoss" style="font-size:22px;font-weight:700;">0</div></div></div>
            <div class="stat"><div class="ico">📧</div><div><div class="k">Partial</div><div id="statPartial" style="font-size:22px;font-weight:700;">0</div></div></div>
          </div>
          <div style="margin-top:12px;" class="muted">Last Message ID: <span id="lastMid">—</span></div>

          <div style="margin-top:16px;">
            <div class="k">Recent Matches</div>
            <ul id="matches"></ul>
          </div>

          <div style="margin-top:16px;">
            <div class="k">Profile</div>
            <div id="profileBox" class="muted">—</div>
          </div>

          <div style="margin-top:16px;">
            <div class="k">Backfill previous emails</div>
            <div class="flex">
              <label>Count
                <select id="backfillCount" style="width:100px;background:#0b1020;border:1px solid #1f2937;color:#e2e8f0;border-radius:8px;padding:6px 8px;margin-left:8px;">
                  <option value="25">25</option>
                  <option value="50" selected>50</option>
                  <option value="100">100</option>
                  <option value="200">200</option>
                  <option value="500">500</option>
                </select>
              </label>
              <button id="backfillBtn" class="btn good">Run Backfill</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <footer>Shortlist ©</footer>
    <script>
      // Theme toggle
      (function(){
        function applyTheme() {
          const t = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
          document.documentElement.classList.remove('light','dark');
          document.documentElement.classList.add(t);
        }
        applyTheme();
        const themeBtn = document.getElementById('theme');
        themeBtn.addEventListener('click', () => {
          const now = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
          localStorage.setItem('theme', now);
          applyTheme();
        });
      })();

      const els = {
        start: document.getElementById('start'),
        check: document.getElementById('check'),
        runnerStatus: document.getElementById('runnerStatus'),
        status: document.getElementById('status'),
        limit: document.getElementById('limit'),
        logs: document.getElementById('logs'),
        clear: document.getElementById('clear'),
        autoscroll: document.getElementById('autoscroll'),
        statConfirmed: document.getElementById('statConfirmed'),
        statPoss: document.getElementById('statPoss'),
        statPartial: document.getElementById('statPartial'),
        lastMid: document.getElementById('lastMid'),
        matches: document.getElementById('matches'),
        profileBox: document.getElementById('profileBox'),
        backfillBtn: document.getElementById('backfillBtn'),
        backfillCount: document.getElementById('backfillCount'),
      };

      let sinceId = null;
      let polling = false;

      function setRunnerPill(running) {
        els.runnerStatus.textContent = running ? 'running' : 'stopped';
        els.runnerStatus.className = 'pill ' + (running ? 'ok' : 'warn');
      }

      async function refreshStatus() {
        try {
          const r = await fetch('/api/runner/status');
          const j = await r.json();
          setRunnerPill(!!j.running);
        } catch (e) {
          els.runnerStatus.textContent = 'error';
          els.runnerStatus.className = 'pill warn';
        }
      }

      async function startRunner() {
        els.start.disabled = true;
        try {
          const r = await fetch('/api/runner/start', { method: 'POST' });
          const j = await r.json();
          els.status.textContent = j.message || 'runner started';
          setRunnerPill(true);
        } catch (e) {
          els.status.textContent = 'failed to start runner: ' + e;
        } finally {
          setTimeout(() => els.start.disabled = false, 1500);
        }
      }

      async function checkEmail() {
        els.check.disabled = true;
        try {
          const r = await fetch('/api/check-email', { method: 'POST' });
          const j = await r.json();
          els.status.textContent = j.message || (j.success ? 'checked' : 'not processed');
        } catch (e) {
          els.status.textContent = 'check failed: ' + e;
        } finally {
          setTimeout(() => els.check.disabled = false, 1200);
        }
      }

      function appendLines(items) {
        const atBottom = (els.logs.scrollTop + els.logs.clientHeight + 10) >= els.logs.scrollHeight;
        const frag = document.createDocumentFragment();
        for (const it of items) {
          const div = document.createElement('div');
          div.textContent = it.line;
          frag.appendChild(div);
          sinceId = it.id;
        }
        els.logs.appendChild(frag);
        if (els.autoscroll.checked && (atBottom || items.length > 50)) {
          els.logs.scrollTop = els.logs.scrollHeight;
        }
      }

      async function pollLogs() {
        if (polling) return;
        polling = true;
        try {
          const u = new URL(location.origin + '/api/logs');
          u.searchParams.set('limit', els.limit.value || '400');
          if (sinceId !== null) u.searchParams.set('since_id', String(sinceId));
          const r = await fetch(u);
          const j = await r.json();
          if (j.success && j.items.length > 0) appendLines(j.items);
        } catch (e) {
          // ignore transient errors
        } finally {
          polling = false;
          setTimeout(pollLogs, 1200);
        }
      }

      async function refreshState() {
        try {
          const [s, m, p] = await Promise.all([
            fetch('/api/state').then(r => r.json()),
            fetch('/api/matches').then(r => r.json()),
            fetch('/api/profile').then(r => r.json()),
          ]);
          if (s && s.stats) {
            els.statConfirmed.textContent = s.stats.confirmed_count ?? 0;
            els.statPoss.textContent = s.stats.possibilities_count ?? 0;
            els.statPartial.textContent = s.stats.partial_count ?? 0;
            els.lastMid.textContent = s.stats.last_message_id || '—';
          }
          if (m) {
            const items = []
              .concat((m.confirmed || []).slice(-5).map(x => ({ t: '🎯', s: x.subject })))
              .concat((m.possibilities || []).slice(-5).map(x => ({ t: '🤔', s: x.subject })))
              .concat((m.partial || []).slice(-5).map(x => ({ t: '📧', s: x.subject })));
            els.matches.innerHTML = '';
            for (const it of items.slice(-10)) {
              const li = document.createElement('li');
              li.textContent = it.t + ' ' + (it.s || 'No subject');
              els.matches.appendChild(li);
            }
          }
          if (p) {
            els.profileBox.textContent = (p.name || 'Unknown') + ' • ' + (p.registration_number || 'No Reg');
          }
        } catch (e) {
          // ignore transient errors
        } finally {
          setTimeout(refreshState, 4000);
        }
      }

      els.start.addEventListener('click', startRunner);
      els.check.addEventListener('click', checkEmail);
      els.clear.addEventListener('click', () => { els.logs.textContent = ''; sinceId = null; });
      els.backfillBtn.addEventListener('click', async () => {
        try {
          els.backfillBtn.disabled = true;
          const count = parseInt(els.backfillCount.value || '50', 10);
          const r = await fetch('/api/backfill', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ count }) });
          const j = await r.json();
          els.status.textContent = j.message || (j.success ? 'Backfill started' : 'Failed to start backfill');
        } catch (e) {
          els.status.textContent = 'Backfill failed: ' + e;
        } finally {
          setTimeout(() => els.backfillBtn.disabled = false, 2000);
        }
      });
      refreshStatus();
      pollLogs();
      refreshState();
    </script>
  </body>
</html>
"""
    return html


@app.route('/matches', methods=['GET'])
def matches_page():
    """Page to browse all matches with filtering and quick stats."""
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Shortlist • Matches</title>
    <style>
      :root { color-scheme: light dark; }
      :root.light { --bg:#f7fafc; --panel:#ffffff; --border:#e5e7eb; --muted:#475569; --text:#0f172a; --accent:#2563eb; }
      :root.dark { --bg:#0b0f17; --panel:#121826; --border:#1f2937; --muted:#94a3b8; --text:#e2e8f0; --accent:#3b82f6; }
      body { margin: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; }
      header { position: sticky; top: 0; z-index: 10; background: color-mix(in oklab, var(--bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
      .wrap { max-width: 1100px; margin: 0 auto; padding: 14px; }
      a { text-decoration: none; color: inherit; }
      .tabs { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
      .tab { padding: 8px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--panel); cursor: pointer; color: var(--text); text-decoration:none; }
      .tab.active { outline: 2px solid var(--accent); }
      .grid { display: grid; grid-template-columns: 1fr; gap: 14px; padding: 14px; position: relative; }
      .bg-blob { position:absolute; inset:-8% -8% auto auto; width: 320px; height: 320px; border-radius: 50%; filter: blur(60px); opacity:.25; background: radial-gradient(closest-side, var(--accent), transparent); pointer-events:none; }
      .bg-blob.b2 { left:-8%; top:30%; right:auto; background: radial-gradient(closest-side, color-mix(in oklab, var(--accent) 40%, #22c55e), transparent); }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px color-mix(in oklab, var(--bg) 75%, #000); }
      .card h2 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 16px; background: color-mix(in oklab, var(--panel) 85%, var(--bg)); }
      .section { padding: 12px 14px; }
      .muted { color: var(--muted); }
      .list { display: grid; gap: 10px; }
      .row { display: grid; gap: 10px; grid-template-columns: 28px 1fr 200px; align-items: center; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: color-mix(in oklab, var(--panel) 88%, var(--bg)); transition: transform .15s ease, border-color .15s ease; }
      .row:hover { transform: translateY(-1px); border-color: color-mix(in oklab, var(--accent) 50%, var(--border)); }
      .pill { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); }
      .pill.c { background: rgba(34,197,94,.12); border-color: rgba(34,197,94,.3); color: #86efac; }
      .pill.p { background: rgba(59,130,246,.12); border-color: rgba(59,130,246,.3); color: #93c5fd; }
      .pill.r { background: rgba(234,179,8,.12); border-color: rgba(234,179,8,.3); color: #fde68a; }
      .controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
      input, select { background: var(--panel); border:1px solid var(--border); color: var(--text); border-radius:8px; padding:6px 8px; }
      .pager { display:flex; gap:10px; align-items:center; }
      .btn { background: var(--accent); color:#fff; border:0; padding:8px 12px; border-radius:8px; cursor:pointer; }
      .btn.secondary { background: color-mix(in oklab, var(--panel) 85%, var(--text)); color: var(--text); border: 1px solid var(--border); }
    </style>
  </head>
  <body>
    <header>
      <div class="wrap">
        <div style="display:flex; align-items:center; gap:12px; justify-content: space-between;">
          <div class="tabs">
            <a href="/" class="tab">Home</a>
            <span class="tab active">Matches</span>
            <a href="/calendar" class="tab">Calendar</a>
            <a href="/profile" class="tab">Profile</a>
            <a href="/logs" class="tab">Logs</a>
          </div>
          <div>
            <button id="theme" class="btn secondary">Toggle theme</button>
          </div>
        </div>
        <div class="controls" style="margin-top:10px;">
          <input id="q" placeholder="Search subject or from…">
          <select id="type">
            <option value="">All</option>
            <option value="CONFIRMED_MATCH">Confirmed</option>
            <option value="POSSIBILITY">Possibility</option>
            <option value="PARTIAL_MATCH">Partial</option>
          </select>
          <span class="muted" id="count">—</span>
          <span class="pager" style="margin-left:auto">
            <button id="prev" class="btn secondary">Prev</button>
            <span id="page" class="muted">1</span>
            <button id="next" class="btn secondary">Next</button>
            <select id="ps">
              <option>25</option><option selected>50</option><option>100</option><option>200</option>
            </select>
          </span>
        </div>
      </div>
    </header>

    <div class="wrap grid">
      <div class="bg-blob"></div>
      <div class="bg-blob b2"></div>
      <div class="card">
        <h2>Matches</h2>
        <div class="section">
          <div class="list" id="list"></div>
        </div>
      </div>
    </div>

    <script>
      // Theme alignment with other pages
      (function(){
        function applyTheme() {
          const t = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
          document.documentElement.classList.remove('light','dark');
          document.documentElement.classList.add(t);
        }
        applyTheme();
        const themeBtn = document.getElementById('theme');
        themeBtn.addEventListener('click', () => {
          const now = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
          localStorage.setItem('theme', now);
          applyTheme();
        });
      })();
      const els = {
        list: document.getElementById('list'),
        q: document.getElementById('q'),
        type: document.getElementById('type'),
        count: document.getElementById('count'),
        prev: document.getElementById('prev'),
        next: document.getElementById('next'),
        page: document.getElementById('page'),
        ps: document.getElementById('ps'),
      };
      let all = [];
      let view = [];
      let page = 1;

      function render(items, paged=true) {
        const pageSize = parseInt(els.ps.value || '50', 10);
        const total = items.length;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        if (paged) {
          if (page > totalPages) page = totalPages;
          const start = (page - 1) * pageSize;
          view = items.slice(start, start + pageSize);
        } else {
          view = items;
        }
        els.page.textContent = page + ' / ' + totalPages;
        els.count.textContent = total + ' results';
        const frag = document.createDocumentFragment();
        for (const it of view) {
          const row = document.createElement('div');
          row.className = 'row';
          const icon = document.createElement('div');
          icon.textContent = it.match_type === 'CONFIRMED_MATCH' ? '🎯' : it.match_type === 'POSSIBILITY' ? '🤔' : '📧';
          const main = document.createElement('div');
          main.innerHTML = '<div style="font-weight:600;">' + (it.subject || 'No subject') + '</div>' +
            '<div class="muted" style="margin-top:4px;">' + (it.from_display_name || '') + ' &lt;' + (it.from_email || '') + '&gt;</div>';
          const tag = document.createElement('div');
          const cls = it.match_type === 'CONFIRMED_MATCH' ? 'c' : it.match_type === 'POSSIBILITY' ? 'p' : 'r';
          tag.className = 'pill ' + cls;
          tag.textContent = it.match_type.replace('_', ' ');
          row.appendChild(icon); row.appendChild(main); row.appendChild(tag);
          frag.appendChild(row);
        }
        els.list.innerHTML = '';
        els.list.appendChild(frag);
      }

      function applyFilter(resetPage=true) {
        const q = els.q.value.trim().toLowerCase();
        const t = els.type.value;
        let items = all.slice();
        if (t) items = items.filter(x => x.match_type === t);
        if (q) items = items.filter(x => (x.subject || '').toLowerCase().includes(q) || (x.from_display_name || '').toLowerCase().includes(q) || (x.from_email || '').toLowerCase().includes(q));
        if (resetPage) page = 1;
        render(items, true);
      }

      async function load() {
        const s = await fetch('/api/state').then(r => r.json());
        const merged = []
          .concat((s.state.confirmed_matches || []).map(x => ({...x, match_type: 'CONFIRMED_MATCH'})))
          .concat((s.state.possibilities || []).map(x => ({...x, match_type: 'POSSIBILITY'})))
          .concat((s.state.partial_matches || []).map(x => ({...x, match_type: 'PARTIAL_MATCH'})));
        all = merged.reverse().slice(0, 500);
        applyFilter();
      }

      els.q.addEventListener('input', () => applyFilter(true));
      els.type.addEventListener('change', () => applyFilter(true));
      els.ps.addEventListener('change', () => applyFilter(true));
      els.prev.addEventListener('click', () => { if (page > 1) { page--; applyFilter(false); } });
      els.next.addEventListener('click', () => { page++; applyFilter(false); });
      load();
    </script>
  </body>
</html>
"""
    return html


@app.route('/profile', methods=['GET'])
def profile_page():
    """Profile viewer/editor (basic fields persisted in profile.json)."""
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Shortlist • Profile</title>
    <style>
      :root { color-scheme: light dark; }
      :root.light { --bg:#f7fafc; --panel:#ffffff; --border:#e5e7eb; --muted:#475569; --text:#0f172a; --accent:#2563eb; }
      :root.dark { --bg:#0b0f17; --panel:#121826; --border:#1f2937; --muted:#94a3b8; --text:#e2e8f0; --accent:#3b82f6; }
      body { margin: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; }
      header { position: sticky; top: 0; z-index: 10; background: color-mix(in oklab, var(--bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
      .wrap { max-width: 800px; margin: 0 auto; padding: 14px; }
      .tabs { display: flex; gap: 10px; margin-top: 10px; }
      .tab { padding: 8px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--panel); cursor: pointer; color: var(--text); text-decoration: none; }
      .tab.active { outline: 2px solid var(--accent); }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; margin: 16px; box-shadow: 0 10px 30px color-mix(in oklab, var(--bg) 75%, #000); }
      .card h2 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 16px; background: color-mix(in oklab, var(--panel) 85%, var(--bg)); }
      .section { padding: 12px 14px; }
      label { display:block; margin: 10px 0 4px; color: var(--muted); }
      input, textarea { width: 100%; background: var(--panel); border:1px solid var(--border); color: var(--text); border-radius:8px; padding:8px 10px; }
      .btn { background: var(--accent); color: white; border: 0; padding: 10px 14px; border-radius: 10px; cursor: pointer; font-weight: 600; }
      .muted { color: var(--muted); }
      .avatar { width:72px; height:72px; border-radius:50%; display:grid; place-items:center; font-weight:800; letter-spacing:.5px; background: linear-gradient(135deg, color-mix(in oklab, var(--accent) 70%, transparent), color-mix(in oklab, var(--accent2, #22c55e) 70%, transparent)); color:white; }
      .row { display:flex; align-items:center; gap:12px; }
    </style>
  </head>
  <body>
    <header>
      <div class="wrap">
        <div class="tabs">
          <a href="/" class="tab">Home</a>
          <a href="/matches" class="tab">Matches</a>
          <a href="/calendar" class="tab">Calendar</a>
          <span class="tab active">Profile</span>
          <span style="margin-left:auto"><a class="tab" href="/logs">Logs</a></span>
        </div>
      </div>
    </header>

    <div class="card">
      <h2>Profile</h2>
      <div class="section">
        <div class="row" style="margin-bottom:10px;">
          <div class="avatar" id="avatar">U</div>
          <div>
            <div style="font-weight:700" id="avatarName">User</div>
            <div class="muted" id="avatarEmail">—</div>
          </div>
        </div>
        <div class="muted" id="status" style="margin:8px 0;"></div>
        <label>Name</label>
        <input id="name">
        <label>Registration Number</label>
        <input id="reg">
        <label>Gmail Display Name</label>
        <input id="gmail">
        <div style="margin-top:12px;">
          <button id="save" class="btn">Save</button>
        </div>
      </div>
    </div>

    <script>
      // Theme preference from the home/logs pages
      (function(){
        function applyTheme() {
          const t = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
          document.documentElement.classList.remove('light','dark');
          document.documentElement.classList.add(t);
        }
        applyTheme();
      })();
      const els = { name: document.getElementById('name'), reg: document.getElementById('reg'), gmail: document.getElementById('gmail'), save: document.getElementById('save'), status: document.getElementById('status') };
      const avEls = { a: document.getElementById('avatar'), n: document.getElementById('avatarName'), e: document.getElementById('avatarEmail') };
      let original = {};

      async function load() {
        const p = await fetch('/api/profile').then(r => r.json());
        original = p || {};
        els.name.value = p.name || '';
        els.reg.value = p.registration_number || '';
        els.gmail.value = p.gmail_display_name || '';
        const initials = (p.name || p.gmail_display_name || p.gmail_address || 'U').split(' ').slice(0,2).map(s => s[0] || '').join('').toUpperCase();
        avEls.a.textContent = initials || 'U';
        avEls.n.textContent = p.name || p.gmail_display_name || 'User';
        avEls.e.textContent = p.gmail_address || p.personal_email || '';
      }

      async function save() {
        try {
          els.save.disabled = true;
          const body = {
            name: els.name.value.trim(),
            registration_number: els.reg.value.trim(),
            gmail_display_name: els.gmail.value.trim(),
          };
          const r = await fetch('/api/profile', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
          const j = await r.json();
          els.status.textContent = j.message || (j.success ? 'Saved' : 'Failed');
        } catch (e) {
          els.status.textContent = 'Save failed: ' + e;
        } finally {
          els.save.disabled = false;
        }
      }

      els.save.addEventListener('click', save);
      load();
    </script>
  </body>
</html>
"""
    return html


@app.route('/calendar', methods=['GET'])
def calendar_page():
    """Calendar page showing upcoming events."""
    html = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Shortlist • Calendar</title>
    <style>
      :root { color-scheme: light dark; }
      :root.light { --bg:#f7fafc; --panel:#ffffff; --border:#e5e7eb; --muted:#475569; --text:#0f172a; --accent:#2563eb; }
      :root.dark { --bg:#0b0f17; --panel:#121826; --border:#1f2937; --muted:#94a3b8; --text:#e2e8f0; --accent:#3b82f6; }
      body { margin: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; }
      header { position: sticky; top: 0; z-index: 10; background: color-mix(in oklab, var(--bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
      .wrap { max-width: 900px; margin: 0 auto; padding: 14px; }
      .tabs { display: flex; gap: 10px; margin-top: 10px; }
      .tab { padding: 8px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--panel); cursor: pointer; color: var(--text); text-decoration: none; }
      .tab.active { outline: 2px solid var(--accent); }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; margin: 16px; box-shadow: 0 10px 30px color-mix(in oklab, var(--bg) 75%, #000); }
      .card h2 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 16px; background: color-mix(in oklab, var(--panel) 85%, var(--bg)); }
      .section { padding: 12px 14px; }
      .muted { color: var(--muted); }
      .list { display: grid; gap: 16px; position: relative; padding-left: 16px; }
      .list::before { content:""; position:absolute; left: 6px; top:0; bottom:0; width:2px; background: color-mix(in oklab, var(--accent) 40%, var(--border)); border-radius:2px; }
      .row { display: grid; gap: 10px; grid-template-columns: 1fr 200px; align-items: center; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: color-mix(in oklab, var(--panel) 88%, var(--bg)); position: relative; }
      .row::before { content:""; position:absolute; left:-12px; top: 14px; width: 12px; height: 12px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px color-mix(in oklab, var(--accent) 30%, transparent); }
      .k { font-size: 12px; color: var(--muted); }
    </style>
  </head>
  <body>
    <header>
      <div class="wrap">
        <div class="tabs">
          <a href="/" class="tab">Home</a>
          <a href="/matches" class="tab">Matches</a>
          <span class="tab active">Calendar</span>
          <a href="/profile" class="tab">Profile</a>
          <span style="margin-left:auto"><a class="tab" href="/logs">Logs</a></span>
        </div>
      </div>
    </header>

    <div class="card">
      <h2>Upcoming Events</h2>
      <div class="section">
        <div style="display:flex; gap:10px; align-items:center; justify-content: space-between;">
          <div class="muted" id="status">Fetching…</div>
          <div style="display:flex; gap:8px; align-items:center;">
            <span class="k" id="updatedAt"></span>
            <button id="refresh" style="background: var(--accent); color:#fff; border:0; padding:8px 12px; border-radius:8px; cursor:pointer;">Refresh</button>
          </div>
        </div>
        <div class="list" id="list"></div>
      </div>
    </div>

    <script>
      (function(){
        function applyTheme() {
          const t = localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
          document.documentElement.classList.remove('light','dark');
          document.documentElement.classList.add(t);
        }
        applyTheme();
      })();
      const els = { list: document.getElementById('list'), status: document.getElementById('status'), updatedAt: document.getElementById('updatedAt'), refresh: document.getElementById('refresh') };
      let loading = false;
      async function load() {
        if (loading) return;
        loading = true;
        try {
          const r = await fetch('/api/calendar-events');
          const j = await r.json();
          if (!j.events) throw new Error(j.message || 'No events');
          els.status.textContent = (j.events || []).length + ' events';
          const frag = document.createDocumentFragment();
          for (const e of j.events) {
            const row = document.createElement('div');
            row.className = 'row';
            const title = document.createElement('div');
            title.innerHTML = '<div style="font-weight:600;">' + (e.summary || 'No Title') + '</div>' +
                              '<div class="k">' + (e.location || '') + '</div>';
            const meta = document.createElement('div');
            meta.innerHTML = '<div>' + (e.start || '') + '</div>' +
                             (e.htmlLink ? '<div class="k"><a href="' + e.htmlLink + '" target="_blank">open</a></div>' : '');
            row.appendChild(title); row.appendChild(meta);
            frag.appendChild(row);
          }
          els.list.innerHTML = '';
          els.list.appendChild(frag);
          const now = new Date();
          els.updatedAt.textContent = 'Updated ' + now.toLocaleTimeString();
        } catch (e) {
          els.status.textContent = 'Failed: ' + e;
        } finally {
          loading = false;
        }
      }
      els.refresh.addEventListener('click', load);
      load();
      setInterval(load, 10000);
    </script>
  </body>
</html>
"""
    return html

if __name__ == '__main__':
    app.run(debug=True, port=5000)

