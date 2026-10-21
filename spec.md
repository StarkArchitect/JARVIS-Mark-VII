# JARVIS — Local Desktop AI Assistant — Specification

## Goal
A fully local desktop AI assistant. Listens, thinks, acts, speaks.
Runs offline for voice I/O; uses OpenRouter (OpenAI-compatible) for the brain.

## Environment
- Python 3.11+
- Windows / macOS / Linux via platform checks
- `OPENROUTER_API_KEY` read from existing `.env` (never rewritten)
- OpenRouter base: `https://openrouter.ai/api/v1`
- Default model: `anthropic/claude-sonnet-latest` (config-driven)
- Free-model swap documented in README (`openai/gpt-oss-120b:free`)

## Modes
| Flag       | Behavior |
|------------|----------|
| `--text`   | default; typed input, streamed stdout replies |
| `--voice`  | wake word -> listen -> think -> speak; falls back to text if no mic |
| `--reset`  | wipe conversation history and exit |
| `--dry-run`| no API calls; mocked brain; plumbing testable offline |
| `--debug`  | DEBUG-level log of raw requests/responses and timings |

## Conversation
- Streamed token-by-token to stdout; complete sentences also emitted via callback (voice).
- Rolling window of `config.history_turns` user/assistant pairs; dropped turns summarised and kept as a single summary note.
- Text-mode slash commands: `/reset`, `/memory`, `/tools`, `/cost`, `/quit`.

## Tool loop
- OpenAI function-calling format (`TOOL_SCHEMAS`).
- Loop: send schemas -> execute requested calls (multiple per turn supported) -> append tool results -> repeat.
- Hard cap `config.max_tool_iters` (default 6); on cap, force a final no-tools answer.
- Tool exceptions are caught and returned as the tool result string — never crash the loop.
- `confirm_shell` gates `run_shell_command` behind y/n unless config disables it.
- File tools resolve paths and refuse to escape `allow_paths`.

## Memory
- SQLite, WAL mode. Tables: `facts`, `turns`.
- `facts`: durable user facts; top-k keyword-overlap recall injected into system prompt each turn.
- Explicit `remember(fact)` and `recall(query)` tools.
- `/memory` prints stored facts and recent turns.

## Voice
- **Wake word:** continuous low-cost VAD loop; on word match, requires a following utterance (no double-fire).
- **VAD:** RMS energy against a calibrated noise floor (first ~1s ambient). End-of-speech after ~800 ms of silence.
- **Audio callback:** never blocks — frames pushed onto a `queue.Queue`.
- **TTS:** sentence-chunked. As soon as the brain emits a complete sentence, a worker thread starts speaking it while generation continues.
- **Barge-in:** saying "stop" or pressing space calls `Speaker.interrupt()`.
- **No microphone:** warn once, fall back to text mode, no crash.

## Persona
Calm, dry-witted, competent butler. Concise. Occasional "sir".
Never rambles, never restates the question, says "I don't know" rather than inventing.
Lives in `jarvis/persona.py` for easy editing.

## Robustness
- Exponential backoff with jitter on HTTP 429 / 5xx; max 4 attempts.
- Clear human error if `OPENROUTER_API_KEY` is missing or empty.
- Every subprocess call gets a timeout.
- `Ctrl+C` saves history and exits cleanly.
- Rotating log at `./jarvis/jarvis.log`.
- Token usage logged per response.

## Tools (final set)
get_current_time, get_date, open_application, run_shell_command,
read_file, write_file, list_directory, web_search (DuckDuckGo HTML),
calculate (ast-whitelisted), get_system_stats (psutil), set_volume,
take_screenshot, clipboard_get, clipboard_set, remember, recall.

## File manifest
```
jarvis/
  .env                  <- user's, untouched
  main.py               <- arg parsing, mode dispatch, Ctrl+C
  config.yaml           <- user-editable settings
  requirements.txt
  README.md
  spec.md               <- this file
  PROGRESS.md           <- live checklist
  selftest.py           <- Phase 4 verification
  jarvis/
    __init__.py
    config.py
    brain.py
    tools.py
    memory.py
    voice_in.py
    voice_out.py
    persona.py
    utils.py
```

## Build order
- Phase 0: spec.md + PROGRESS.md
- Phase 1: config, utils, memory, brain, tools, main -> `python main.py --text` works with one tool (`get_current_time`)
- Phase 2: remaining tools; wire long-term memory into prompt
- Phase 3: voice_in / voice_out and `--voice` mode
- Phase 4: selftest.py, README.md, polish, `--debug` logging

## Verification (`selftest.py`)
Prints PASS/FAIL per line; exits nonzero on any failure; < 60 s total.
1. config loads and OPENROUTER_API_KEY is non-empty
2. one real completion returns non-empty text
3. every tool dispatches with sample args without raising
4. memory add -> search round-trips
5. tool loop completes when a tool is forced
6. history window trims correctly at the boundary
7. `--dry-run` boots without touching the network
