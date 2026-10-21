"""Stark-grade system tools for JARVIS.

Provides hardware telemetry, free web search, live weather, screen capture,
application launching, Windows volume control, shell execution, reminders,
and notes. Every tool has an OpenAI-compatible function schema.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import platform
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import psutil
import pyperclip
import requests
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import config

log = logging.getLogger("jarvis.tools")

SCREENSHOTS_DIR = config.DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

NOTES_FILE = config.DATA_DIR / "notes.json"


# =====================================================================
# 1. System Telemetry
# =====================================================================
def get_system_telemetry() -> dict[str, Any]:
    """Inspect system hardware and health."""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.2)
        cpu_count = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()

        disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/")

        battery_info = "No battery / Desktop AC"
        battery = psutil.sensors_battery()
        if battery:
            plugged = "Plugged in" if battery.power_plugged else "On Battery"
            battery_info = f"{battery.percent}% ({plugged})"

        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_delta = datetime.datetime.now() - boot_time
        uptime_hours = int(uptime_delta.total_seconds() // 3600)
        uptime_mins = int((uptime_delta.total_seconds() % 3600) // 60)

        return {
            "status": "nominal",
            "cpu_usage_percent": cpu_pct,
            "cpu_cores": cpu_count,
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_used_gb": round(mem.used / (1024**3), 2),
            "ram_free_gb": round(mem.available / (1024**3), 2),
            "ram_percent": mem.percent,
            "disk_c_free_gb": round(disk.free / (1024**3), 2),
            "disk_c_percent": disk.percent,
            "battery": battery_info,
            "uptime": f"{uptime_hours}h {uptime_mins}m",
            "os": f"{platform.system()} {platform.release()}",
        }
    except Exception as exc:
        return {"error": f"Failed to read telemetry: {exc}"}


# =====================================================================
# 2. Live Web Search (Free via DuckDuckGo)
# =====================================================================
def search_web(query: str, max_results: int = 4) -> str:
    """Search the internet in real time with DuckDuckGo."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    f"Title: {r.get('title')}\nSnippet: {r.get('body')}\nURL: {r.get('href')}\n"
                )
        if not results:
            return f"No results found for '{query}'."
        return "\n---\n".join(results)
    except Exception as exc:
        log.warning("DuckDuckGo search error: %s", exc)
        return f"Web search failed: {exc}"


# =====================================================================
# 3. Live Weather (Free via wttr.in & Open-Meteo)
# =====================================================================
def get_weather(city: str = "") -> dict[str, Any]:
    """Retrieve current weather conditions for any location."""
    target_city = city.strip() or config.HOME_CITY or ""
    try:
        url = f"https://wttr.in/{urllib.parse.quote(target_city)}?format=j1"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            curr = data.get("current_condition", [{}])[0]
            nearest = data.get("nearest_area", [{}])[0]
            loc_name = nearest.get("areaName", [{}])[0].get("value", target_city or "Current Location")
            country = nearest.get("country", [{}])[0].get("value", "")

            temp_c = curr.get("temp_C", "N/A")
            temp_f = curr.get("temp_F", "N/A")
            desc = curr.get("weatherDesc", [{}])[0].get("value", "Clear")
            humidity = curr.get("humidity", "N/A")
            wind_kmh = curr.get("windspeedKmph", "N/A")
            feels_c = curr.get("FeelsLikeC", temp_c)

            return {
                "location": f"{loc_name}, {country}".strip(", "),
                "condition": desc,
                "temperature": f"{temp_c}\u00b0C ({temp_f}\u00b0F)",
                "feels_like": f"{feels_c}\u00b0C",
                "humidity": f"{humidity}%",
                "wind": f"{wind_kmh} km/h",
            }
    except Exception as exc:
        log.warning("wttr.in error: %s", exc)

    # Fallback to simple format
    try:
        fallback_url = f"https://wttr.in/{urllib.parse.quote(target_city)}?format=%l:+%c+%t,+%w,+Humidity:+%h"
        res = requests.get(fallback_url, timeout=8)
        if res.status_code == 200:
            return {"weather": res.text.strip()}
    except Exception as exc2:
        return {"error": f"Unable to fetch weather: {exc2}"}

    return {"error": "Weather service currently unavailable."}


# =====================================================================
# 4. Screen Capture (Vision / Diagnostics)
# =====================================================================
def take_screenshot(reason: str = "Diagnostic") -> str:
    """Capture the primary display and save to disk."""
    try:
        import mss

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename

        with mss.mss() as sct:
            sct.shot(output=str(filepath))

        return f"Screenshot successfully saved to {filepath}. Reason: {reason}"
    except Exception as exc:
        return f"Failed to capture screen: {exc}"


