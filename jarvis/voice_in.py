"""Microphone listener: non-blocking capture, RMS VAD, wake word, Groq Whisper STT.

Includes real-time audio level callbacks for GUI Arc Reactor pulse animation.
"""

from __future__ import annotations

import io
import queue
import time
import wave
from collections import deque
from typing import Callable, Optional

import numpy as np

from .config import load_api_keys
from .utils import get_logger

log = get_logger()

try:
    import sounddevice as _sd
    _SD_AVAILABLE = True
except Exception:  # noqa: BLE001 — PortAudio may be missing entirely
    _SD_AVAILABLE = False

SAMPLE_RATE = 16_000
CHUNK = 1024                    # 64 ms per frame
SILENCE_SECONDS = 0.85          # end-of-speech threshold
PREBUFFER_SECONDS = 0.3
CALIBRATION_SECONDS = 0.75

STOP_WORDS = {"stop", "stop it", "quiet", "shut up", "jarvis stop", "stop jarvis"}


def _encode_wav(audio_pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode float32 or int16 numpy array into standard WAV in-memory bytes."""
    buf = io.BytesIO()
    if audio_pcm.dtype == np.float32 or audio_pcm.dtype == np.float64:
        clipped = np.clip(audio_pcm, -1.0, 1.0)
        pcm_data = (clipped * 32767).astype(np.int16)
    else:
        pcm_data = audio_pcm.astype(np.int16)

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data.tobytes())
    return buf.getvalue()


class Listener:
    """One persistent InputStream; audio callback only enqueues frames."""

    def __init__(
        self,
        stt_model: str = "whisper-large-v3-turbo",
        wake_word: str = "jarvis",
        audio_level_callback: Optional[Callable[[float], None]] = None,
        state_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.wake_word = wake_word.lower()
        self.stt_model_name = stt_model
        self.audio_level_callback = audio_level_callback
        self.state_callback = state_callback
        self.available = False
        self._warned = False
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=256)
        self._stream = None
        self._whisper = None
        self.noise_floor: float | None = None
        self._abort_record = False
        self._groq_key = load_api_keys().get("groq", "")

        if not _SD_AVAILABLE:
            self._warn_once("sounddevice not installed — voice input disabled")
            return
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=CHUNK, callback=self._callback,
            )
            self._stream.start()
            self.available = True
        except Exception as exc:  # noqa: BLE001
            self._warn_once(f"microphone unavailable ({exc}) — voice input disabled")

    def set_callbacks(
        self,
        audio_level_callback: Optional[Callable[[float], None]] = None,
        state_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        if audio_level_callback:
            self.audio_level_callback = audio_level_callback
        if state_callback:
            self.state_callback = state_callback

    def _warn_once(self, message: str) -> None:
        if not self._warned:
            print(f"WARNING: {message}")
            log.warning(message)
            self._warned = True

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        try:
            self._q.put_nowait(indata.copy().reshape(-1))
        except queue.Full:
            pass

    # ------------------------------------------------------------------ VAD

    @staticmethod
    def _rms(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))

    def calibrate(self) -> None:
        """Measure ambient noise for ~0.75 s to set the VAD threshold."""
        levels: list[float] = []
        deadline = time.monotonic() + CALIBRATION_SECONDS
        while time.monotonic() < deadline:
            try:
                frame = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            levels.append(self._rms(frame))
        if levels:
            self.noise_floor = float(np.mean(levels)) * 2.2 + 1e-4
        else:
            self.noise_floor = 0.01
        log.info("VAD noise floor calibrated to %.5f", self.noise_floor)

    def _drain(self) -> None:
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def stop_recording(self) -> None:
        """Signal recording loop to stop immediately."""
        self._abort_record = True

    def _collect_utterance(self, max_seconds: float) -> np.ndarray:
        """Record until ~800 ms of silence, manual abort, or max_seconds."""
        self._abort_record = False
        if self.noise_floor is None:
            self.calibrate()
        self._drain()
        floor = self.noise_floor or 0.01
        chunk_seconds = CHUNK / SAMPLE_RATE
        silence_limit = int(SILENCE_SECONDS / chunk_seconds)
        prebuffer: deque[np.ndarray] = deque(
            maxlen=max(1, int(PREBUFFER_SECONDS / chunk_seconds))
        )
        speech: list[np.ndarray] = []
        silence_run = 0
        started = False
        deadline = time.monotonic() + max_seconds

        if self.state_callback:
            self.state_callback("LISTENING")

        while time.monotonic() < deadline:
            if self._abort_record:
                break

            try:
                frame = self._q.get(timeout=0.2)
            except queue.Empty:
                if started:
                    break
                continue

            rms = self._rms(frame)
            # Normalize level for visualizer (0.0 to 1.0)
            scaled_lvl = min(1.0, max(0.0, (rms - floor) / 0.15))
            if self.audio_level_callback:
                self.audio_level_callback(scaled_lvl)

            if rms > floor:
                if not started:
                    speech.extend(prebuffer)
                    started = True
                speech.append(frame)
                silence_run = 0
            elif started:
                speech.append(frame)
                silence_run += 1
                if silence_run >= silence_limit:
                    break
            else:
                prebuffer.append(frame)

        if self.audio_level_callback:
            self.audio_level_callback(0.0)

        if not speech:
            if self.state_callback:
                self.state_callback("IDLE")
            return np.zeros(0, dtype=np.float32)

        trim = max(0, silence_run - 2) if started else 0
        if trim:
            speech = speech[:-trim]

        return np.concatenate(speech).astype(np.float32)

    # ------------------------------------------------------------------ public API

    def wait_for_wake_word(self) -> bool:
        """Block until a spoken utterance contains the wake word. No double-fire."""
        if not self.available:
            return False
        audio = self._collect_utterance(max_seconds=5.0)
        if audio.size < SAMPLE_RATE // 4:      # ignore tiny blips
            return False
        text = self.transcribe(audio)
        log.debug("wake check heard: %r", text)
        return bool(text) and self.wake_word in text.lower()

    def record_until_silence(self, max_seconds: float = 12.0) -> np.ndarray:
        return self._collect_utterance(max_seconds)

    def barge_in_once(self, timeout: float = 0.4) -> bool:
        """Listen briefly during playback; True only for an explicit stop word."""
        if not self.available or self.noise_floor is None:
            return False
        floor = self.noise_floor
        chunk_seconds = CHUNK / SAMPLE_RATE
        needed = int(1.0 / chunk_seconds)
        frames: list[np.ndarray] = []
        speech_frames = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                frame = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            frames.append(frame)
            if self._rms(frame) > floor:
                speech_frames += 1
            if speech_frames >= needed:
                audio = np.concatenate(frames).astype(np.float32)
                text = self.transcribe(audio).lower().strip(".!? ")
                log.debug("barge-in heard: %r", text)
                return text in STOP_WORDS
        return False

    def transcribe(self, audio: np.ndarray) -> str:
        """Speech-to-text: prefers fast free Groq Whisper API, falls back to faster-whisper."""
        if audio.size == 0:
            return ""

        if self.state_callback:
            self.state_callback("PROCESSING")

        # 1. Primary: Groq Whisper API (<300ms, free)
        if self._groq_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self._groq_key, base_url="https://api.groq.com/openai/v1", timeout=15.0)
                wav_bytes = _encode_wav(audio)
                audio_file = io.BytesIO(wav_bytes)
                audio_file.name = "audio.wav"
                res = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    language="en",
                    response_format="text",
                )
                if self.state_callback:
                    self.state_callback("IDLE")
                return str(res).strip()
            except Exception as exc:
                log.warning("Groq Whisper transcription failed: %s", exc)

        # 2. Fallback: local faster-whisper if installed
        try:
            from faster_whisper import WhisperModel
            if self._whisper is None:
                self._whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
            segments, _info = self._whisper.transcribe(audio, beam_size=1)
            text = " ".join(seg.text for seg in segments).strip()
            if self.state_callback:
                self.state_callback("IDLE")
            return text
        except ImportError:
            pass
        except Exception as exc:
            log.warning("Local whisper failed: %s", exc)

        if self.state_callback:
            self.state_callback("IDLE")
        return ""

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            self.available = False
