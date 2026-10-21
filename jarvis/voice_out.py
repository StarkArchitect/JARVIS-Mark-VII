"""Sentence-chunked TTS on a worker thread with barge-in interruption.

Primary: Natural British Neural Voice (Edge-TTS 'en-GB-RyanNeural') via pygame.
Fallback: Offline SAPI5 engine (pyttsx3).
Features: Real-time audio level callback for GUI Arc Reactor pulse animation.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import queue
import random
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import pygame
    _PYGAME_AVAILABLE = True
except Exception:
    _PYGAME_AVAILABLE = False

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except Exception:
    _PYTTSX3_AVAILABLE = False

try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except Exception:
    _EDGE_TTS_AVAILABLE = False

log = logging.getLogger("jarvis.voice_out")


def _clean_for_speech(text: str) -> str:
    """Filter out code blocks, markdown links, symbols, and formatting for natural speech."""
    s = re.sub(r"```[\s\S]*?```", " [code snippet] ", text)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    s = re.sub(r"https?://\S+", "link", s)
    s = re.sub(r"^[\s*\-•]+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+\.\s*", "", s, flags=re.MULTILINE)
    s = s.replace("**", "").replace("*", "").replace("##", "").replace("#", "")
    s = s.replace("—", ", ").replace("--", ", ")
    s = s.replace("🔴", "").replace("🔋", "").replace("⚠️", "").replace("⚡", "").replace("✓", "").replace("✗", "")
    return s.strip()


class Speaker:
    """Queues sentences; a single worker thread owns the audio playback."""

    def __init__(
        self,
        voice: str = "en-GB-RyanNeural",
        rate: int = 180,
        audio_level_callback: Optional[Callable[[float], None]] = None,
        state_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.voice = voice or "en-GB-RyanNeural"
        self.rate = rate
        self.audio_level_callback = audio_level_callback
        self.state_callback = state_callback
        self.ok = _EDGE_TTS_AVAILABLE or _PYTTSX3_AVAILABLE
        self._q: queue.Queue[str | None] = queue.Queue()
        self._stop = threading.Event()
        self._busy = threading.Event()
        self._pyttsx3_engine = None
        self.is_speaking = False

        if _PYGAME_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
            except Exception as exc:
                log.warning("Pygame mixer init failed: %s", exc)

        if _PYTTSX3_AVAILABLE:
            try:
                self._pyttsx3_engine = pyttsx3.init()
            except Exception:
                pass

        self._thread = threading.Thread(target=self._worker, daemon=True, name="jarvis-tts")
        self._thread.start()

    @property
    def busy(self) -> bool:
        return self._busy.is_set() or not self._q.empty()

    def set_callbacks(
        self,
        audio_level_callback: Optional[Callable[[float], None]] = None,
        state_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        if audio_level_callback:
            self.audio_level_callback = audio_level_callback
        if state_callback:
            self.state_callback = state_callback

    def say(self, text: str) -> None:
        """Enqueue one sentence (safe to call from any thread)."""
        self._stop.clear()
        clean = _clean_for_speech(text)
        if clean:
            self._q.put(clean)

    def interrupt(self) -> None:
        """Barge-in: stop current speech immediately and flush queued sentences."""
        self._stop.set()
        self.is_speaking = False
        if _PYGAME_AVAILABLE:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        if self._pyttsx3_engine is not None:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass
        self._drain()
        if self.audio_level_callback:
            self.audio_level_callback(0.0)
        if self.state_callback:
            self.state_callback("IDLE")

    def reset(self) -> None:
        """Clear the interrupt flag for the next turn."""
        self._stop.clear()
        self.is_speaking = False

    def _worker(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                break
            if self._stop.is_set():
                self._drain()
                self._stop.clear()
                continue
            self._busy.set()
            self.is_speaking = True
            if self.state_callback:
                self.state_callback("SPEAKING")
            try:
                self._speak_sentence(text)
            except Exception:
                log.warning("TTS playback error", exc_info=True)
            finally:
                self.is_speaking = False
                self._busy.clear()
                if self._q.empty():
                    if self.state_callback:
                        self.state_callback("IDLE")
                    if self.audio_level_callback:
                        self.audio_level_callback(0.0)

    def _speak_sentence(self, text: str) -> None:
        if self._stop.is_set():
            return

        # 1. Primary: Edge TTS + Pygame
        if _EDGE_TTS_AVAILABLE and _PYGAME_AVAILABLE:
            temp_path = None
            try:
                communicate = edge_tts.Communicate(text, voice=self.voice)
                cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                temp_path = cache_dir / f"tts_{os.getpid()}_{int(time.time()*1000)}_{random.randint(100,999)}.mp3"
                
                async def _save_with_timeout():
                    await communicate.save(str(temp_path))

                asyncio.run(asyncio.wait_for(_save_with_timeout(), timeout=8.0))

                if self._stop.is_set():
                    return

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)

                pygame.mixer.music.load(str(temp_path))
                pygame.mixer.music.play()

                # Visualizer simulation loop while music plays
                step = 0
                while pygame.mixer.music.get_busy():
                    if self._stop.is_set():
                        pygame.mixer.music.stop()
                        break
                    step += 1
                    # Generate natural vocal rhythm wave
                    lvl = 0.45 + 0.4 * math.sin(step * 0.4) + 0.15 * math.cos(step * 0.8)
                    lvl = max(0.15, min(0.95, lvl + random.uniform(-0.1, 0.1)))
                    if self.audio_level_callback:
                        self.audio_level_callback(lvl)
                    time.sleep(0.05)
                return
            except Exception as exc:
                log.warning("Edge-TTS error (%s), using pyttsx3 fallback", exc)
            finally:
                if self.audio_level_callback:
                    self.audio_level_callback(0.0)
                if temp_path and temp_path.exists():
                    try:
                        if pygame.mixer.get_init():
                            pygame.mixer.music.unload()
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

        # 2. Offline fallback: pyttsx3
        if self._pyttsx3_engine is not None and not self._stop.is_set():
            try:
                self._pyttsx3_engine.say(text)
                self._pyttsx3_engine.runAndWait()
            except Exception as exc:
                log.warning("pyttsx3 error: %s", exc)

    def _drain(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return
