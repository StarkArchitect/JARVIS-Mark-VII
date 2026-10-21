# 🦾 J.A.R.V.I.S. - Autonomous AI Assistant (Free API Edition)

> *"Just A Rather Very Intelligent System"* — A fully autonomous, voice-interactive AI assistant built in Python, operating **100% on free-tier APIs and open-source models** with zero subscription fees.

---

## 🚀 1-Click Quick Launch (Windows)

Choose any of these effortless ways to launch JARVIS without typing terminal commands:

| Method | How to Run | What it Does |
| :--- | :--- | :--- |
| **🖥️ Desktop Shortcut** | Double-click **`J.A.R.V.I.S. Mark VII`** on your Desktop | Launches the Holographic Arc Reactor HUD directly from your desktop. |
| **⚡ 1-Click Batch File** | Double-click **`run.bat`** (or `JARVIS.bat` / `start.bat`) | Auto-checks Python & dependencies, then launches the HUD GUI. |
| **🎛️ Interactive Launcher**| Run `python launcher.py` | Shows a Stark command center menu with a 5s countdown timer. |
| **💻 PowerShell Launcher**| Run `powershell .\run.ps1` | Native PowerShell launcher with parameter forwarding. |

> 💡 **Create Desktop Shortcut**: Run `create_shortcut.bat` or `powershell .\create_desktop_shortcut.ps1` to place a shortcut directly on your Windows Desktop.

---

## ⚡ Command-Line Quick Start

### 1. Run the Diagnostic Test
Verify your API keys, microphone, speakers, and tools:
```powershell
python jarvis.py --diag
```

### 2. Launch JARVIS

#### Holographic Arc Reactor HUD (Desktop GUI)
Launches the full Stark Industries holographic interface with animated Arc Reactor, real-time audio visualizer, hardware telemetry gauges, and streaming transcript:
```powershell
python jarvis.py
# or explicitly:
python main.py --gui
```
*Hotkeys in GUI*:
- `Space`: Toggle voice microphone input (Push-to-Talk)
- `Escape`: Barge-in / Silence JARVIS instantly
- `Enter`: Submit text message

#### Text Chat Mode (Interactive Terminal)
Type commands or questions in the console:
```powershell
python main.py --text
```

#### Push-to-Talk Voice Mode (Terminal)
Press Enter to speak into your microphone; Groq Whisper transcribes your voice in milliseconds:
```powershell
python main.py --ptt
```

#### Hands-Free Voice Mode (Terminal)
Listens continuously for commands:
```powershell
python main.py --voice
```

#### List Audio Input Devices (Microphones)
```powershell
python jarvis.py --list-mics
```

---

## 🧠 Brain Architecture & Free Fallback

JARVIS connects to multiple free AI providers speaking the standard OpenAI interface. If a provider hits a rate limit (`429`) or temporary outage, JARVIS automatically cascades to the next provider:

1. **Google Gemini** (`gemini-3.8-flash` / `gemini-2.0-flash`): 1,500 requests/day, fast reasoning, native tool calling.
2. **Groq Cloud** (`qwen/qwen3.8-27b` / `llama-3.3-70b`): Ultra-fast inference (<300ms) and free Whisper STT.
3. **OpenRouter** (`meta-llama/llama-3.3-70b-instruct:free`): Access to free open-source models.
4. **Mistral AI** (`mistral-small-latest`): Multilingual intelligence.
5. **Zhipu AI (Z.ai)** (`glm-4-flash` / `glm-5.3-flash`): Free GLM models.
6. **Ollama**: 100% local, offline AI with zero internet required.

For a guide on getting free keys in 60 seconds, see **[FREE_API_GUIDE.md](FREE_API_GUIDE.md)**.

---

## 🛠️ Built-in Capabilities & Tools

| Tool | Capability | Example Query |
| :--- | :--- | :--- |
| **Agenda & Planner** | Track tasks, daily plans, milestones | *"What's planned today?"* / *"Add a plan: Review code"* |
| **Morning Briefing** | Executive synthesis (Time, Weather, Health, Agenda) | *"Give me the morning briefing, Jarvis"* |
| **Temp Disk Purge** | Frees Windows temporary file bloat | *"Clean temporary files on drive C:"* |
| **Process Monitor** | Identifies top CPU or RAM consuming processes | *"What processes are lagging my PC?"* |
| **Media Controller** | Controls play/pause, next/prev tracks | *"Pause media playback"* / *"Next track"* |
| **Network Diagnostics**| Local IP, gateway ping, internet connectivity | *"Check network connection status"* |
| **File Search** | Fast recursive file search | *"Find all PDF files on my desktop"* |
| **System Telemetry** | CPU, RAM, Disk, Battery, Uptime | *"Jarvis, report system diagnostic."* |
| **Live Web Search** | Real-time DuckDuckGo searches | *"Search the web for SpaceX starship news."* |
| **Live Weather** | Real-time weather via wttr.in | *"What is the weather in Tokyo?"* |
| **Screen Vision** | High-res desktop screen capture | *"Take a screenshot of my screen."* |
| **Application Launcher** | Launches desktop apps or websites | *"Open notepad"* / *"Open github.com"* |
| **Volume Control** | Master audio mute, unmute, adjust | *"Mute system volume"* / *"Turn volume up"* |
| **Safe Shell Execution** | PowerShell command execution | *"Run dir in powershell"* |
| **Persistent Memory** | Stores facts & preferences | *"Remember my project is in D:\jarvis"* |
| **Reminders & Timers** | Background countdown alerts | *"Set a reminder to drink water in 10 minutes"* |
| **Clipboard Manager** | Reads or copies clipboard text | *"Copy my last response to clipboard"* |

---

## 🎙️ Voice Subsystem

- **Text-to-Speech (TTS)**: Microsoft Edge Neural TTS (`en-GB-RyanNeural`) for natural JARVIS speech cadence, with automatic offline fallback to Windows SAPI5 (`pyttsx3`).
- **Speech-to-Text (STT)**: Groq Whisper Large v3 Turbo (`whisper-large-v3-turbo`) transcribing audio in ~250ms.
- **Microphone Management**: RMS energy silence detection with automatic hang-time calculation.

---

## 📁 Project Structure

```
d:\jarvis\
├── jarvis.py             # Main entry point & CLI controller
├── config.py             # Central environment & model configuration
├── brain.py              # Multi-provider LLM brain router & tool execution loop
├── voice.py              # TTS and STT voice engine
├── tools.py              # Stark-grade tool handlers & OpenAI schemas
├── memory.py             # Long-term persistent memory manager
├── requirements.txt      # Python dependencies
├── .env                  # API keys & personal settings (never overwritten)
├── FREE_API_GUIDE.md     # Detailed guide for getting 100% free API keys
└── data/                 # Local persistent storage (memory, notes, screenshots)
```
