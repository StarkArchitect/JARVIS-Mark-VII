"""Voice input (STT) and output (TTS) engine for JARVIS.

- TTS: Natural British Butler voice ('en-GB-RyanNeural') via edge-tts with pygame playback and pyttsx3 fallback.
- STT: Blazing fast transcription using Groq's free Whisper API ('whisper-large-v3-turbo').
- Wake Word: Built-in Picovoice Porcupine support, plus continuous listening and Push-To-Talk modes.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pygame
import sounddevice as sd
from openai import OpenAI

import config

log = logging.getLogger("jarvis.voice")

# Initialize pygame mixer once
try:
    pygame.mixer.init(frequency=24000)
except Exception:
    try:
        pygame.mixer.init()
    except Exception as exc:
        log.warning("Could not initialize pygame mixer: %s", exc)

_is_speaking = False
_stop_speech_flag = False


# =====================================================================
# 1. Text-To-Speech (TTS)
# =====================================================================
def stop_speaking() -> None:
    """Halt any active audio playback immediately."""
    global _is_speaking, _stop_speech_flag
    _stop_speech_flag = True
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass
    _is_speaking = False


def speak(text: str, interruptible: bool = True) -> None:
    """Speak text aloud using Edge-TTS neural voice with offline fallback."""
    global _is_speaking, _stop_speech_flag
    clean_text = text.strip()
    if not clean_text:
        return

    # Strip code blocks or special markdown characters for natural speech
    speech_text = _clean_text_for_speech(clean_text)
    if not speech_text:
        return

    _stop_speech_flag = False
    _is_speaking = True

    try:
        # Run async edge-tts generation
        asyncio.run(_edge_tts_speak(speech_text, interruptible))
    except Exception as exc:
        log.warning("Edge-TTS failed (%s), falling back to pyttsx3 offline engine...", exc)
        _pyttsx3_fallback(speech_text)
    finally:
        _is_speaking = False


async def _edge_tts_speak(text: str, interruptible: bool) -> None:
    global _stop_speech_flag
    import edge_tts

    voice = config.TTS_VOICE
    rate = config.TTS_RATE
    volume = config.TTS_VOLUME

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)

    # Save to a temporary mp3 file
    temp_dir = config.DATA_DIR / "cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"tts_{os.getpid()}_{int(time.time()*1000)}.mp3"

    try:
        await communicate.save(str(temp_file))

        if _stop_speech_flag:
            return

        # Play via pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(str(temp_file))
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if _stop_speech_flag and interruptible:
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.05)

    finally:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.unload()
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
        except Exception:
            pass


def _pyttsx3_fallback(text: str) -> None:
    """Offline SAPI5 TTS fallback for Windows."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Prefer British or Male voice if found
        voices = engine.getProperty("voices")
        for v in voices:
            if "george" in v.name.lower() or "david" in v.name.lower() or "hazel" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        log.error("pyttsx3 fallback failed: %s", exc)


def _clean_text_for_speech(text: str) -> str:
    """Filter out markdown, URLs, code blocks, and symbols for fluid speech."""
    import re
    # Remove code blocks
    s = re.sub(r"```[\s\S]*?```", " [code snippet omitted] ", text)
    # Remove inline code
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Remove markdown links [text](url) -> text
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    # Remove URLs
    s = re.sub(r"https?://\S+", "link", s)
    # Remove asterisks and hashes
    s = s.replace("**", "").replace("*", "").replace("##", "").replace("#", "")
    return s.strip()


# =====================================================================
# 2. Speech-To-Text (STT) via Groq Whisper API
# =====================================================================
def transcribe_audio_buffer(wav_bytes: bytes) -> str:
    """Transcribe in-memory WAV audio bytes using Groq's free Whisper API."""
    if not config.GROQ_API_KEY:
        log.warning("No GROQ_API_KEY available for Whisper transcription.")
        return ""

    try:
        client = OpenAI(
            api_key=config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=25.0,
        )

        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"

        transcription = client.audio.transcriptions.create(
            model=config.STT_MODEL,
            file=audio_file,
            language=config.STT_LANGUAGE,
            response_format="text",
        )
        return str(transcription).strip()
    except Exception as exc:
        log.warning("Groq Whisper transcription failed: %s", exc)
        return ""


