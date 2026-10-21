"""Python-to-JavaScript Bridge for J.A.R.V.I.S. Stark Industries HUD.

Provides bidirectional communication between the pywebview HTML5/Canvas UI
and the JARVIS core (Brain, Memory, Tools, Voice In, Voice Out).
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from typing import Any, Optional

import psutil

from .brain import Brain
from .config import Config
from .memory import Memory
from .utils import get_logger
from .voice_in import Listener
from .voice_out import Speaker

log = get_logger()


class JarvisGUIBridge:
    """API object exposed to JavaScript via pywebview.api."""

    def __init__(
        self,
        brain: Brain,
        memory: Memory,
        config: Config,
        speaker: Optional[Speaker] = None,
        listener: Optional[Listener] = None,
    ) -> None:
        self.brain = brain
        self.memory = memory
        self.config = config
        self.speaker = speaker or Speaker(voice=config.tts_voice)
        self.listener = listener or Listener(stt_model=config.stt_model, wake_word=config.wake_word)

        self.window = None  # Bound by gui.py once pywebview window is created
        self.is_muted = False
        self._running = True
        self._is_processing = False
        self._is_recording = False
        self._last_audio_update = 0.0

        # Wire audio level and state callbacks
        self._setup_callbacks()

        # Telemetry thread
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_worker, daemon=True, name="jarvis-telemetry"
        )
        self._telemetry_thread.start()

    def set_window(self, window: Any) -> None:
        """Bind the pywebview window instance."""
        self.window = window
        # Send initial state and initial telemetry
        threading.Thread(target=self._initial_sync, daemon=True).start()

    def _initial_sync(self) -> None:
        time.sleep(0.8)
        self.safe_eval_js("window.updateState('IDLE')")
        self._push_telemetry()
        # Add welcome message
        welcome = f"Welcome back, {self.config.user_title}. All Mark VII diagnostic subroutines are online."
        self.safe_eval_js(f"window.addMessage('JARVIS', {json.dumps(welcome)})")
        if not self.is_muted:
            self.speaker.say(welcome)

    def _setup_callbacks(self) -> None:
        def on_audio_level(lvl: float) -> None:
            now = time.time()
            if now - self._last_audio_update >= 0.035:  # ~28 fps throttle
                self._last_audio_update = now
                self.safe_eval_js(f"window.updateAudioLevel({lvl:.3f})")

        def on_speaker_state(state: str) -> None:
            self.safe_eval_js(f"window.updateState({json.dumps(state)})")

        self.speaker.set_callbacks(
            audio_level_callback=on_audio_level,
            state_callback=on_speaker_state,
        )

        def on_listener_audio(lvl: float) -> None:
            now = time.time()
            if now - self._last_audio_update >= 0.035:
                self._last_audio_update = now
                self.safe_eval_js(f"window.updateAudioLevel({lvl:.3f})")

        def on_listener_state(state: str) -> None:
            self.safe_eval_js(f"window.updateState({json.dumps(state)})")

        self.listener.set_callbacks(
            audio_level_callback=on_listener_audio,
            state_callback=on_listener_state,
        )

    def safe_eval_js(self, js_code: str) -> None:
        """Execute JS in pywebview safely without raising on GUI teardown."""
        if not self.window:
            return
        try:
            self.window.evaluate_js(js_code)
        except Exception as exc:
            log.debug("safe_eval_js exception: %s", exc)

    # ------------------------------------------------------------------ Telemetry
    def _telemetry_worker(self) -> None:
        while self._running:
            self._push_telemetry()
            time.sleep(1.5)

    def _push_telemetry(self) -> None:
        if not self.window:
            return
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent

            disk_target = "C:\\" if os.name == "nt" else "/"
            try:
                disk = psutil.disk_usage(disk_target).percent
                disk_str = f"{disk:.0f}%"
            except Exception:
                disk_str = "N/A"

            battery = psutil.sensors_battery()
            if battery:
                status = "AC" if battery.power_plugged else "BAT"
                battery_str = f"{battery.percent:.0f}% [{status}]"
            else:
                battery_str = "100% [AC]"

            uptime_sec = time.time() - psutil.boot_time()
            hours = int(uptime_sec // 3600)
            minutes = int((uptime_sec % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"

            provider = getattr(self.brain, "active_provider_label", "Stark Core")

            data = {
                "cpu": round(cpu, 1),
                "ram": round(ram, 1),
                "battery": battery_str,
                "disk": disk_str,
                "uptime": uptime_str,
                "provider": provider,
            }
            self.safe_eval_js(f"window.updateTelemetry({json.dumps(data)})")
        except Exception as exc:
            log.debug("Telemetry error: %s", exc)

    # ------------------------------------------------------------------ JS API methods
    def send_text(self, text: str) -> None:
        """Receive user text from GUI chat input and stream reply."""
        if not text or not text.strip():
            return
        clean_text = text.strip()
        threading.Thread(target=self._process_text, args=(clean_text,), daemon=True).start()

    def _process_text(self, user_text: str) -> None:
        if self._is_processing:
            log.info("Already processing a query; interrupting speaker.")
            self.speaker.interrupt()

        self.speaker.reset()
        self._is_processing = True
        try:
            self.safe_eval_js("window.updateState('PROCESSING')")
            self.safe_eval_js("window.startJarvisReply()")

            def on_sentence(sentence: str) -> None:
                if not self.is_muted:
                    self.speaker.say(sentence)

            def on_token(token: str) -> None:
                self.safe_eval_js(f"window.appendToken({json.dumps(token)})")

            reply = self.brain.stream_reply(
                user_text,
                on_sentence=on_sentence,
                on_token=on_token,
            )

            # Keep state updated while speaking
            while self.speaker.busy:
                time.sleep(0.08)

        except Exception as exc:
            log.error("Error processing reply: %s", exc, exc_info=True)
            err_msg = f"System Error: {exc}"
            self.safe_eval_js(f"window.addMessage('SYSTEM', {json.dumps(err_msg)})")
            if not self.is_muted:
                self.speaker.say("I encountered an anomaly while processing your request, Sir.")
        finally:
            self._is_processing = False
            self.safe_eval_js("window.updateState('IDLE')")
            self.safe_eval_js("window.updateAudioLevel(0)")

    def toggle_voice(self) -> None:
        """Toggle microphone recording from HUD core button or hotkey."""
        if self._is_recording:
            log.info("Stopping recording early.")
            self.listener.stop_recording()
            return

        threading.Thread(target=self._record_and_process, daemon=True).start()

    def _record_and_process(self) -> None:
        if not self.listener.available:
            self.safe_eval_js("window.addMessage('SYSTEM', 'Microphone hardware unavailable.')")
            if not self.is_muted:
                self.speaker.say("Microphone input is currently unavailable, Sir.")
            return

        self._is_recording = True
        self.speaker.interrupt()
        self.safe_eval_js("window.updateState('LISTENING')")

        try:
            audio = self.listener.record_until_silence(max_seconds=12.0)
            self.safe_eval_js("window.updateState('PROCESSING')")
            if audio is None or len(audio) == 0:
                log.info("No audio recorded.")
                self.safe_eval_js("window.updateState('IDLE')")
                return

            text = self.listener.transcribe(audio)
            if not text:
                log.info("Whisper transcription returned empty string.")
                self.safe_eval_js("window.updateState('IDLE')")
                return

            # Display transcribed text in chat
            self.safe_eval_js(f"window.addMessage('USER', {json.dumps(text)})")
            self.speaker.reset()
            # Process the response
            self._process_text(text)

        except Exception as exc:
            log.error("Voice recording error: %s", exc, exc_info=True)
            self.safe_eval_js("window.updateState('IDLE')")
        finally:
            self._is_recording = False

    def stop_speech(self) -> None:
        """Immediate barge-in or silence command."""
        self.speaker.interrupt()
        self.listener.stop_recording()
        self.safe_eval_js("window.updateState('IDLE')")
        self.safe_eval_js("window.updateAudioLevel(0)")

    def toggle_mute(self, is_muted: bool) -> None:
        """Mute or unmute voice audio output."""
        self.is_muted = bool(is_muted)
        if self.is_muted:
            self.speaker.interrupt()

    def run_quick_tool(self, tool_name: str) -> None:
        """Execute a quick HUD diagnostic or shortcut action."""
        threading.Thread(target=self._exec_quick_tool, args=(tool_name,), daemon=True).start()

    def _exec_quick_tool(self, tool_name: str) -> None:
        tool_name = tool_name.lower().strip()
        registry = getattr(self.brain, "registry", None)
        if not registry:
            return

        self.safe_eval_js("window.updateState('PROCESSING')")
        try:
            if tool_name in ("stats", "get_system_stats"):
                result = registry.dispatch("get_system_stats", {})
                self.safe_eval_js(f"window.addMessage('SYSTEM', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say("System diagnostics complete, Sir. All telemetry within nominal parameters.")

            elif tool_name in ("time", "get_current_time"):
                result = registry.dispatch("get_current_time", {})
                date_str = registry.dispatch("get_date", {})
                full = f"{date_str} | {result}"
                self.safe_eval_js(f"window.addMessage('SYSTEM', {json.dumps(full)})")
                if not self.is_muted:
                    self.speaker.say(f"It is {result}, Sir.")

            elif tool_name in ("weather", "get_weather"):
                result = registry.dispatch("get_weather", {"city": ""})
                self.safe_eval_js(f"window.addMessage('SYSTEM', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say(result)

            elif tool_name in ("screenshot", "take_screenshot"):
                result = registry.dispatch("take_screenshot", {})
                self.safe_eval_js(f"window.addMessage('SYSTEM', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say("Display capture saved, Sir.")

            elif tool_name in ("plan", "agenda", "manage_agenda"):
                result = registry.dispatch("manage_agenda", {"action": "list"})
                self.safe_eval_js(f"window.addMessage('JARVIS', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say(result)

            elif tool_name in ("briefing", "morning_briefing"):
                result = registry.dispatch("morning_briefing", {})
                self.safe_eval_js(f"window.addMessage('JARVIS', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say(result)

            elif tool_name in ("cleantemp", "clean_temp_files"):
                result = registry.dispatch("clean_temp_files", {"dry_run": False})
                self.safe_eval_js(f"window.addMessage('JARVIS', {json.dumps(result)})")
                if not self.is_muted:
                    self.speaker.say(result)

            else:
                self.safe_eval_js(f"window.addMessage('SYSTEM', 'Unknown tool command: {tool_name}')")

        except Exception as exc:
            log.error("Tool execution failed: %s", exc)
            self.safe_eval_js(f"window.addMessage('SYSTEM', 'Tool execution failed: {exc}')")
        finally:
            self.safe_eval_js("window.updateState('IDLE')")

    def close(self) -> None:
        """Clean shutdown of background threads and devices."""
        self._running = False
        self.speaker.interrupt()
        self.listener.close()