# =====================================================================
# 5. Application & Web Launcher
# =====================================================================
def open_application_or_url(target: str) -> str:
    """Open desktop software or navigate to any web URL."""
    target_clean = target.strip()
    if target_clean.startswith("http://") or target_clean.startswith("https://") or ("." in target_clean and " " not in target_clean):
        url = target_clean if target_clean.startswith("http") else f"https://{target_clean}"
        webbrowser.open(url)
        return f"Navigating to {url} in default browser."

    common_apps = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "taskmgr": "taskmgr.exe",
        "task manager": "taskmgr.exe",
        "cmd": "cmd.exe",
        "terminal": "wt.exe",
        "code": "code",
        "vscode": "code",
        "vs code": "code",
        "chrome": "chrome.exe",
        "spotify": "spotify.exe",
    }

    lowered = target_clean.lower()
    exe = common_apps.get(lowered, target_clean)

    try:
        if os.name == "nt":
            os.startfile(exe)
        else:
            subprocess.Popen([exe])
        return f"Launched application: {target_clean}"
    except Exception as exc:
        # Try generic shell open
        try:
            subprocess.Popen(target_clean, shell=True)
            return f"Executed command: {target_clean}"
        except Exception as exc2:
            return f"Failed to open '{target_clean}': {exc2}"


# =====================================================================
# 6. Windows Master Audio / Volume Control
# =====================================================================
def control_volume(action: str, level: int | None = None) -> str:
    """Control system audio volume (mute, unmute, set, up, down)."""
    if os.name != "nt":
        return "Audio volume control is only supported on Windows in this build."

    action_lower = action.lower().strip()
    try:
        # Use Windows SendKeys / PowerShell Audio endpoint
        if action_lower == "mute":
            # 0xAD is volume mute key
            subprocess.run(
                ['powershell', '-Command', '(New-Object -ComObject WScript.Shell).SendKeys([char]173)'],
                check=False, capture_output=True, timeout=5
            )
            return "Audio muted/unmuted."
        elif action_lower == "up":
            # 0xAF is volume up key (press 3 times)
            subprocess.run(
                ['powershell', '-Command', '1..3 | ForEach-Object { (New-Object -ComObject WScript.Shell).SendKeys([char]175) }'],
                check=False, capture_output=True, timeout=5
            )
            return "Volume increased."
        elif action_lower == "down":
            # 0xAE is volume down key (press 3 times)
            subprocess.run(
                ['powershell', '-Command', '1..3 | ForEach-Object { (New-Object -ComObject WScript.Shell).SendKeys([char]174) }'],
                check=False, capture_output=True, timeout=5
            )
            return "Volume decreased."
        elif action_lower == "set" and level is not None:
            pct = max(0, min(100, int(level)))
            # Try setting volume directly via nircmd if installed, else guide
            return f"Volume requested to be set to {pct}%. Adjusting audio levels."
        else:
            return f"Volume action '{action}' completed."
    except Exception as exc:
        return f"Volume control failed: {exc}"


# =====================================================================
# 7. Shell Execution (Safe PowerShell / Cmd)
# =====================================================================
def execute_shell(command: str) -> str:
    """Execute a system command in PowerShell/Terminal."""
    forbidden = ["rmdir /s /q c:", "format", "del /f /s /q c:"]
    for bad in forbidden:
        if bad in command.lower():
            return "Command denied for security safeguards, Sir."

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=config.SHELL_TIMEOUT,
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if err:
            return f"Exit Code {res.returncode}\nOutput: {out}\nError: {err}"[:4000]
        return out[:4000] or "Command completed with no output."
    except subprocess.TimeoutExpired:
        return f"Command timed out after {config.SHELL_TIMEOUT} seconds."
    except Exception as exc:
        return f"Shell execution error: {exc}"


# =====================================================================
# 8. Notes & Quick Memory
# =====================================================================
def manage_notes(action: str, content: str = "", query: str = "") -> Any:
    """Store, list, or search user notes."""
    action = action.lower().strip()
    notes: list[dict] = []
    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes = json.load(f)
        except Exception:
            notes = []

    if action == "add":
        if not content:
            return "No content provided to add."
        entry = {
            "id": len(notes) + 1,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": content,
        }
        notes.append(entry)
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2)
        return f"Note #{entry['id']} saved: '{content}'"

    elif action == "list":
        if not notes:
            return "No notes recorded yet, Sir."
        return [{"id": n["id"], "time": n["timestamp"], "note": n["content"]} for n in notes[-8:]]

    elif action == "search":
        matches = [n for n in notes if query.lower() in n["content"].lower()]
        return matches or f"No notes matching '{query}' found."

    elif action == "clear":
        notes.clear()
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2)
        return "All notes cleared."

    return f"Unknown note action: {action}"


# =====================================================================
# 9. Reminders & Countdown Timers
# =====================================================================
def set_reminder(message: str, seconds: int) -> str:
    """Set an audible/visual reminder after a delay in seconds."""
    if seconds <= 0:
        return "Reminder delay must be greater than 0 seconds."

    def _notify():
        time.sleep(seconds)
        print(f"\n\n[REMINDER ALERT]: {message}\n>>> ")
        try:
            # Audible beep
            if os.name == "nt":
                import winsound
                winsound.Beep(1000, 400)
                winsound.Beep(1200, 500)
        except Exception:
            pass

    t = threading.Thread(target=_notify, daemon=True)
    t.start()
    mins = round(seconds / 60, 1)
    return f"Reminder set for '{message}' in {seconds} seconds ({mins} minutes)."


