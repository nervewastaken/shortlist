"""
WhatsApp notification system using chussa.py automation.
Creates and sends shortlisting notifications automatically.
"""

import urllib.parse
import webbrowser
import re
import subprocess
import os
import sys
import time
from typing import Dict, Any, Optional

# Import pyautogui and Quartz for direct WhatsApp interaction
try:
    import pyautogui
    from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    AUTOMATION_AVAILABLE = True
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except ImportError:
    AUTOMATION_AVAILABLE = False
    print("⚠️ pyautogui or Quartz not available - install with: pip install pyautogui pyobjc-framework-Quartz")

# Global variable to track if chussa automation is running
_chussa_process = None

def get_phone_number_from_profile(profile: Dict[str, Any]) -> Optional[str]:
    """
    Extract phone number from profile.
    """
    phone_number = profile.get("phone_number", "")
    if phone_number and phone_number.strip():
        return phone_number.strip()
    return None

def create_shortlist_message(name: str, reg_number: str, subject: str, gmail_link: str) -> str:
    """
    Create a simple shortlisting notification message.
    """
    message_parts = [
        f"Hi {name} ({reg_number})",
        f"",
        f"🎉 You're SHORTLISTED! 🎉",
        f"",
        f"📧 Subject: {subject}",
        f"",
        f"🔗 Mail Link: {gmail_link}",
        f"",
        f"Check your email for details!",
        f"",
        f"Best of luck! 🚀"
    ]
    
    return "\n".join(message_parts)

def find_whatsapp_window():
    """Find WhatsApp window (Desktop/Web) for coordinate calculation"""
    if not AUTOMATION_AVAILABLE:
        return None
        
    try:
        windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        for window in windows:
            owner = window.get("kCGWindowOwnerName", "")
            window_name = window.get("kCGWindowName", "")
            bounds = window.get("kCGWindowBounds", {})
            width = bounds.get("Width", 0)
            height = bounds.get("Height", 0)
            if width < 400 or height < 300:
                continue
            if (
                "WhatsApp" in owner
                or ("Chrome" in owner and "WhatsApp" in window_name)
                or ("Safari" in owner and "WhatsApp" in window_name)
                or ("Firefox" in owner and "WhatsApp" in window_name)
                or ("Microsoft Edge" in owner and "WhatsApp" in window_name)
            ):
                return {
                    "x": int(bounds.get("X", 0)),
                    "y": int(bounds.get("Y", 0)),
                    "width": int(width),
                    "height": int(height),
                }
        return None
    except Exception as e:
        print(f"❌ Window detection error: {e}")
        return None

