import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Minimal scope for read access; change to gmail.modify if you plan to move/label messages.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            # Starts a temporary localhost server and opens the user’s browser to complete login.
            creds = flow.run_local_server(port=0)  # 0 picks a free port
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds

def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    print("Signed in. Labels:", [l["name"] for l in labels])

if __name__ == "__main__":
    main()
