# app/runner.py
import time
from pathlib import Path

from app.login import get_gmail_client_and_profile
from app.parsers import parse_email_attachments
from app.calendar_service import create_calendar_event, should_create_calendar_event
from app.match_utils import best
from app.email_utils import header, parse_from_header, split_name_and_reg, extract_text
from app.match_logic import evaluate_content_match
# Simple whitelist of trusted CDC sender addresses. Only emails from these
# senders are processed by downstream microservices.
CDC_SENDER_WHITELIST = {
    "vitianscdc2026@vitstudent.ac.in",
    "krish.verma2022@vitstudent.ac.in",
    "tanmay.agrawal2022@vitstudent.ac.in",
}
from app.state_utils import (
    load_state as load_state_file,
    save_state as save_state_file,
    save_profile as save_profile_file,
    log_match_to_data,
    update_state_with_match,
)
from app.log_stream import log

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
PROFILE_FILE = ROOT / "profile.json"
DATA_DIR = ROOT / "data"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Icons for concise output
MATCH_ICONS = {
    "CONFIRMED_MATCH": "🎯",
    "POSSIBILITY": "🤔",
    "PARTIAL_MATCH": "📧",
}

def newest_message_id(service) -> str | None:
    res = service.users().messages().list(userId="me", q="in:inbox", maxResults=1).execute()
    msgs = res.get("messages", [])
    return msgs[0]["id"] if msgs else None

def fetch_full(service, msg_id):
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

# (helpers for header parsing and body extraction are imported from app.email_utils)

# (match evaluation helpers are imported from app.match_logic)

# (state helpers are imported from app.state_utils)

def run():
    service, profile = get_gmail_client_and_profile()
    state = load_state_file(STATE_FILE)

    log("Sandbox runner started. Watching INBOX for newest emails...")
    log(f"Profile: {profile.get('name', 'Unknown')} ({profile.get('registration_number', 'No reg')})")
    poll_seconds = 30

    while True:
        try:
            mid = newest_message_id(service)
            if mid and mid != state.get("last_message_id"):
                msg = fetch_full(service, mid)
                payload = msg.get("payload", {})
                headers = payload.get("headers", [])

                # 1) Always prefer the sender's display name from the email header
                from_raw = header(headers, "From")
                subject = header(headers, "Subject")
                display_name, addr = parse_from_header(from_raw)

                # Intentionally ignore To/Cc/Bcc for matching. Sender is only used
                # for the CDC whitelist check before running any microservice.

                # 2) Extract Name + RegNo from display name only for potential one-time
                # profile fill-in (not used for matching logic).
                parsed_name, reg = split_name_and_reg(display_name)

                # 3b) Extract body early and enforce sender whitelist before any microservice
                body = extract_text(payload)
                sender = (addr or "").strip().lower()
                if sender not in CDC_SENDER_WHITELIST:
                    print(f"Sender not whitelisted: {sender}. Skipping {mid}.")
                    # Still advance the pointer so we don't reprocess
                    state["last_message_id"] = mid
                    save_state_file(state, STATE_FILE)
                    time.sleep(poll_seconds)
                    continue

                # Evaluate content-based match (subject/body) only for placement-like emails
                match_type = evaluate_content_match(profile, subject or "", body or "")
                
                # 4) Parse attachments for ALL emails (whether they match or not)
                log(f"📎 Checking attachments for email {mid}...")
                attachment_results = parse_email_attachments(service, mid, profile)
                
                # 5) Determine overall match considering both email content and attachments
                overall_match_type = match_type
                att_overall = attachment_results.get('overall_match_type', 'NO_MATCH')
                if att_overall != 'NO_MATCH':
                    # If attachments have a stronger match, use that
                    prev = overall_match_type
                    upgraded = best(prev, att_overall)
                    if upgraded != prev:
                        overall_match_type = upgraded
                        log(f"📎 Attachments upgraded match type to: {overall_match_type}")
                
                # 6) If we have any match (email content or attachments), log it
                if overall_match_type != "NO_MATCH" or attachment_results['total_attachments'] > 0:
                    # body already extracted above
                    email_data = {
                        "message_id": mid,
                        "from_display_name": display_name,
                        "from_email": addr,
                        "parsed_name": parsed_name,
                        "parsed_reg": reg,
                        "subject": subject,
                        "body_preview": body[:400] if body else "",
                        "match_type": overall_match_type,
                        "attachments": attachment_results
                    }
                    
                    # Only log to data directory if there's an actual match
                    if overall_match_type != "NO_MATCH":
                        
                        log_match_to_data(profile, email_data, DATA_DIR)
                        update_state_with_match(state, email_data, overall_match_type)
                        
                        log(f"{MATCH_ICONS.get(overall_match_type, '❓')} {overall_match_type} FOUND!")
                        
                        # Create calendar event for confirmed shortlisting emails
                        if should_create_calendar_event(email_data):
                            log("📅 Creating calendar event...")
                            event_created = create_calendar_event(
                                subject,
                                body,
                                mid
                            )
                            if event_created:
                                log("✅ Calendar event created successfully!")
                            else:
                                log("❌ Failed to create calendar event")
                    
                    # Report attachment analysis for all emails with attachments
                    if attachment_results['total_attachments'] > 0:
                        log(f"📎 Analyzed {attachment_results['total_attachments']} attachments:")
                        log(f"   └─ Confirmed matches: {attachment_results['summary']['confirmed_matches']}")
                        log(f"   └─ Possibilities: {attachment_results['summary']['possibilities']}")
                        log(f"   └─ Partial matches: {attachment_results['summary']['partial_matches']}")
                        
                        # Show individual files processed
                        for result in attachment_results.get('parsing_results', []):
                            filename = result.get('filename', 'unknown')
                            parser_used = result.get('parser_used', 'none')
                            parsing_result = result.get('parsing_result', {})
                            # Derive a sensible per-file match for document parser outputs
                            if 'total_rows' in parsing_result:
                                c = len(parsing_result.get('confirmed_matches', []))
                                p = len(parsing_result.get('possibilities', []))
                                r = len(parsing_result.get('partial_matches', []))
                                if c > 0:
                                    result_match = 'CONFIRMED_MATCH'
                                elif p > 0:
                                    result_match = 'POSSIBILITY'
                                elif r > 0:
                                    result_match = 'PARTIAL_MATCH'
                                else:
                                    result_match = 'NO_MATCH'
                            else:
                                result_match = parsing_result.get('match_type', 'NO_MATCH')
                            
                            if parser_used != 'none':
                                status_icon = "✅" if result_match != 'NO_MATCH' else "📄"
                                # Include counts for document parser to avoid confusion
                                if 'total_rows' in parsing_result:
                                    c = len(parsing_result.get('confirmed_matches', []))
                                    p = len(parsing_result.get('possibilities', []))
                                    r = len(parsing_result.get('partial_matches', []))
                                    log(f"   {status_icon} {filename} (document): {result_match} [rows: C={c} P={p} R={r}]")
                                else:
                                    log(f"   {status_icon} {filename} ({parser_used}): {result_match}")
                            else:
                                log(f"   ❌ {filename}: Unsupported format")

                # 7) Update profile: only fill name/reg if we parsed them from email headers
                # and they're not already set from login. Do not store or update gmail_display_name.
                updated = False
                if parsed_name and not profile.get("name"):
                    profile["name"] = parsed_name; updated = True
                if reg and not profile.get("registration_number"):
                    profile["registration_number"] = reg; updated = True
                if updated:
                    save_profile_file(profile, PROFILE_FILE)
