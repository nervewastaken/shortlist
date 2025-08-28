# app/login.py
import os
import json
import re
import base64
from pathlib import Path
from typing import Dict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Minimal scope for read; upgrade to gmail.modify/gmail.send later as needed
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = ROOT / "token.json"
PROFILE_FILE = ROOT / "profile.json"
CREDENTIALS_FILE = ROOT / "credentials.json"

# VIT reg-no pattern, e.g., 22BCE2382
REG_RE = re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE)

def parse_display_name_for_profile(display_name: str):
    """
    Extract name and registration number from Google account display name.
    Expected format: "First Last RegNumber" (e.g., "Krish Verma 22BCE2382")
    """
    if not display_name:
        return "", ""
    
    # Look for registration number
    reg_match = REG_RE.search(display_name)
    reg = reg_match.group(0).upper() if reg_match else ""
    
    # Extract name by removing registration number
    name = display_name
    if reg:
        name = re.sub(re.escape(reg), "", name, flags=re.IGNORECASE).strip()
    
    # Clean up the name
    name = re.sub(r"[,\-–]+$", "", name).strip()
    name = re.sub(r"\s{2,}", " ", name)
    
    return name, reg

def _load_json(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default

def _save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)

def ensure_credentials() -> Credentials:
    """
    Create/refresh OAuth credentials and persist token.json.
    Uses a fixed localhost port and forces browser open for reliability.
    """
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            # Launch a local server and open the default browser; if that fails, it prints the URL.
            creds = flow.run_local_server(
                host="localhost",
                port=8088,  # change if occupied
                authorization_prompt_message="Please authorize this app by visiting: {url}",
                success_message="Authentication complete. You may close this tab.",
                open_browser=True,
            )
        TOKEN_FILE.write_text(creds.to_json())
    return creds

def ensure_profile(service) -> Dict:
    """
    Create/augment a simple profile.json with Gmail and personal info.
    Parse name and registration number from Google account display name.
    """
    prof = _load_json(PROFILE_FILE, {})
    me = service.users().getProfile(userId="me").execute()
    prof.setdefault("gmail_address", me.get("emailAddress", ""))

    # Try to get display name from various Gmail API sources
    google_display_name = ""
    
    # Method 1: Check if we can get it from sending a test draft (this often contains the display name)
    try:
        # Get a recent sent message to see how the user's name appears
        sent_messages = service.users().messages().list(userId="me", q="in:sent", maxResults=1).execute()
        if sent_messages.get("messages"):
            sent_msg_id = sent_messages["messages"][0]["id"]
            sent_msg = service.users().messages().get(userId="me", id=sent_msg_id, format="full").execute()
            headers = sent_msg.get("payload", {}).get("headers", [])
            for header in headers:
                if header.get("name", "").lower() == "from":
                    from_value = header.get("value", "")
                    # Parse the From header to get display name
                    from email.utils import parseaddr
                    name, addr = parseaddr(from_value)
                    if name and name.strip():
                        google_display_name = name.strip()
                        print(f"Found display name from sent emails: {google_display_name}")
                        break
    except Exception as e:
        print(f"Could not get display name from sent emails: {e}")

    # Method 2: If we still don't have it, try to create a draft and see the From field
    if not google_display_name:
        try:
            # Create a test draft to see how the From field appears
            draft_body = {
                'message': {
                    'raw': base64.urlsafe_b64encode(
                        f"To: {prof.get('gmail_address', '')}\r\n"
                        f"Subject: Test\r\n\r\n"
                        f"Test message".encode()
                    ).decode()
                }
            }
            draft = service.users().drafts().create(userId="me", body=draft_body).execute()
            draft_id = draft.get("id")
            
            # Get the draft details
            draft_details = service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
            headers = draft_details.get("message", {}).get("payload", {}).get("headers", [])
            
            for header in headers:
                if header.get("name", "").lower() == "from":
                    from_value = header.get("value", "")
                    from email.utils import parseaddr
                    name, addr = parseaddr(from_value)
                    if name and name.strip():
                        google_display_name = name.strip()
                        print(f"Found display name from draft: {google_display_name}")
                        break
            
            # Clean up the test draft
            service.users().drafts().delete(userId="me", id=draft_id).execute()
            
        except Exception as e:
            print(f"Could not get display name from draft method: {e}")

    # Method 3: If still no luck, extract from email address prefix as fallback
    if not google_display_name:
        gmail_address = prof.get("gmail_address", "")
        if gmail_address:
            # Extract the part before @ and try to make it readable
            prefix = gmail_address.split("@")[0]
            # Convert something like "krish.verma2022" to "Krish Verma"
            # This is a fallback and might not always work perfectly
            google_display_name = prefix.replace(".", " ").replace("_", " ").title()
            print(f"Using fallback display name from email: {google_display_name}")

    # Store and parse the display name
    if google_display_name:
        prof["google_account_display_name"] = google_display_name
        parsed_name, parsed_reg = parse_display_name_for_profile(google_display_name)
        if parsed_name:
            prof["name"] = parsed_name
        if parsed_reg:
            prof["registration_number"] = parsed_reg
        print(f"Parsed from display name - Name: '{parsed_name}', Reg: '{parsed_reg}'")

    # One-time prompt for personal email and phone number
    if not prof.get("personal_email"):
        try:
            personal = input("Enter personal email to associate with this account: ").strip()
        except EOFError:
            personal = ""
        prof["personal_email"] = personal
    
    if not prof.get("phone_number"):
        try:
            phone = input("Enter your phone number (Indian format, e.g., 9876543210): ").strip()
            # Clean and format the phone number
            phone = re.sub(r'[^\d]', '', phone)  # Remove non-digits
            if phone.startswith('91'):
                phone = phone[2:]  # Remove country code if already present
            if phone.startswith('0'):
                phone = phone[1:]  # Remove leading 0
            if len(phone) == 10 and phone.isdigit():
                prof["phone_number"] = f"+91{phone}"
                print(f"Phone number saved as: {prof['phone_number']}")
            else:
                print("Invalid phone number format. Skipping...")
                prof["phone_number"] = ""
        except EOFError:
            prof["phone_number"] = ""

    prof.setdefault("gmail_display_name", "")
    prof.setdefault("name", "")
    prof.setdefault("registration_number", "")
    prof.setdefault("phone_number", "")
    _save_json(PROFILE_FILE, prof)
    return prof

def get_gmail_client_and_profile():
    """
    Public entry: returns (gmail_service, profile_dict).
    """
    creds = ensure_credentials()
    service = build("gmail", "v1", credentials=creds)
    profile = ensure_profile(service)
    return service, profile

if __name__ == "__main__":
    # Allow running this module directly to perform sign-in only
    service, profile = get_gmail_client_and_profile()
    print("Signed in as:", profile.get("gmail_address"))
