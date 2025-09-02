# app/runner.py
import time
from pathlib import Path

from app.login import get_gmail_client_and_profile
from app.parsers import parse_email_attachments
from app.calendar_service import create_calendar_event, should_create_calendar_event
from app.match_utils import best
from app.email_utils import header, parse_from_header, split_name_and_reg, extract_text
from app.match_logic import evaluate_match, evaluate_content_match
from app.state_utils import (
    load_state as load_state_file,
    save_state as save_state_file,
    save_profile as save_profile_file,
    log_match_to_data,
    update_state_with_match,
)

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

    print("Sandbox runner started. Watching INBOX for newest emails...")
    print(f"Profile: {profile.get('name', 'Unknown')} ({profile.get('registration_number', 'No reg')})")
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

                # 2) Extract Name + RegNo from that display name
                parsed_name, reg = split_name_and_reg(display_name)

                # 3) Check for matches with logged-in user's profile using new criteria (headers)
                match_type_header = evaluate_match(profile, parsed_name, reg, addr)

                # 3b) Extract body early and evaluate content-based match (subject/body)
                body = extract_text(payload)
                match_type_content = evaluate_content_match(profile, subject or "", body or "")

                # Choose strongest between header-based and content-based
                match_type = best(match_type_header, match_type_content)
                
                # 4) Parse attachments for ALL emails (whether they match or not)
                print(f"📎 Checking attachments for email {mid}...")
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
                        print(f"📎 Attachments upgraded match type to: {overall_match_type}")
                
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
                        
                        print(f"{MATCH_ICONS.get(overall_match_type, '❓')} {overall_match_type} FOUND!")
                        
                        # Create calendar event for confirmed shortlisting emails
                        if should_create_calendar_event(email_data):
                            print("📅 Creating calendar event...")
                            event_created = create_calendar_event(
                                subject,
                                body,
                                mid
                            )
                            if event_created:
                                print("✅ Calendar event created successfully!")
                            else:
                                print("❌ Failed to create calendar event")
                    
                    # Report attachment analysis for all emails with attachments
                    if attachment_results['total_attachments'] > 0:
                        print(f"📎 Analyzed {attachment_results['total_attachments']} attachments:")
                        print(f"   └─ Confirmed matches: {attachment_results['summary']['confirmed_matches']}")
                        print(f"   └─ Possibilities: {attachment_results['summary']['possibilities']}")
                        print(f"   └─ Partial matches: {attachment_results['summary']['partial_matches']}")
                        
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
                                    print(f"   {status_icon} {filename} (document): {result_match} [rows: C={c} P={p} R={r}]")
                                else:
                                    print(f"   {status_icon} {filename} ({parser_used}): {result_match}")
                            else:
                                print(f"   ❌ {filename}: Unsupported format")

                # 7) Update profile: only fill name/reg if we parsed them from email headers
                # and they're not already set from login
                updated = False
                if display_name and display_name != profile.get("gmail_display_name"):
                    profile["gmail_display_name"] = display_name; updated = True
                
                # Only update name/reg from email if not already set from Google account
                if parsed_name and not profile.get("name"):
                    profile["name"] = parsed_name; updated = True
                if reg and not profile.get("registration_number"):
                    profile["registration_number"] = reg; updated = True
                    
                if updated:
                    save_profile_file(profile, PROFILE_FILE)
                    print("Profile updated:", {
                        "name": profile.get("name"),
                        "registration_number": profile.get("registration_number"),
                        "gmail_display_name": profile.get("gmail_display_name"),
                    })

                # 8) Print summary (reuse body extracted earlier)
                print(f"\nNew email {mid}\nFrom: {display_name} <{addr}>\nSubject: {subject}")
                if parsed_name or reg:
                    print(f"Parsed: Name='{parsed_name}', Reg='{reg}'")
                print(f"—\n{(body or '')[:400]}...\n")

                # 9) Persist last processed message id
                state["last_message_id"] = mid
                save_state_file(state, STATE_FILE)
                
                # Print summary statistics
                print(f"📊 Running totals:")
                print(f"   🎯 Confirmed: {len(state.get('confirmed_matches', []))}")
                print(f"   🤔 Possibilities: {len(state.get('possibilities', []))}")
                print(f"   📧 Partial: {len(state.get('partial_matches', []))}")

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            print("Stopping runner.")
            break
        except Exception as e:
            print("Error:", e)
            time.sleep(min(300, poll_seconds * 2))

if __name__ == "__main__":
    run()