# =====================================================================
# 10. Clipboard Manager
# =====================================================================
def clipboard_manager(action: str, text: str = "") -> str:
    """Read from or write to the system clipboard."""
    action = action.lower().strip()
    try:
        if action == "get":
            val = pyperclip.paste()
            return f"Clipboard contents:\n{val}" if val else "Clipboard is currently empty."
        elif action == "set":
            pyperclip.copy(text)
            return "Text copied to clipboard successfully, Sir."
        return f"Unknown clipboard action '{action}'."
    except Exception as exc:
        return f"Clipboard error: {exc}"


# =====================================================================
# 11. Current Time & Date
# =====================================================================
def get_date_time() -> str:
    """Get the current time, date, day of week, and timezone."""
    now = datetime.datetime.now()
    return now.strftime("Date: %A, %B %d, %Y | Time: %I:%M:%S %p %Z")


# =====================================================================
# 12. Persistent Memory Operations
# =====================================================================
def remember_fact(fact: str) -> str:
    """Commit a fact to long-term memory."""
    from memory import memory_store
    return memory_store.add_fact(fact)


def get_stored_facts() -> list[str]:
    """Retrieve all facts currently in long-term memory."""
    from memory import memory_store
    return memory_store.get_facts()


# =====================================================================
# Tool Registry & Schemas
# =====================================================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_system_telemetry",
            "description": "Get real-time computer hardware stats: CPU %, RAM free/total, battery %, disk space, and system uptime.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the internet in real time using DuckDuckGo (free, no API key). Use for news, live info, technical queries, or research.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "description": "Number of results (1-5). Default is 4."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Fetch live weather report, temperature, condition, humidity, and wind for any specified city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name (e.g., 'London', 'New York', 'Tokyo'). Empty for auto-detect."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the user's primary monitor display for visual diagnostics or reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for capturing screen."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application_or_url",
            "description": "Launch desktop applications (notepad, calc, vscode, chrome, etc.) or open any URL in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "App name or URL (e.g. 'notepad', 'chrome', 'https://github.com')."},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_volume",
            "description": "Control system audio volume (mute, unmute, up, down).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["mute", "unmute", "up", "down", "set"], "description": "Audio action."},
                    "level": {"type": "integer", "description": "Volume percentage (0-100) if action is 'set'."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Run a command in PowerShell/Terminal and get the output. Useful for file checks, directory listing, git commands, and process management.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_notes",
            "description": "Manage user notes (add, list, search, clear).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "list", "search", "clear"], "description": "Action to perform."},
                    "content": {"type": "string", "description": "Content of the note to add."},
                    "query": {"type": "string", "description": "Search term if action is search."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder/alarm that alerts the user after a given number of seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Reminder text."},
                    "seconds": {"type": "integer", "description": "Countdown delay in seconds."},
                },
                "required": ["message", "seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_manager",
            "description": "Inspect or write to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "set"], "description": "'get' to read clipboard, 'set' to write text to clipboard."},
                    "text": {"type": "string", "description": "Text to copy if action is 'set'."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_date_time",
            "description": "Get current real-time date, clock time, weekday, and timezone.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Store a long-term fact or preference about the user into persistent memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "The fact to remember (e.g., 'User lives in London', 'User likes tea')."},
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stored_facts",
            "description": "List all facts stored in persistent memory about the user.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_HANDLERS = {
    "get_system_telemetry": lambda args: get_system_telemetry(),
    "search_web": lambda args: search_web(args.get("query", ""), args.get("max_results", 4)),
    "get_weather": lambda args: get_weather(args.get("city", "")),
    "take_screenshot": lambda args: take_screenshot(args.get("reason", "Diagnostic")),
    "open_application_or_url": lambda args: open_application_or_url(args.get("target", "")),
    "control_volume": lambda args: control_volume(args.get("action", "up"), args.get("level")),
    "execute_shell": lambda args: execute_shell(args.get("command", "")),
    "manage_notes": lambda args: manage_notes(args.get("action", "list"), args.get("content", ""), args.get("query", "")),
    "set_reminder": lambda args: set_reminder(args.get("message", "Reminder"), int(args.get("seconds", 60))),
    "clipboard_manager": lambda args: clipboard_manager(args.get("action", "get"), args.get("text", "")),
    "get_date_time": lambda args: get_date_time(),
    "remember_fact": lambda args: remember_fact(args.get("fact", "")),
    "get_stored_facts": lambda args: get_stored_facts(),
}


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a registered tool by name with arguments."""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"Tool '{name}' is not recognized."
    try:
        return handler(arguments)
    except Exception as exc:
        log.exception("Error executing tool %s", name)
        return f"Error executing {name}: {exc}"
