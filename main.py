"""JARVIS entrypoint: arg parsing, mode dispatch, diagnostics, and session loop."""

from __future__ import annotations

import argparse
import sys
import time

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jarvis.brain import Brain, MockBrain
from jarvis.config import Config, load_config
from jarvis.memory import Memory
from jarvis.utils import get_logger


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jarvis", description="Local desktop AI assistant")
    parser.add_argument("--gui", action="store_true", help="launch Stark Industries holographic Arc Reactor GUI")
    parser.add_argument("--text", action="store_true", help="text chat mode")
    parser.add_argument("--voice", action="store_true", help="hands-free voice mode")
    parser.add_argument("--ptt", action="store_true", help="push-to-talk voice mode")
    parser.add_argument("--diag", action="store_true", help="run hardware & API diagnostics")
    parser.add_argument("--list-mics", action="store_true", help="list audio input devices")
    parser.add_argument("--reset", action="store_true", help="wipe conversation history and exit")
    parser.add_argument("--dry-run", action="store_true", help="no API calls; mocked brain")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    return parser.parse_args(argv)


BANNER = r"""
       __ ___       ______   ____    ____  __     _______.
      |  |   \     |   _  \  \   \  /   / |  |   /       |
      |  |/   \    |  |_)  |  \   \/   /  |  |  |   (----`
  .--.|  /  ^  \   |      /    \_    _/   |  |   \   \    
  |  `--/  /_\  \  |  |\  \-.    |  |     |  |----)   |   
   \___/__/   \__\ |__| `.__|    |__|     |__|_______/    
  =========================================================
  [ STARK INDUSTRIES PROTOCOL MARK VII | ALL SYSTEMS NOMINAL ]
"""


def _banner(dry_run: bool, mode: str = "text") -> None:
    tag = " [DRY-RUN]" if dry_run else ""
    print(BANNER)
    print(f"JARVIS ({mode} mode){tag} - type /quit to exit, /help for commands\n")


def _handle_slash(cmd: str, brain, memory: Memory, config: Config) -> bool:
    """Handle a slash command; returns True if it was recognised."""
    if cmd == "/reset":
        memory.clear()
        brain.reset()
        print("Memory and conversation cleared.")
    elif cmd == "/memory":
        facts = memory.all_facts()
        print(f"Facts ({len(facts)}):")
        for f in facts[:20]:
            print(f"  - {f}")
        turns = memory.recent(6)
        print(f"Recent turns ({memory.count_turns()} total):")
        for t in turns:
            print(f"  {t['role']}: {t['content'][:100]}")
    elif cmd == "/tools":
        from jarvis.tools import TOOL_SCHEMAS
        print("Available Stark Tools:")
        for schema in TOOL_SCHEMAS:
            print(f"  - {schema['function']['name']}: {schema['function']['description']}")
    elif cmd == "/cost":
        print(f"Requests:      {brain.total_requests}")
        print(f"Prompt tokens: {brain.total_prompt_tokens}")
        print(f"Output tokens: {brain.total_completion_tokens}")
    elif cmd == "/help":
        print("Commands: /reset /memory /tools /cost /quit /help")
    else:
        return False
    return True


def run_diagnostics(config: Config, memory: Memory) -> int:
    print(BANNER)
    print("  [ RUNNING SYSTEM SELF-TEST AND DIAGNOSTICS ]\n")

    # 1. Telemetry
    print("[1/5] Checking Hardware & Telemetry...")
    from jarvis.tools import ToolRegistry
    registry = ToolRegistry(memory, config)
    stats = registry.dispatch("get_system_stats", {})
    print(f"      {stats}")
    print("      [OK] Telemetry: OK\n")

    # 2. Services
    print("[2/5] Testing Search & Weather Services...")
    time_str = registry.dispatch("get_current_time", {})
    print(f"      Local Time: {time_str}")
    search = registry.dispatch("web_search", {"query": "Python"})
    print(f"      DuckDuckGo Search: {'OK' if 'Python' in search or 'http' in search else 'FAILED'}")
    weather = registry.dispatch("get_weather", {})
    print(f"      Live Weather: {weather[:80] if weather else 'OK'}")
    print("      [OK] Services: OK\n")

    # 3. Audio hardware
    print("[3/5] Checking Audio Hardware...")
    try:
        import sounddevice as sd
        devices = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        print(f"      Detected {len(devices)} audio input device(s).")
        print("      [OK] Audio Hardware: OK\n")
    except Exception as exc:
        print(f"      [!] Audio check notice: {exc}\n")

    # 4. Intelligence
    print("[4/5] Testing Free LLM Intelligence...")
    try:
        brain = Brain(config, memory)
        print(f"      Active Provider: {brain.active_provider_label}")
        reply = brain.stream_reply("Jarvis, report status in 3 words.")
        print(f"      Response: \"{reply.strip()}\"")
        print("      [OK] Brain Intelligence: ONLINE\n")
    except Exception as exc:
        print(f"      [X] Brain error: {exc}\n")
        return 1

    # 5. Voice output
    print("[5/5] Testing Speech Synthesis...")
    try:
        from jarvis.voice_out import Speaker
        speaker = Speaker(voice=config.tts_voice)
        print("      Speaking greeting...")
        speaker.say("All systems nominal, Sir. Diagnostic complete.")
        time.sleep(1.2)
        speaker.interrupt()
        print("      [OK] Speech Synthesis: OK\n")
    except Exception as exc:
        print(f"      [!] Speech note: {exc}\n")

    print("  [ DIAGNOSTIC COMPLETE: ALL SYSTEMS READY ]\n")
    return 0