def unminimize_whatsapp():
    """Unminimize and focus WhatsApp (Desktop or Web in browser)"""
    script = '''
    tell application "System Events"
        set appList to (name of every process)
    end tell

    if appList contains "WhatsApp" then
        tell application "WhatsApp" to activate
        tell application "System Events"
            tell process "WhatsApp"
                set frontmost to true
                repeat with win in windows
                    if value of attribute "AXMinimized" of win is true then
                        set value of attribute "AXMinimized" of win to false
                    end if
                end repeat
            end tell
        end tell
    else
        set browsers to {"Google Chrome", "Safari", "Microsoft Edge", "Firefox"}
        repeat with b in browsers
            if appList contains b then
                tell application b to activate
                tell application "System Events"
                    tell process b
                        set frontmost to true
                        repeat with win in windows
                            if value of attribute "AXMinimized" of win is true then
                                set value of attribute "AXMinimized" of win to false
                            end if
                        end repeat
                    end tell
                end tell
                exit repeat
            end if
        end repeat
    end if
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True)

def type_message_in_whatsapp(message: str) -> bool:
    """Type a message directly into WhatsApp textbox"""
    if not AUTOMATION_AVAILABLE:
        print("❌ Automation not available - cannot type message")
        return False
    
    try:
        # Unminimize and focus WhatsApp
        print("🔍 Finding and focusing WhatsApp...")
        unminimize_whatsapp()
        time.sleep(1)
        
        # Find WhatsApp window
        window = find_whatsapp_window()
        if not window:
            print("❌ WhatsApp window not found")
            return False
        
        print(f"✅ Found WhatsApp window: {window['width']}x{window['height']}")
        
        # Click in textbox area (bottom center of window)
        textbox_x = window["x"] + int(window["width"] * 0.5)
        textbox_y = window["y"] + int(window["height"] * 0.9)
        
        print(f"🖱️ Clicking textbox at ({textbox_x}, {textbox_y})")
        pyautogui.click(textbox_x, textbox_y)
        time.sleep(0.5)
        
        # Clear any existing text
        pyautogui.hotkey('cmd', 'a')
        time.sleep(0.1)
        
        # Type the message
        print("⌨️ Typing message...")
        pyautogui.write(message)
        time.sleep(0.5)
        
        print("✅ Message typed successfully!")
        print("🤖 Chussa will automatically send it in ~3 seconds")
        
        return True
        
    except Exception as e:
        print(f"❌ Error typing message: {e}")
        return False

def create_whatsapp_url(phone_number: str, message: str) -> str:
    """
    Create WhatsApp URL with encoded message.
    """
    # Clean phone number (remove spaces, hyphens, etc.)
    clean_phone = re.sub(r'[^\d+]', '', phone_number)
    
    # Ensure phone number starts with country code
    if not clean_phone.startswith('+'):
        if clean_phone.startswith('91'):  # Indian number
            clean_phone = '+' + clean_phone
        elif clean_phone.startswith('0'):  # Remove leading 0
            clean_phone = '+91' + clean_phone[1:]
        else:
            clean_phone = '+91' + clean_phone
    
    # URL encode the message
    encoded_message = urllib.parse.quote(message)
    
    # Create WhatsApp URL
    whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_message}"
    
    return whatsapp_url

def start_chussa_automation():
    """
    Start the chussa.py WhatsApp automation in the background.
    """
    global _chussa_process
    
    # Check if already running
    if _chussa_process and _chussa_process.poll() is None:
        print("🤖 Chussa automation already running")
        return True
    
    try:
        # Get the path to chussa.py
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        chussa_path = os.path.join(current_dir, "chussa.py")
        
        if not os.path.exists(chussa_path):
            print(f"❌ chussa.py not found at {chussa_path}")
            return False
        
        # Start chussa.py as a background process
        _chussa_process = subprocess.Popen([
            sys.executable, chussa_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"🚀 Started chussa automation (PID: {_chussa_process.pid})")
        print("💡 Make sure WhatsApp is open for automation to work")
        return True
        
    except Exception as e:
        print(f"❌ Failed to start chussa automation: {e}")
        return False

def stop_chussa_automation():
    """
    Stop the chussa automation if running.
    """
    global _chussa_process
    
    if _chussa_process and _chussa_process.poll() is None:
        try:
            _chussa_process.terminate()
            _chussa_process.wait(timeout=5)
            print("🛑 Stopped chussa automation")
        except subprocess.TimeoutExpired:
            _chussa_process.kill()
            print("🛑 Force-killed chussa automation")
        except Exception as e:
            print(f"⚠️ Error stopping chussa automation: {e}")
    
    _chussa_process = None

def is_chussa_running():
    """
    Check if chussa automation is currently running.
    """
    global _chussa_process
    return _chussa_process and _chussa_process.poll() is None

def send_whatsapp_notification(profile: Dict[str, Any], name: str, reg_number: str, subject: str, message_id: str) -> bool:
    """
    Send WhatsApp notification for a shortlisted candidate using chussa automation.
    """
    try:
        # Get phone number from profile
        phone_number = get_phone_number_from_profile(profile)
        if not phone_number:
            print("❌ No phone number available for WhatsApp notification")
            print("💡 Tip: Run 'python -m app.login' again to add your phone number")
            return False
        
        # Create Gmail link
        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{message_id}" if message_id else "Check your Gmail inbox"
        
        # Create the message
        message = create_shortlist_message(name, reg_number, subject, gmail_link)
        
        # Create WhatsApp URL
        whatsapp_url = create_whatsapp_url(phone_number, message)
        
        print(f"📱 WhatsApp notification created!")
        print(f"📞 To: {phone_number}")
        print(f"💬 Message preview: {message[:100]}...")
        
        # Start chussa automation if not running
        if not is_chussa_running():
            print("🚀 Starting chussa automation...")
            start_chussa_automation()
            time.sleep(2)
        
        # First open WhatsApp to the correct chat
        print("🌐 Opening WhatsApp chat...")
        whatsapp_url = create_whatsapp_url(phone_number, "")  # Empty message, we'll type it directly
        webbrowser.open(whatsapp_url)
        time.sleep(3)  # Give time for WhatsApp to load
        
        # Now type the message directly into WhatsApp
        print("⌨️ Typing message directly into WhatsApp...")
        success = type_message_in_whatsapp(message)
        
        if success:
            print("✅ Message typed successfully!")
            print("🤖 Chussa will automatically send it!")
            print("💡 Keep WhatsApp window visible")
        else:
            print("❌ Failed to type message")
            print("📝 Please manually copy and paste this message:")
            print(f"---\n{message}\n---")
        
        return success
        
    except Exception as e:
        print(f"❌ Error creating WhatsApp notification: {e}")
        return False

def should_send_whatsapp_notification(email_data: Dict[str, Any]) -> bool:
    """
    Determine if a WhatsApp notification should be sent based on email data.
    """
    match_type = email_data.get('match_type', 'NO_MATCH')
    
    # Only send for confirmed matches
    if match_type != 'CONFIRMED_MATCH':
        return False
    
    # Check if it looks like a shortlisting email
    subject = email_data.get('subject', '').lower()
    body_preview = email_data.get('body_preview', '').lower()
    
    # Keywords that suggest shortlisting/selection
    shortlist_keywords = [
        'shortlist', 'selected', 'qualified', 'interview', 'next round',
        'congratulations', 'proceed', 'further process', 'round 2',
        'technical interview', 'hr interview', 'final round'
    ]
    
    # Check if any shortlisting keywords are present
    combined_text = f"{subject} {body_preview}"
    for keyword in shortlist_keywords:
        if keyword in combined_text:
            return True
    
    return False

# Example usage and testing
if __name__ == "__main__":
    # Test data
    test_profile = {
        "name": "Krish Verma",
        "registration_number": "22BCE2382",
        "phone_number": "+919876543210"
    }
    
    print("🧪 Testing WhatsApp notification system...")
    
    # Test message creation
    test_message = create_shortlist_message(
        "Krish Verma", 
        "22BCE2382", 
        "Congratulations! You've been shortlisted for Software Engineer position",
        "https://mail.google.com/mail/u/0/#inbox/test123"
    )
    print(f"💬 Message created:")
    print(test_message)
    print()
    print(f"✅ Notification system ready")
    print("🤖 Chussa automation available")
