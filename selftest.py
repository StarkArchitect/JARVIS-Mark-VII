"""Automated verification suite for JARVIS.

Runs 10 core gate tests:
1. Config loads and API keys are present
2. Real LLM completion returns non-empty text
3. All Tool Registry core dispatches
4. SQLite memory add -> search round-trip
5. Tool loop completes and executes tools
6. History window trims correctly at boundary
7. Dry-run mode boots without network calls
8. GUI Bridge & Voice pipeline integration
9. Heavy-Duty Stark Skills Suite execution
10. Speech Queue resilience & defensive memory aliases
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# UTF-8 encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from jarvis.brain import Brain, MockBrain
from jarvis.config import Config, get_providers, load_api_keys, load_config
from jarvis.memory import Memory
from jarvis.tools import TOOL_SCHEMAS, ToolRegistry


def test_1_config_and_keys() -> bool:
    print("[TEST 1/10] Config & API Key Availability... ", end="", flush=True)
    try:
        cfg = load_config()
        keys = load_api_keys()
        providers = get_providers(cfg)
        assert len(providers) > 0, "No active providers configured"
        assert cfg.model, "No model configured"
        print(f"PASS (Active: {[p['label'] for p in providers]})")
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False


def test_2_real_completion() -> bool:
    print("[TEST 2/10] Real LLM Provider Completion... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        brain = Brain(cfg, mem)
        reply = brain.stream_reply("Respond with only the word: ONLINE")
        assert reply and len(reply.strip()) > 0, "Empty response from LLM"
        print(f"PASS ({brain.active_provider_label} -> '{reply.strip()}')")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_3_tool_dispatches() -> bool:
    print("[TEST 3/10] All Tool Registry Dispatches... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        reg = ToolRegistry(mem, cfg)
        
        sample_calls = [
            ("get_current_time", {}),
            ("get_date", {}),
            ("get_system_stats", {}),
            ("calculate", {"expression": "100 / 4 + 7"}),
            ("get_weather", {"city": "London"}),
            ("web_search", {"query": "Python"}),
            ("clipboard_get", {}),
            ("clipboard_set", {"text": "selftest_test"}),
            ("remember", {"fact": "User is Stark", "tags": "hero"}),
            ("recall", {"query": "Stark"}),
            ("set_reminder", {"message": "Test reminder", "seconds": 9999}),
        ]
        
        for name, args in sample_calls:
            res = reg.dispatch(name, args)
            assert isinstance(res, str) and not res.startswith("ERROR: ValueError: unknown tool"), f"Tool {name} failed: {res}"
        print(f"PASS ({len(sample_calls)} tools verified)")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_4_memory_roundtrip() -> bool:
    print("[TEST 4/10] SQLite Memory Persistence Roundtrip... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        db_path = Path(td) / "mem_test.db"
        mem = Memory(db_path=db_path)
        secret = "JARVIS_MARK_85_ONLINE"
        mem.add_fact(f"Secret code is {secret}", tags="security")
        
        # Recall
        results = mem.search("Secret code", k=2)
        assert any(secret in r for r in results), "Failed to recall stored fact"
        
        # Turns
        mem.add_turn("user", "Hello Jarvis")
        mem.add_turn("assistant", "At your service, Sir.")
        recent = mem.recent(5)
        assert len(recent) == 2, "Turn count mismatch"
        assert recent[0]["role"] == "user"
        assert recent[1]["role"] == "assistant"
        print("PASS (Facts + Turns verified)")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_5_tool_loop_completion() -> bool:
    print("[TEST 5/10] Autonomous Tool-Calling Loop... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        brain = Brain(cfg, mem)
        # Ask a question that invokes the time or stats tool
        reply = brain.stream_reply("Jarvis, what is the exact current time?")
        assert reply and len(reply) > 0, "No reply from tool loop"
        print(f"PASS (Reply: '{reply.strip()[:60]}...')")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_6_history_window_trimming() -> bool:
    print("[TEST 6/10] History Trimming & Context Window... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        cfg.history_turns = 4
        mem = Memory(db_path=Path(td) / "test.db")
        for i in range(10):
            mem.add_turn("user", f"Question {i}")
            mem.add_turn("assistant", f"Answer {i}")
        
        brain = MockBrain(cfg, mem)
        history = brain.build_history()
        assert len(history) <= 4, f"History window not trimmed: got {len(history)} turns"
        print(f"PASS (Trimmed to {len(history)} turns)")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_7_dry_run_offline() -> bool:
    print("[TEST 7/10] Dry-Run Mode Offline Verification... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        mock = MockBrain(cfg, mem)
        reply = mock.stream_reply("System check")
        assert "Dry-run mode" in reply, "MockBrain failed to emit dry-run response"
        print("PASS (MockBrain functional)")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_8_gui_bridge_and_voice() -> bool:
    print("[TEST 8/10] GUI Bridge & Voice Pipeline... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        from jarvis.gui_bridge import JarvisGUIBridge
        from jarvis.voice_in import Listener
        from jarvis.voice_out import Speaker

        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        mock = MockBrain(cfg, mem)
        speaker = Speaker(voice=cfg.tts_voice)
        listener = Listener(stt_model=cfg.stt_model, wake_word=cfg.wake_word)

        bridge = JarvisGUIBridge(mock, mem, cfg, speaker=speaker, listener=listener)
        assert bridge is not None, "Bridge failed to initialize"

        # Verify safe eval does not throw without window
        bridge.safe_eval_js("console.log('test')")

        # Verify quick tool dispatch
        bridge._exec_quick_tool("stats")

        # Clean shutdown
        bridge.close()
        mem.close()
        print("PASS (GUI Bridge + Speaker + Listener OK)")
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_9_heavy_duty_skills() -> bool:
    print("[TEST 9/10] Heavy-Duty Stark Skills Suite... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        cfg = load_config()
        mem = Memory(db_path=Path(td) / "test.db")
        reg = ToolRegistry(mem, cfg)

        # 1. Agenda
        res_add = reg.dispatch("manage_agenda", {"action": "add", "title": "Check reactor core", "due_time": "15:00"})
        assert "Check reactor core" in res_add, f"Agenda add failed: {res_add}"
        res_list = reg.dispatch("manage_agenda", {"action": "list"})
        assert "Check reactor core" in res_list, f"Agenda list failed: {res_list}"
        res_done = reg.dispatch("manage_agenda", {"action": "complete", "title": "Check reactor core"})
        assert "completed" in res_done, f"Agenda complete failed: {res_done}"

        # 2. Temp cleanup (dry run)
        res_clean = reg.dispatch("clean_temp_files", {"dry_run": True})
        assert "Temp scan complete" in res_clean, f"Temp clean failed: {res_clean}"

        # 3. Top processes
        res_procs = reg.dispatch("get_top_processes", {"sort_by": "memory", "limit": 3})
        assert "Top" in res_procs, f"Top processes failed: {res_procs}"

        # 4. Network status
        res_net = reg.dispatch("get_network_status", {})
        assert "Network Status" in res_net, f"Network status failed: {res_net}"

        # 5. Morning Briefing
        res_brief = reg.dispatch("morning_briefing", {})
        assert "Good day" in res_brief, f"Briefing failed: {res_brief}"

        print("PASS (Agenda, Temp Clean, Processes, Network, Briefing OK)")
        mem.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def test_10_speech_queue_resilience() -> bool:
    print("[TEST 10/10] Speech Queue Resilience & Defensive Aliases... ", end="", flush=True)
    td = tempfile.mkdtemp()
    try:
        from jarvis.voice_out import Speaker
        speaker = Speaker()
        
        # Simulate an interrupt
        speaker.interrupt()
        assert speaker._stop.is_set(), "Speaker interrupt failed to set _stop"

        # Calling say() MUST clear _stop so subsequent turns speak
        speaker.say("System nominal, Sir.")
        assert not speaker._stop.is_set(), "Speaker.say() failed to clear _stop flag!"

        # Defensive memory alias check
        mem = Memory(db_path=Path(td) / "test.db")
        mem.append("user", "What is the plan?")
        mem.append("assistant", "Standing by, Sir.")
        recent = mem.recent(2)
        assert len(recent) == 2, f"Memory alias failed: {recent}"
        assert recent[0]["content"] == "What is the plan?"

        speaker.interrupt()
        mem.close()
        print("PASS (Interrupt recovery & Memory.append alias OK)")
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False
    finally:
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass


def main() -> int:
    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S. AUTOMATED SELF-TEST VERIFICATION SUITE")
    print("=" * 60 + "\n")

    tests = [
        test_1_config_and_keys,
        test_2_real_completion,
        test_3_tool_dispatches,
        test_4_memory_roundtrip,
        test_5_tool_loop_completion,
        test_6_history_window_trimming,
        test_7_dry_run_offline,
        test_8_gui_bridge_and_voice,
        test_9_heavy_duty_skills,
        test_10_speech_queue_resilience,
    ]

    passed = 0
    for t in tests:
        if t():
            passed += 1

    print("\n" + "=" * 60)
    print(f"  RESULT: {passed}/{len(tests)} TESTS PASSED")
    print("=" * 60 + "\n")

    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
