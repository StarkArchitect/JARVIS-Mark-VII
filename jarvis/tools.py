"""Tool schemas + registry for JARVIS.

dispatch() never raises; it returns a clean string result.
Includes system stats, free web search, live weather, screen capture,
volume control, application launching, shell commands, file management,
clipboard, safe calculations, reminders, and persistent memory.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .config import Config
from .memory import Memory
from .utils import get_logger, platform_open, safe_eval

log = get_logger()


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOL_SCHEMAS: list[dict] = [
    _fn("get_current_time", "Current local time (HH:MM:SS) and timezone.", {}, []),
    _fn("get_date", "Today's date and day of the week.", {}, []),
    _fn("open_application", "Open an app, file, folder, or URL with the OS default handler.",
        {"target": {"type": "string", "description": "App name (e.g. notepad, chrome), path, or URL"}}, ["target"]),
    _fn("run_shell_command", "Run a PowerShell/Shell command and return output.",
        {"command": {"type": "string", "description": "The command string to execute."}}, ["command"]),
    _fn("read_file", "Read text content from a file (up to ~8KB).",
        {"path": {"type": "string", "description": "Relative or absolute file path."}}, ["path"]),
    _fn("write_file", "Write text to a file (creates parent directories, overwrites existing).",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("list_directory", "List directory entries with types and sizes.",
        {"path": {"type": "string", "description": "Directory path."}}, ["path"]),
    _fn("web_search", "Search DuckDuckGo in real-time and return top results.",
        {"query": {"type": "string", "description": "Search query."}}, ["query"]),
    _fn("get_weather", "Fetch current weather, temperature, humidity, and wind for any city.",
        {"city": {"type": "string", "description": "City name (e.g. 'London', 'Tokyo'). Empty for local."}}, []),
    _fn("calculate", "Evaluate a math expression safely using AST walker (e.g. '2*(3+4)/7').",
        {"expression": {"type": "string"}}, ["expression"]),
    _fn("get_system_stats", "Real-time hardware status: CPU %, RAM free/used, Disk %, Battery %, Uptime.", {}, []),
    _fn("set_volume", "Control system output volume (0-100, mute, unmute).",
        {"action": {"type": "string", "enum": ["set", "mute", "unmute", "up", "down"]},
         "level": {"type": "number", "minimum": 0, "maximum": 100}}, ["action"]),
    _fn("take_screenshot", "Capture the screen display to a PNG file and return its path.", {}, []),
    _fn("clipboard_get", "Read current clipboard text.", {}, []),
    _fn("clipboard_set", "Copy text to clipboard.",
        {"text": {"type": "string"}}, ["text"]),
    _fn("remember", "Store a durable user fact or preference in persistent memory.",
        {"fact": {"type": "string", "description": "The fact to remember."},
         "tags": {"type": "string", "description": "Optional comma-separated tags."}}, ["fact"]),
    _fn("recall", "Search stored memory facts.",
        {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
    _fn("set_reminder", "Set an alert/reminder after a countdown in seconds.",
        {"message": {"type": "string"}, "seconds": {"type": "integer"}}, ["message", "seconds"]),
    _fn("manage_agenda", "Manage daily plans, tasks, and calendar events in persistent memory (list, add, complete, clear).",
        {"action": {"type": "string", "enum": ["list", "add", "complete", "clear"], "description": "Action to perform"},
         "title": {"type": "string", "description": "Plan or task title (required for add/complete)"},
         "due_time": {"type": "string", "description": "Optional due time or deadline (e.g. '14:00', 'today 5pm')"}}, ["action"]),
    _fn("clean_temp_files", "Scan and clean temporary files, cache, and crash dumps to free up disk space.",
        {"dry_run": {"type": "boolean", "description": "If true, only report space to be freed without deleting. Default is false."}}, []),
    _fn("get_top_processes", "List top resource-intensive running processes sorted by CPU or Memory.",
        {"sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Sort metric"},
         "limit": {"type": "integer", "description": "Number of processes to return (default 5)"}}, []),
    _fn("media_control", "Control multimedia playback (play/pause, next track, previous track, stop).",
        {"action": {"type": "string", "enum": ["play_pause", "next", "prev", "stop"], "description": "Media action to trigger"}}, ["action"]),
    _fn("search_files", "Fast search for files matching a pattern or name across common user folders or custom directory.",
        {"query": {"type": "string", "description": "Search keyword or pattern (e.g. 'report', '*.pdf')"},
         "location": {"type": "string", "description": "Folder to search ('desktop', 'downloads', 'documents', or a folder path). Default: desktop."},
         "max_results": {"type": "integer", "description": "Max files to return (default 10)"}}, ["query"]),
    _fn("get_network_status", "Check local network IP, gateway, internet connectivity, and ping latency.", {}, []),
    _fn("morning_briefing", "Generate a comprehensive Stark executive daily briefing: time, weather, system health, pending agenda tasks, and recommendations.", {}, []),
]


# --------------------------------------------------------------------------- helpers

def _run(cmd: list[str], timeout: int = 10) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )
    out = (result.stdout or "") + (result.stderr or "")
    return out.strip() or "(no output)"


def _allowed_roots(config: Config) -> list[Path]:
    return [Path(p).expanduser().resolve() for p in config.allow_paths]


def _check_path(raw: str, config: Config) -> Path:
    p = Path(raw).expanduser().resolve()
    for root in _allowed_roots(config):
        if p == root or p.is_relative_to(root):
            return p
    # Allow local project root as well
    project_root = Path(__file__).resolve().parent.parent
    if p == project_root or p.is_relative_to(project_root):
        return p
    raise PermissionError(f"path {raw!r} is outside allowed roots")


class _DDGParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.snippets: list[str] = []
        self._in_a = False
        self._a_href = ""
        self._a_text: list[str] = []
        self._in_snip = False
        self._snip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        adict = {k: (v or "") for k, v in attrs}
        if tag == "a":
            href = adict.get("href", "")
            classes = adict.get("class", "")
            if "result__a" in classes or "uddg=" in href:
                self._in_a = True
                self._a_href = href
                self._a_text = []
        elif tag == "td" and "result-snippet" in adict.get("class", ""):
            self._in_snip = True
            self._snip_text = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._a_text.append(data)
        elif self._in_snip:
            self._snip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a:
            title = html.unescape("".join(self._a_text)).strip()
            url = self._a_href
            if "uddg=" in url:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                url = parsed.get("uddg", [url])[0]
            if title and url.startswith("http"):
                self.links.append((title, url))
            self._in_a = False
        elif tag == "td" and self._in_snip:
            text = html.unescape("".join(self._snip_text)).strip()
            if text:
                self.snippets.append(text)
            self._in_snip = False


def _web_search(query: str) -> str:
    # First attempt: modern ddgs library
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=4):
                results.append(f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}\n")
            if results:
                return "\n---\n".join(results)
    except Exception:
        pass

    # Fallback to HTML parser
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        parser = _DDGParser()
        parser.feed(page)
        if parser.links:
            lines = []
            for i, (title, link) in enumerate(parser.links[:4]):
                snip = parser.snippets[i] if i < len(parser.snippets) else ""
                lines.append(f"{i + 1}. {title}\n   {link}\n   {snip[:200]}")
            return "\n".join(lines)
    except Exception as exc:
        log.warning("Web search error: %s", exc)

    return f"No results found for {query!r}."


def _get_weather(city: str = "") -> str:
    target = urllib.parse.quote(city.strip()) if city.strip() else ""
    try:
        url = f"https://wttr.in/{target}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        curr = data.get("current_condition", [{}])[0]
        nearest = data.get("nearest_area", [{}])[0]
        area = nearest.get("areaName", [{}])[0].get("value", city or "Current Location")
        country = nearest.get("country", [{}])[0].get("value", "")
        desc = curr.get("weatherDesc", [{}])[0].get("value", "Clear")
        temp_c = curr.get("temp_C", "N/A")
        temp_f = curr.get("temp_F", "N/A")
        humidity = curr.get("humidity", "N/A")
        wind = curr.get("windspeedKmph", "N/A")
        return f"Weather for {area}, {country}: {desc}, {temp_c}°C ({temp_f}°F), Humidity: {humidity}%, Wind: {wind} km/h"
    except Exception:
        try:
            url = f"https://wttr.in/{target}?format=%l:+%c+%t,+%w,+Humidity:+%h"
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception as exc:
            return f"Weather service unavailable ({exc})."


def _set_volume(action: str, level: float | None = None) -> str:
    action = action.lower().strip()
    system = platform.system()
    if system == "Windows":
        if action == "mute":
            subprocess.run(['powershell', '-Command', '(New-Object -ComObject WScript.Shell).SendKeys([char]173)'],
                           check=False, capture_output=True, timeout=5)
            return "Volume muted/unmuted."
        elif action == "up":
            subprocess.run(['powershell', '-Command', '1..4 | ForEach-Object { (New-Object -ComObject WScript.Shell).SendKeys([char]175) }'],
                           check=False, capture_output=True, timeout=5)
            return "Volume turned up."
        elif action == "down":
            subprocess.run(['powershell', '-Command', '1..4 | ForEach-Object { (New-Object -ComObject WScript.Shell).SendKeys([char]174) }'],
                           check=False, capture_output=True, timeout=5)
            return "Volume turned down."
        elif action == "set" and level is not None:
            lvl = max(0, min(100, int(level)))
            import ctypes
            VK_DOWN, VK_UP = 0xB0, 0xAF
            for _ in range(50):
                ctypes.windll.user32.keybd_event(VK_DOWN, 0, 0, 0)
            for _ in range(round(lvl / 2)):
                ctypes.windll.user32.keybd_event(VK_UP, 0, 0, 0)
            return f"Volume set to ~{lvl}%"
        return f"Volume action {action!r} processed."
    elif system == "Darwin":
        if level is not None:
            _run(["osascript", "-e", f"set volume output volume {int(level)}"], timeout=5)
            return f"Volume set to {int(level)}%"
        return "Action completed."
    return "Volume control not supported on this OS."


def _screenshot() -> str:
    out_dir = Path(__file__).resolve().parent.parent / "screenshots"
    out_dir.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"screenshot_{stamp}.png"
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=str(out_path))
        return f"screenshot saved to {out_path}"
    except Exception:
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(out_path)
            return f"screenshot saved to {out_path}"
        except Exception as exc:
            return f"screenshot failed: {exc}"


def _clipboard_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or "(clipboard is empty)"
    except Exception:
        if platform.system() == "Windows":
            return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"], timeout=10)
        return "(clipboard unavailable)"


def _clipboard_set(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text)
        return "clipboard set"
    except Exception:
        if platform.system() == "Windows":
            _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                  f"Set-Clipboard -Value {json.dumps(text)}"], timeout=10)
            return "clipboard set"
        return "failed to set clipboard"


def _set_reminder(message: str, seconds: int) -> str:
    if seconds <= 0:
        return "Reminder delay must be > 0 seconds."

    def _alert():
        time.sleep(seconds)
        print(f"\n\n[REMINDER]: {message}\nJARVIS: ")
        try:
            if platform.system() == "Windows":
                import winsound
                winsound.Beep(1000, 300)
                winsound.Beep(1200, 400)
        except Exception:
            pass

    threading.Thread(target=_alert, daemon=True).start()
    return f"Reminder set for {message!r} in {seconds} seconds."


def _get_system_stats() -> str:
    import psutil
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    
    disk_target = "C:\\" if os.name == "nt" else "/"
    try:
        disk = psutil.disk_usage(disk_target)
        disk_str = f"Disk {disk.percent:.0f}% used ({disk.free / 1e9:.1f} GB free)"
    except Exception:
        disk_str = "Disk info unavailable"

    battery = psutil.sensors_battery()
    bat_str = f"Battery: {battery.percent}% ({'Plugged in' if battery.power_plugged else 'On Battery'})" if battery else "Desktop AC"

    uptime_hours = int((time.time() - psutil.boot_time()) // 3600)
    return (f"CPU: {cpu:.0f}% ({psutil.cpu_count(logical=True)} cores) | "
            f"RAM: {mem.percent:.0f}% used ({mem.used / 1e9:.1f}/{mem.total / 1e9:.1f} GB) | "
            f"{disk_str} | {bat_str} | Uptime: {uptime_hours}h")


def _clean_temp_files(dry_run: bool = False) -> str:
    temp_dirs = []
    if os.name == "nt":
        if "TEMP" in os.environ:
            temp_dirs.append(Path(os.environ["TEMP"]))
        if "TMP" in os.environ:
            temp_dirs.append(Path(os.environ["TMP"]))
    else:
        temp_dirs.append(Path("/tmp"))

    total_bytes = 0
    deleted_files = 0

    seen = set()
    for tdir in temp_dirs:
        if not tdir.exists():
            continue
        try:
            for item in tdir.iterdir():
                if item in seen:
                    continue
                seen.add(item)
                try:
                    if item.is_file() or item.is_symlink():
                        sz = item.stat().st_size
                        total_bytes += sz
                        if not dry_run:
                            item.unlink(missing_ok=True)
                            deleted_files += 1
                    elif item.is_dir():
                        if not dry_run:
                            shutil.rmtree(item, ignore_errors=True)
                            deleted_files += 1
                except Exception:
                    pass
        except Exception:
            pass

    mb = total_bytes / (1024 * 1024)
    if dry_run:
        return f"Temp scan complete, Sir. Found approximately {mb:.1f} MB of temporary files eligible for cleanup."
    return f"Cleanup complete, Sir. Successfully purged {deleted_files} items, freeing approximately {mb:.1f} MB of disk space."


def _get_top_processes(sort_by: str = "cpu", limit: int = 5) -> str:
    import psutil
    procs = []
    sort_key = "cpu_percent" if sort_by.lower() == "cpu" else "memory_percent"

    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x.get(sort_key) or 0.0, reverse=True)
    top = procs[:max(1, min(limit, 20))]
    lines = [f"Top {len(top)} processes by {sort_by.upper()}:"]
    for idx, p in enumerate(top, 1):
        lines.append(f"{idx}. {p['name']} (PID {p['pid']}) — CPU: {p['cpu_percent']:.1f}%, RAM: {p['memory_percent']:.1f}%")
    return "\n".join(lines)


def _media_control(action: str) -> str:
    action = action.lower().strip()
    if platform.system() == "Windows":
        import ctypes
        VK_MAP = {
            "play_pause": 0xB3,
            "next": 0xB0,
            "prev": 0xB1,
            "stop": 0xB2,
        }
        vk = VK_MAP.get(action)
        if vk is not None:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            return f"Media command '{action}' executed, Sir."
        return f"Unknown media action: {action}"
    return "Media control is only supported on Windows in this build."


def _search_files(query: str, location: str = "desktop", max_results: int = 10) -> str:
    import fnmatch
    loc = location.lower().strip()
    user_home = Path.home()
    if loc == "desktop":
        base_dir = user_home / "Desktop"
    elif loc == "downloads":
        base_dir = user_home / "Downloads"
    elif loc == "documents":
        base_dir = user_home / "Documents"
    else:
        base_dir = Path(location).expanduser()

    if not base_dir.exists():
        return f"Location '{base_dir}' does not exist."

    matches = []
    pattern = query if ("*" in query or "?" in query) else f"*{query}*"
    count = 0
    try:
        for root, _, files in os.walk(base_dir):
            for f in files:
                if fnmatch.fnmatch(f.lower(), pattern.lower()):
                    fp = Path(root) / f
                    try:
                        sz_kb = fp.stat().st_size / 1024
                        matches.append(f"{f} ({sz_kb:.1f} KB) -> {fp}")
                    except Exception:
                        matches.append(f"{f} -> {fp}")
                    count += 1
                    if count >= max_results:
                        break
            if count >= max_results:
                break
    except Exception as exc:
        return f"Search encountered an issue: {exc}"

    if not matches:
        return f"No files matching '{query}' found in {base_dir.name}."
    return f"Found {len(matches)} matching file(s) in {base_dir.name}:\n" + "\n".join(matches)


def _get_network_status() -> str:
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    ping_status = "Online"
    latency = "N/A"
    try:
        t0 = time.time()
        s = socket.create_connection(("8.8.8.8", 53), timeout=2.5)
        latency = f"{(time.time() - t0) * 1000:.0f} ms"
        s.close()
    except Exception:
        ping_status = "Offline / Degraded"

    return f"Network Status: {ping_status} | Hostname: {hostname} | Local IP: {local_ip} | Gateway Latency: {latency}"


def _manage_agenda(memory: Memory, action: str, title: str = "", due_time: str = "") -> str:
    act = action.lower().strip()
    if act == "list":
        plans = memory.list_plans("pending")
        if not plans:
            return "No pending items currently on your agenda, Sir. All clear."
        lines = [f"Agenda ({len(plans)} pending objective{'s' if len(plans) != 1 else ''}):"]
        for p in plans:
            due = f" [Due: {p['due_time']}]" if p['due_time'] else ""
            lines.append(f"- #{p['id']}: {p['title']}{due}")
        return "\n".join(lines)

    if act == "add":
        if not title:
            return "Please provide a title or description for the plan item."
        pid = memory.add_plan(title, "task", due_time)
        return f"Objective #{pid} logged to agenda: '{title}'" + (f" (Due: {due_time})" if due_time else "") + ", Sir."

    if act == "complete":
        if not title:
            return "Please specify the plan ID or title to mark complete."
        ok = memory.complete_plan(title)
        if ok:
            return f"Objective '{title}' marked as completed, Sir."
        return f"Could not find an open objective matching '{title}', Sir."

    if act == "clear":
        c = memory.clear_completed_plans()
        return f"Archived {c} completed objective(s) from memory, Sir."

    return f"Unknown agenda action: {action}"


def _morning_briefing(memory: Memory, config: Config) -> str:
    now = _dt.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%A, %d %B %Y")
    
    weather = _get_weather("")
    stats = _get_system_stats()
    
    plans = memory.list_plans("pending")
    if plans:
        agenda_str = f"You have {len(plans)} pending objective(s) today: " + "; ".join(f"{p['title']}" for p in plans[:3])
    else:
        agenda_str = "You have no standing appointments or pending objectives on the agenda, Sir."

    return (
        f"Good day, {config.user_title}. It is {time_str} on {date_str}.\n"
        f"Weather report: {weather}.\n"
        f"Agenda: {agenda_str}.\n"
        f"System health check: {stats}."
    )


# --------------------------------------------------------------------------- registry

class ToolRegistry:
    """Executes tools by name. dispatch() never raises — errors become strings."""

    def __init__(self, memory: Memory, config: Config) -> None:
        self.memory = memory
        self.config = config

    def dispatch(self, name: str, args: dict) -> str:
        try:
            return self._execute(name, args or {})
        except Exception as exc:  # noqa: BLE001 — contract: never raise
            log.warning("tool %s failed: %s: %s", name, type(exc).__name__, exc)
            return f"ERROR: {type(exc).__name__}: {exc}"

    def _execute(self, name: str, a: dict[str, Any]) -> str:
        if name == "get_current_time":
            return _dt.datetime.now().strftime("%H:%M:%S")
        if name == "get_date":
            now = _dt.date.today()
            return now.strftime("%Y-%m-%d") + f" ({now.strftime('%A')})"
        if name == "open_application":
            return platform_open(str(a["target"]))
        if name == "run_shell_command":
            cmd = str(a["command"])
            if self.config.confirm_shell:
                answer = input(f"Run shell command: {cmd!r} ? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    return "User declined to run the command."
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True, text=True, timeout=25, check=False
            )
            out = ((result.stdout or "") + (result.stderr or "")).strip()
            return (out[:4000] or f"(exit code {result.returncode})")
        if name == "read_file":
            p = _check_path(str(a["path"]), self.config)
            text = p.read_text(encoding="utf-8", errors="replace")
            return text[:8000] + ("\n...[truncated]" if len(text) > 8000 else "")
        if name == "write_file":
            p = _check_path(str(a["path"]), self.config)
            p.parent.mkdir(parents=True, exist_ok=True)
            content = str(a.get("content", ""))
            p.write_text(content, encoding="utf-8")
            return f"wrote {len(content)} chars to {p}"
        if name == "list_directory":
            p = _check_path(str(a["path"]), self.config)
            entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
            lines = []
            for e in entries[:200]:
                kind = "dir " if e.is_dir() else "file"
                size = e.stat().st_size if e.is_file() else ""
                lines.append(f"{kind}  {e.name}  {size}")
            return "\n".join(lines) or "(empty directory)"
        if name == "web_search":
            return _web_search(str(a["query"]))
        if name == "get_weather":
            return _get_weather(str(a.get("city", "")))
        if name == "calculate":
            return str(safe_eval(str(a["expression"])))
        if name == "get_system_stats":
            return _get_system_stats()
        if name == "set_volume":
            return _set_volume(str(a.get("action", "up")), a.get("level"))
        if name == "take_screenshot":
            return _screenshot()
        if name == "clipboard_get":
            return _clipboard_get()
        if name == "clipboard_set":
            return _clipboard_set(str(a["text"]))
        if name == "remember":
            self.memory.add_fact(str(a["fact"]), str(a.get("tags", "")))
            return "fact stored in persistent memory"
        if name == "recall":
            facts = self.memory.search(str(a["query"]), int(a.get("k", 5)))
            return "\n".join(facts) or "no matching facts in memory"
        if name == "set_reminder":
            return _set_reminder(str(a["message"]), int(a["seconds"]))
        if name == "manage_agenda":
            return _manage_agenda(self.memory, str(a.get("action", "list")), str(a.get("title", "")), str(a.get("due_time", "")))
        if name == "clean_temp_files":
            return _clean_temp_files(bool(a.get("dry_run", False)))
        if name == "get_top_processes":
            return _get_top_processes(str(a.get("sort_by", "cpu")), int(a.get("limit", 5)))
        if name == "media_control":
            return _media_control(str(a.get("action", "play_pause")))
        if name == "search_files":
            return _search_files(str(a["query"]), str(a.get("location", "desktop")), int(a.get("max_results", 10)))
        if name == "get_network_status":
            return _get_network_status()
        if name == "morning_briefing":
            return _morning_briefing(self.memory, self.config)
        raise ValueError(f"unknown tool: {name!r}")
