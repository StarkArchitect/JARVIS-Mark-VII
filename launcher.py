"""J.A.R.V.I.S. Mark VII - Interactive Stark Launcher.

Provides a zero-friction menu with countdown auto-launch to the Holographic HUD.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

try:
    import msvcrt
except ImportError:
    msvcrt = None


BANNER = r"""
       __ ___       ______   ____    ____  __     _______.
      |  |   \     |   _  \  \   \  /   / |  |   /       |
      |  |/   \    |  |_)  |  \   \/   /  |  |  |   (----`
  .--.|  /  ^  \   |      /    \_    _/   |  |   \   \    
  |  `--/  /_\  \  |  |\  \-.    |  |     |  |----)   |   
   \___/__/   \__\ |__| `.__|    |__|     |__|_______/    
  =========================================================
  [ STARK INDUSTRIES PROTOCOL MARK VII | COMMAND CENTER ]
"""


def _countdown_prompt(seconds: int = 5) -> str | None:
    """Wait for user keypress with visual countdown; defaults to None (Option 1) on timeout."""
    # If input is piped or redirected, read directly from stdin without blocking countdown
    if not sys.stdin.isatty():
        try:
            line = sys.stdin.readline().strip()
            if line:
                return line
        except Exception:
            pass
        return "1"

    if not msvcrt:
        return input("Select an option [1-8, 0] (default=1): ").strip()

    print(f"\n[AUTO] Launching Stark Holographic HUD GUI in {seconds}s... (Press 1-8 or 0 to override)")
    for remaining in range(seconds, 0, -1):
        print(f"\r  >> Auto-launching in {remaining}s [Press a number to select]... ", end="", flush=True)
        t_end = time.time() + 1.0
        while time.time() < t_end:
            if msvcrt.kbhit():
                char = msvcrt.getch().decode("utf-8", errors="ignore").strip()
                print(f"\nSelected: {char}")
                return char
            time.sleep(0.05)

    print("\n[AUTO] Countdown elapsed. Initializing Holographic HUD GUI...")
    return "1"


def print_menu() -> None:
    print(BANNER)
    print("  [ SELECT OPERATION PROTOCOL ]\n")
    print("  [1] 🦾 Stark Holographic HUD GUI       (Default - Arc Reactor 60FPS UI)")
    print("  [2] 🎙️ Hands-Free Voice Assistant      (Edge-TTS + Groq Whisper + Barge-In)")
    print("  [3] 🔘 Push-to-Talk Voice Mode        (Spacebar activation)")
    print("  [4] 💬 Interactive Terminal Chat       (Fast CLI conversational mode)")
    print("  [5] 🛠️ Hardware & API Diagnostics      (Telemetry, models, search, weather)")
    print("  [6] 🧪 Automated 10-Point Self-Test    (selftest.py verification suite)")
    print("  [7] 🖥️ Create Desktop 1-Click Shortcut (Puts JARVIS icon on your Desktop)")
    print("  [8] 📦 Check & Install Dependencies    (pip install -r requirements.txt)")
    print("  [0] ❌ Exit")


def create_desktop_shortcut() -> None:
    """Executes the PowerShell shortcut creation script."""
    script_path = os.path.join(os.path.dirname(__file__), "create_desktop_shortcut.ps1")
    if os.path.exists(script_path):
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path], check=False)
    else:
        print("[ERROR] create_desktop_shortcut.ps1 not found.")


def install_deps() -> None:
    """Installs required packages."""
    print("\n[SYS] Updating and verifying dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=False)


def main() -> int:
    # Ensure UTF-8 output
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print_menu()
    choice = _countdown_prompt(seconds=5)

    if not choice:
        choice = "1"

    python_exe = sys.executable

    if choice == "1":
        print("\n[SYS] Initializing Stark Holographic HUD...")
        return subprocess.run([python_exe, "main.py", "--gui"]).returncode
    elif choice == "2":
        print("\n[SYS] Initializing Hands-Free Voice Mode...")
        return subprocess.run([python_exe, "main.py", "--voice"]).returncode
    elif choice == "3":
        print("\n[SYS] Initializing Push-to-Talk Voice Mode...")
        return subprocess.run([python_exe, "main.py", "--ptt"]).returncode
    elif choice == "4":
        print("\n[SYS] Initializing Terminal Text Chat...")
        return subprocess.run([python_exe, "main.py", "--text"]).returncode
    elif choice == "5":
        print("\n[SYS] Running System Diagnostics...")
        return subprocess.run([python_exe, "main.py", "--diag"]).returncode
    elif choice == "6":
        print("\n[SYS] Executing Self-Test Suite...")
        return subprocess.run([python_exe, "selftest.py"]).returncode
    elif choice == "7":
        create_desktop_shortcut()
        print("\nPress Enter to continue...")
        input()
        return 0
    elif choice == "8":
        install_deps()
        print("\nPress Enter to continue...")
        input()
        return 0
    elif choice == "0":
        print("\nExiting. Systems standing down, Sir.")
        return 0
    else:
        print(f"\n[UNKNOWN OPTION: {choice}] Defaulting to Holographic HUD...")
        return subprocess.run([python_exe, "main.py", "--gui"]).returncode


if __name__ == "__main__":
    sys.exit(main())
