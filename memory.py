"""Persistent long-term memory for JARVIS.

Saves and retrieves facts, preferences, user identity, and session notes
in data/memory.json across conversations.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

import config

log = logging.getLogger("jarvis.memory")

MEMORY_FILE = config.DATA_DIR / "memory.json"


class Memory:
    def __init__(self, filepath: Path = MEMORY_FILE):
        self.filepath = filepath
        self.data: dict[str, Any] = {
            "user_title": config.USER_TITLE,
            "assistant_name": config.ASSISTANT_NAME,
            "created_at": datetime.datetime.now().isoformat(),
            "facts": [],
            "preferences": {},
            "recent_sessions": [],
        }
        self.load()

    def load(self) -> None:
        """Load memory state from disk."""
        if not self.filepath.exists():
            self.save()
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except Exception as exc:
            log.warning("Could not read memory file (%s), reinitializing: %s", self.filepath, exc)

    def save(self) -> None:
        """Commit memory state to disk."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            log.error("Failed to save memory: %s", exc)

    def add_fact(self, fact: str) -> str:
        """Remember a personal fact about the user or system."""
        fact_str = fact.strip()
        if not fact_str:
            return "No fact content provided."
        entry = {
            "id": len(self.data.get("facts", [])) + 1,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fact": fact_str,
        }
        self.data.setdefault("facts", []).append(entry)
        self.save()
        return f"I shall remember that, {self.data.get('user_title', 'Sir')}: '{fact_str}'"

    def get_facts(self) -> list[str]:
        """Return list of all stored facts."""
        return [f["fact"] for f in self.data.get("facts", [])]

    def set_preference(self, key: str, value: Any) -> str:
        """Set a user preference."""
        self.data.setdefault("preferences", {})[key] = value
        self.save()
        return f"Preference '{key}' updated to '{value}'."

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.data.get("preferences", {}).get(key, default)

    def record_session(self, summary: str) -> None:
        """Record a brief note about the current session."""
        sessions = self.data.setdefault("recent_sessions", [])
        sessions.append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": summary[:300],
        })
        if len(sessions) > 10:
            self.data["recent_sessions"] = sessions[-10:]
        self.save()

    def build_system_context(self) -> str:
        """Build injected memory section for system prompt."""
        facts = self.get_facts()
        prefs = self.data.get("preferences", {})
        parts = []

        if facts:
            facts_list = "\n".join(f"- {f}" for f in facts[-10:])
            parts.append(f"Things you remember about {self.data.get('user_title', 'Sir')}:\n{facts_list}")

        if prefs:
            prefs_list = "\n".join(f"- {k}: {v}" for k, v in prefs.items())
            parts.append(f"User Preferences:\n{prefs_list}")

        return "\n\n".join(parts)


# Global singleton instance
memory_store = Memory()