def encode_pcm_to_wav(pcm_data: np.ndarray, sample_rate: int = config.SAMPLE_RATE) -> bytes:
    """Encode numpy int16 PCM array into standard WAV bytes in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data.tobytes())
    return buf.getvalue()


# =====================================================================
# 3. Audio Recording & Silence Detection
# =====================================================================
def record_utterance(
    status_callback: Optional[Callable[[str], None]] = None,
    silence_rms: float = config.SILENCE_RMS,
    silence_hang: float = config.SILENCE_HANG,
    max_duration: float = config.MAX_UTTERANCE,
) -> Optional[np.ndarray]:
    """Record microphone audio until the user stops speaking."""
    sample_rate = config.SAMPLE_RATE
    block_size = config.BLOCK_SIZE
    mic_device = config.MIC_DEVICE

    audio_queue: queue.Queue[np.ndarray] = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status and config.VERBOSE:
            log.debug("Audio status: %s", status)
        audio_queue.put(indata.copy())

    recorded_blocks = []
    speaking_started = False
    silence_start = None
    start_time = time.time()

    if status_callback:
        status_callback("Listening...")

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
            device=mic_device,
            callback=audio_callback,
        ):
            while True:
                # Check maximum duration
                if time.time() - start_time > max_duration:
                    break

                try:
                    block = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Calculate RMS
                data_float = block.astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(data_float**2)))

                if rms > silence_rms:
                    if not speaking_started:
                        speaking_started = True
                        if status_callback:
                            status_callback("Hearing you...")
                    silence_start = None
                    recorded_blocks.append(block)
                else:
                    if speaking_started:
                        recorded_blocks.append(block)
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > silence_hang:
                            # Silence hang time exceeded
                            break
                    else:
                        # Keep a tiny rolling buffer before speech starts
                        recorded_blocks.append(block)
                        if len(recorded_blocks) > int(sample_rate / block_size * 0.4):
                            recorded_blocks.pop(0)

    except Exception as exc:
        log.error("Microphone input error: %s", exc)
        if status_callback:
            status_callback(f"Mic error: {exc}")
        return None

    if not speaking_started or not recorded_blocks:
        return None

    return np.concatenate(recorded_blocks, axis=0)


def listen_and_transcribe(status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Listen to microphone and return transcribed text."""
    pcm = record_utterance(status_callback=status_callback)
    if pcm is None or len(pcm) == 0:
        return ""

    if status_callback:
        status_callback("Transcribing...")

    wav_bytes = encode_pcm_to_wav(pcm)
    text = transcribe_audio_buffer(wav_bytes)
    return text


# =====================================================================
# 4. Wake Word Detection (Picovoice Porcupine + Keyless Fallback)
# =====================================================================
def create_wake_word_detector() -> Optional[Any]:
    """Initialize Porcupine wake word engine if access key is present."""
    if not config.PICOVOICE_KEY:
        return None

    try:
        import pvporcupine
        keyword = config.WAKE_WORD
        builtins = [k.value for k in pvporcupine.BuiltinKeyword] if hasattr(pvporcupine, "BuiltinKeyword") else ["jarvis"]
        kw = keyword if keyword in builtins else "jarvis"

        porcupine = pvporcupine.create(
            access_key=config.PICOVOICE_KEY,
            keywords=[kw],
        )
        return porcupine
    except Exception as exc:
        log.warning("Porcupine wake-word failed to initialize: %s", exc)
        return None


def list_microphones() -> list[dict]:
    """Enumerate all available audio input devices."""
    devices = []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({
                    "id": idx,
                    "name": dev.get("name", "Unknown"),
                    "channels": dev.get("max_input_channels"),
                    "default": idx == sd.default.device[0],
                })
    except Exception as exc:
        log.error("Failed to query sound devices: %s", exc)
    return devices
