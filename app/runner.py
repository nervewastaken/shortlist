# app/runner.py
import time
import json
import re
import base64
from pathlib import Path
from email.utils import parseaddr
from email.header import decode_header, make_header

from app.login import get_gmail_client_and_profile
from app.parsers import parse_email_attachments
from app.calendar_service import create_calendar_event, should_create_calendar_event

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "state.json"
PROFILE_FILE = ROOT / "profile.json"
DATA_DIR = ROOT / "data"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# VIT reg-no pattern, e.g., 22BCE2382
REG_RE = re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE)

# Phrases to strip from display names (common in list/forwarded mail)
VIA_CLAUSES = [
    r"\s+via\s+.*$",                # "via Something"
    r"\s+\(via\s+.*\)$",            # "(via Something)"
    r"\s*[-–]\s*Google\s+Groups$",  # "- Google Groups"
]

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "last_message_id": None,
        "confirmed_matches": [],
        "possibilities": [],
        "partial_matches": []
    }

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def save_profile(profile):
    PROFILE_FILE.write_text(json.dumps(profile, indent=2))

def decode_display_name(raw: str) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return raw.strip()

def clean_display_name(name: str) -> str:
    if not name:
        return ""
    out = name.strip()
    for pat in VIA_CLAUSES:
        out = re.sub(pat, "", out, flags=re.IGNORECASE).strip()
    # Remove extra quotes
    out = out.strip("'\" ").strip()
    # Collapse whitespace
    out = re.sub(r"\s{2,}", " ", out)
    return out

def parse_from_header(from_value: str):
    """
    Return a cleaned display name and email address from a From header.
    """
    raw_name, addr = parseaddr(from_value or "")
    name = decode_display_name(raw_name)
    name = clean_display_name(name)
    return name, addr

def split_name_and_reg(display_name: str):
    """
    Extract reg number from display name; the remainder is the person's name.
    """
    if not display_name:
        return "", ""
    m = REG_RE.search(display_name)
    reg = m.group(0).upper() if m else ""
    name = display_name
    if reg:
        name = re.sub(re.escape(reg), "", name, flags=re.IGNORECASE).strip()
    # Remove any trailing commas or stray separators
    name = re.sub(r"[,\-–]+$", "", name).strip()
    name = re.sub(r"\s{2,}", " ", name)
    return name, reg

def newest_message_id(service) -> str | None:
    res = service.users().messages().list(userId="me", q="in:inbox", maxResults=1).execute()
    msgs = res.get("messages", [])
    return msgs[0]["id"] if msgs else None

def fetch_full(service, msg_id):
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

def header(headers, key):
    for h in headers or []:
        if h.get("name","").lower() == key.lower():
            return h.get("value","")
    return ""