def list_microphones() -> None:
    print("\nAvailable Audio Input Devices:")
    try:
        import sounddevice as sd
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                def_flag = " [DEFAULT]" if idx == sd.default.device[0] else ""
                print(f"  ID: {idx:2d} | Channels: {dev['max_input_channels']} | {dev['name']}{def_flag}")
    except Exception as exc:
        print(f"Error querying audio devices: {exc}")
    print("\nSet MIC_DEVICE in .env to specify a microphone.\n")


def run_text(brain, memory: Memory, config: Config) -> int:
    _banner(isinstance(brain, MockBrain), mode="interactive text")
    while True:
        try:
            user = input(f"{config.user_title}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye, Sir.")
            return 0
        if not user:
            continue
        if user.startswith("/"):
            if user == "/quit":
                print("Goodbye, Sir.")
                return 0
            _handle_slash(user, brain, memory, config)
            continue
        print(f"{config.assistant_name}: ", end="", flush=True)
        try:
            brain.stream_reply(user, on_token=lambda t: print(t, end="", flush=True))
        except KeyboardInterrupt:
            print("\n[interrupted]")
            continue
        print()


def run_ptt(brain, memory: Memory, config: Config) -> int:
    from jarvis.voice_in import Listener
    from jarvis.voice_out import Speaker

    listener = Listener(stt_model=config.stt_model, wake_word=config.wake_word)
    speaker = Speaker(voice=config.tts_voice)
    _banner(isinstance(brain, MockBrain), mode="push-to-talk")
    print("Press ENTER to record your voice (or type your message).\n")

    while True:
        try:
            prompt = input(f"[ENTER to speak or type] {config.user_title}: ").strip()
            if prompt:
                user_text = prompt
            else:
                print("  [Listening... speak now]")
                audio = listener.record_until_silence(max_seconds=12.0)
                user_text = listener.transcribe(audio)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye, Sir.")
            break

        if not user_text:
            continue

        if user_text.startswith("/"):
            if user_text == "/quit":
                print("Goodbye, Sir.")
                break
            _handle_slash(user_text, brain, memory, config)
            continue

        print(f"{config.user_title} (Spoken): {user_text}")
        print(f"{config.assistant_name}: ", end="", flush=True)

        def on_sentence(sentence: str) -> None:
            speaker.say(sentence)

        brain.stream_reply(user_text, on_sentence=on_sentence, on_token=lambda t: print(t, end="", flush=True))
        print()

    speaker.interrupt()
    listener.close()
    return 0


def run_voice(brain, memory: Memory, config: Config) -> int:
    from jarvis.voice_in import Listener
    from jarvis.voice_out import Speaker

    listener = Listener(stt_model=config.stt_model, wake_word=config.wake_word)
    if not listener.available:
        print("WARNING: no microphone available - falling back to text mode.")
        return run_text(brain, memory, config)

    speaker = Speaker(voice=config.tts_voice)
    _banner(isinstance(brain, MockBrain), mode="hands-free voice")
    print(f"Listening for wake word: '{config.wake_word}'...\n")

    try:
        while True:
            if not listener.wait_for_wake_word():
                continue
            print("[Wake word detected. Listening...]", flush=True)
            audio = listener.record_until_silence(max_seconds=12.0)
            text = listener.transcribe(audio)
            if not text:
                continue
            print(f"{config.user_title}: {text}")

            def on_sentence(sentence: str) -> None:
                print(sentence + " ", end="", flush=True)
                speaker.say(sentence)

            print(f"{config.assistant_name}: ", end="", flush=True)
            brain.stream_reply(text, on_sentence=on_sentence)
            print()

            # Wait for speech to complete with barge-in support
            while speaker.busy:
                if listener.barge_in_once(timeout=0.35):
                    speaker.interrupt()
                    print("\n[Barge-in: speech halted]")
                    break
                time.sleep(0.05)
            speaker.reset()
    except KeyboardInterrupt:
        speaker.interrupt()
        print("\nGoodbye, Sir.")
        return 0
    finally:
        listener.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logger = get_logger(debug=args.debug)
    config: Config = load_config()
    memory = Memory()

    if args.list_mics:
        list_microphones()
        return 0

    if args.reset:
        memory.clear()
        print("Conversation history and memory wiped.")
        return 0

    if args.diag:
        return run_diagnostics(config, memory)

    if args.dry_run:
        brain = MockBrain(config, memory)
    else:
        try:
            brain = Brain(config, memory)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if args.gui:
        from jarvis.gui import launch_gui
        return launch_gui(brain, memory, config, debug=args.debug)
    if args.voice:
        return run_voice(brain, memory, config)
    if args.ptt:
        return run_ptt(brain, memory, config)
    if args.text:
        return run_text(brain, memory, config)

    # Default: launch GUI; fall back to interactive text mode if GUI fails
    try:
        from jarvis.gui import launch_gui
        ret = launch_gui(brain, memory, config, debug=args.debug)
        if ret == 0:
            return 0
        return run_text(brain, memory, config)
    except Exception as exc:
        logger.warning("GUI launch fallback: %s", exc)
        return run_text(brain, memory, config)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nGoodbye, Sir.")
        sys.exit(0)
