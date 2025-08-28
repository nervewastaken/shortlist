#!/usr/bin/env python3
"""
WhatsApp Auto Sender - Minimal version
- No reading/copying textbox
- Just clicks in the textbox and sends if not minimized
- Un-minimizes and focuses WhatsApp first
"""

import subprocess
import sys
import time

def install_package(package):
    try:
        __import__(package.split('==')[0] if '==' in package else package)
    except ImportError:
        print(f"📦 Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

for pkg in ["pyautogui", "pyobjc-framework-Quartz"]:
    install_package(pkg)

import pyautogui
from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID

class WhatsAppAutoSender:
    def __init__(self):
        self.check_interval = 3
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        print("✅ WhatsApp Auto Sender (no clipboard) initialized")

    def unminimize_whatsapp(self):
        """Always unminimize/focus WhatsApp (Desktop or Web in browser)"""
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

    def find_whatsapp_window(self):
        """Find WhatsApp window (Desktop/Web) for coordinate calculation"""
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

    def send_once(self, window):
        """Click in textbox area and press enter"""
        # Focus textbox
        textbox_x = window["x"] + int(window["width"] * 0.5)
        textbox_y = window["y"] + int(window["height"] * 0.9)
        print(f"🖱️ Clicking ({textbox_x},{textbox_y}) and pressing enter")
        pyautogui.click(textbox_x, textbox_y)
        time.sleep(0.15)
        pyautogui.press("return")
        time.sleep(0.6)
        # Blur
        blur_x = window["x"] + int(window["width"] * 0.5)
        blur_y = window["y"] + 40
        pyautogui.click(blur_x, blur_y)
        time.sleep(0.1)

    def check_and_send(self):
        """Only send if WhatsApp window is up (no repeat, no clipboard)"""
        print(f"\n⏰ {time.strftime('%H:%M:%S')} - Trying to send")
        self.unminimize_whatsapp()
        time.sleep(0.5)
        window = self.find_whatsapp_window()
        if not window:
            print("⚠️ WhatsApp window not found")
            return
        self.send_once(window)

    def run(self):
        print(
            "\n🚀 WhatsApp Auto Sender (sends whatever is currently in the textbox, no clipboard involved)"
        )
        try:
            while True:
                self.check_and_send()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\n🛑 Sender stopped by user")

def main():
    if sys.platform != "darwin":
        print("❌ This script is for macOS only")
        sys.exit(1)
    sender = WhatsAppAutoSender()
    sender.run()

if __name__ == "__main__":
    main()