def extract_text(payload):
    # Prefer text/plain parts
    if "parts" in payload:
        for p in payload["parts"]:
            if p.get("mimeType","").startswith("text/plain"):
                data = p.get("body",{}).get("data")
                if data:
                    return base64.urlsafe_b64decode(data).decode(errors="ignore")
    data = payload.get("body",{}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode(errors="ignore")
    return ""

def check_name_match(profile_name: str, email_name: str) -> bool:
    """
    Check if the profile name matches the email name.
    This does a case-insensitive comparison and handles partial matches.
    """
    if not profile_name or not email_name:
        return False
    
    profile_name = profile_name.lower().strip()
    email_name = email_name.lower().strip()
    
    # Exact match
    if profile_name == email_name:
        return True
    
    # Check if profile name words are all present in email name
    profile_words = set(profile_name.split())
    email_words = set(email_name.split())
    
    # All profile name words should be in email name
    return profile_words.issubset(email_words)

def check_email_match(profile_email: str, email_addr: str) -> bool:
    """
    Check if the profile email matches the sender email.
    """
    if not profile_email or not email_addr:
        return False
    return profile_email.lower().strip() == email_addr.lower().strip()

def evaluate_match(profile: dict, parsed_name: str, parsed_reg: str, sender_email: str) -> str:
    """
    Evaluate the type of match based on the new criteria:
    - If name + (reg OR gmail_address OR personal_email) exists: CONFIRMED_MATCH
    - If only name exists: POSSIBILITY
    - If only reg/email exists: PARTIAL_MATCH
    - If nothing matches: NO_MATCH
    """
    profile_name = profile.get("name", "")
    profile_reg = profile.get("registration_number", "")
    profile_gmail = profile.get("gmail_address", "")
    profile_personal = profile.get("personal_email", "")
    
    name_match = check_name_match(profile_name, parsed_name)
    reg_match = profile_reg and parsed_reg and profile_reg.upper() == parsed_reg.upper()
    gmail_match = check_email_match(profile_gmail, sender_email)
    personal_match = check_email_match(profile_personal, sender_email)
    
    # Check combinations
    if name_match and (reg_match or gmail_match or personal_match):
        return "CONFIRMED_MATCH"
    elif name_match:
        return "POSSIBILITY"
    elif reg_match or gmail_match or personal_match:
        return "PARTIAL_MATCH"
    else:
        return "NO_MATCH"

def text_contains_name(text: str, name: str) -> bool:
    if not text or not name:
        return False
    # Normalize whitespace and case
    t = re.sub(r"\s+", " ", text).lower()
    n = re.sub(r"\s+", " ", name).lower().strip()
    if not n:
        return False
    # Require that all name words appear in order (loose match)
    parts = [p for p in n.split(" ") if p]
    idx = 0
    for p in parts:
        found = t.find(p, idx)
        if found == -1:
            return False
        idx = found + len(p)
    return True

def evaluate_content_match(profile: dict, subject: str, body: str) -> str:
    """Evaluate match from subject/body content (not just headers).

    - Name match is robust to extra whitespace and order
    - Reg number exact pattern match (e.g., 22BCE2382)
    - Email match for both campus and personal addresses
    """
    text = f"{subject}\n{body}" if body else subject or ""
    text_lower = text.lower()

    prof_name = (profile.get("name") or "").strip()
    prof_reg = (profile.get("registration_number") or "").strip()
    prof_gmail = (profile.get("gmail_address") or "").strip().lower()
    prof_personal = (profile.get("personal_email") or "").strip().lower()

    name_match = text_contains_name(text, prof_name)
    reg_match = bool(prof_reg) and bool(re.search(re.escape(prof_reg), text, re.IGNORECASE))
    gmail_match = bool(prof_gmail) and (prof_gmail in text_lower)
    personal_match = bool(prof_personal) and (prof_personal in text_lower)

    if name_match and (reg_match or gmail_match or personal_match):
        return "CONFIRMED_MATCH"
    elif name_match:
        return "POSSIBILITY"
    elif reg_match or gmail_match or personal_match:
        return "PARTIAL_MATCH"
    return "NO_MATCH"

def log_match_to_data(profile: dict, email_data: dict):
    """
    Log a match between profile and email to the data directory.
    """
    import datetime
    
    timestamp = datetime.datetime.now().isoformat()
    match_data = {
        "timestamp": timestamp,
        "profile": {
            "name": profile.get("name", ""),
            "registration_number": profile.get("registration_number", ""),
            "gmail_address": profile.get("gmail_address", ""),
            "personal_email": profile.get("personal_email", "")
        },
        "email": {
            "message_id": email_data.get("message_id", ""),
            "from_display_name": email_data.get("from_display_name", ""),
            "from_email": email_data.get("from_email", ""),
            "parsed_name": email_data.get("parsed_name", ""),
            "parsed_reg": email_data.get("parsed_reg", ""),
            "subject": email_data.get("subject", ""),
            "body_preview": email_data.get("body_preview", "")
        },
        "match_type": email_data.get("match_type", ""),
        "attachments": email_data.get("attachments", [])
    }
    
    # Create filename with timestamp
    filename = f"match_{timestamp.replace(':', '-').replace('.', '_')}.json"
    match_file = DATA_DIR / filename
    
    try:
        match_file.write_text(json.dumps(match_data, indent=2))
        print(f"✓ Match logged to: {filename}")
    except Exception as e:
        print(f"Error saving match data: {e}")

def update_state_with_match(state: dict, email_data: dict, match_type: str):
    """
    Update the state with match information based on match type.
    """
    match_entry = {
        "message_id": email_data.get("message_id", ""),
        "timestamp": time.time(),
        "from_display_name": email_data.get("from_display_name", ""),
        "from_email": email_data.get("from_email", ""),
        "parsed_name": email_data.get("parsed_name", ""),
        "parsed_reg": email_data.get("parsed_reg", ""),
        "subject": email_data.get("subject", "")
    }
    
    if match_type == "CONFIRMED_MATCH":
        state["confirmed_matches"].append(match_entry)
    elif match_type == "POSSIBILITY":
        state["possibilities"].append(match_entry)
    elif match_type == "PARTIAL_MATCH":
        state["partial_matches"].append(match_entry)
    
    # Keep only last 100 entries per category to prevent unlimited growth
    for key in ["confirmed_matches", "possibilities", "partial_matches"]:
        if len(state[key]) > 100:
            state[key] = state[key][-100:]

def run():
    service, profile = get_gmail_client_and_profile()
    state = load_state()

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
                hierarchy = ['CONFIRMED_MATCH', 'POSSIBILITY', 'PARTIAL_MATCH', 'NO_MATCH']
                match_type = min([match_type_header, match_type_content], key=lambda t: hierarchy.index(t))
                
                # 4) Parse attachments for ALL emails (whether they match or not)
                print(f"📎 Checking attachments for email {mid}...")
                attachment_results = parse_email_attachments(service, mid, profile)
                
                # 5) Determine overall match considering both email content and attachments
                overall_match_type = match_type
                if attachment_results['overall_match_type'] != 'NO_MATCH':
                    # If attachments have a stronger match, use that
                    match_hierarchy = ['CONFIRMED_MATCH', 'POSSIBILITY', 'PARTIAL_MATCH', 'NO_MATCH']
                    if (match_hierarchy.index(attachment_results['overall_match_type']) < 
                        match_hierarchy.index(overall_match_type)):
                        overall_match_type = attachment_results['overall_match_type']
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
                        log_match_to_data(profile, email_data)
                        update_state_with_match(state, email_data, overall_match_type)
                        
                        match_icons = {
                            "CONFIRMED_MATCH": "🎯",
                            "POSSIBILITY": "🤔", 
                            "PARTIAL_MATCH": "📧"
                        }
                        print(f"{match_icons.get(overall_match_type, '❓')} {overall_match_type} FOUND!")
                        
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
                            result_match = parsing_result.get('match_type', 'NO_MATCH')
                            
                            if parser_used != 'none':
                                status_icon = "✅" if result_match != 'NO_MATCH' else "📄"
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
                    save_profile(profile)
                    print("Profile updated:", {
                        "name": profile.get("name"),
                        "registration_number": profile.get("registration_number"),
                        "gmail_display_name": profile.get("gmail_display_name"),
                    })

                # 8) Print summary
                body = extract_text(payload)
                print(f"\nNew email {mid}\nFrom: {display_name} <{addr}>\nSubject: {subject}")
                if parsed_name or reg:
                    print(f"Parsed: Name='{parsed_name}', Reg='{reg}'")
                print(f"—\n{body[:400]}...\n")

                # 9) Persist last processed message id
                state["last_message_id"] = mid
                save_state(state)
                
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