<<<<<<< HEAD
                    log("Profile updated: " + str({
                        "name": profile.get("name"),
                        "registration_number": profile.get("registration_number"),
                        "gmail_display_name": profile.get("gmail_display_name"),
                    }))
=======
>>>>>>> 621266f485c635371474bbae852cc98b572a50de

                # 8) Print summary (reuse body extracted earlier)
                log(f"\nNew email {mid}\nFrom: {display_name} <{addr}>\nSubject: {subject}")
                if parsed_name or reg:
                    log(f"Parsed: Name='{parsed_name}', Reg='{reg}'")
                log(f"—\n{(body or '')[:400]}...\n")

                # 9) Persist last processed message id
                state["last_message_id"] = mid
                save_state_file(state, STATE_FILE)
                
                # Print summary statistics
                log(f"📊 Running totals:")
                log(f"   🎯 Confirmed: {len(state.get('confirmed_matches', []))}")
                log(f"   🤔 Possibilities: {len(state.get('possibilities', []))}")
                log(f"   📧 Partial: {len(state.get('partial_matches', []))}")

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            log("Stopping runner.")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(min(300, poll_seconds * 2))

if __name__ == "__main__":
    run()


def backfill_latest(count: int = 50) -> dict:
    """
    Process the latest 'count' emails from INBOX (newest first).
    Useful to backfill matches from previous emails.
    Returns a summary dict with totals.
    """
    service, profile = get_gmail_client_and_profile()
    state = load_state_file(STATE_FILE)

    count = max(1, min(500, int(count)))
    log(f"🔄 Backfill starting for latest {count} emails...")

    # List latest message ids
    ids: list[str] = []
    try:
        res = service.users().messages().list(userId="me", q="in:inbox", maxResults=count).execute()
        ids = [m["id"] for m in res.get("messages", [])]
    except Exception as e:
        log(f"Backfill failed to list messages: {e}")
        return {"success": False, "processed": 0, "matched": 0, "error": str(e)}

    processed = 0
    matched = 0

    for mid in ids:
        try:
            # Reuse the same per-message processing logic as in the watcher
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
                upgraded = best(overall_match_type, att_overall)
                overall_match_type = upgraded

            if overall_match_type != "NO_MATCH" or attachment_results.get('total_attachments', 0) > 0:
                email_data = {
                    "message_id": mid,
                    "from_display_name": display_name,
                    "from_email": addr,
                    "parsed_name": parsed_name,
                    "parsed_reg": reg,
                    "subject": subject,
                    "body_preview": (body or "")[:400],
                    "match_type": overall_match_type,
                    "attachments": attachment_results
                }
                if overall_match_type != "NO_MATCH":
                    log_match_to_data(profile, email_data, DATA_DIR)
                    update_state_with_match(state, email_data, overall_match_type)
                    matched += 1

            # keep advancing last_message_id so normal runner will skip these next time
            if mid != state.get("last_message_id"):
                state["last_message_id"] = mid
                save_state_file(state, STATE_FILE)

            processed += 1
        except Exception as e:
            log(f"Backfill error for {mid}: {e}")

    log(f"✅ Backfill complete. Processed: {processed}, Matches: {matched}")
    return {"success": True, "processed": processed, "matched": matched}
