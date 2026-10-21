# 🌟 The Ultimate Guide to Free AI Models & API Keys for J.A.R.V.I.S.

This guide provides step-by-step instructions on how to get **100% free** API keys for every model provider supported by JARVIS. **Zero credit card required, zero dollars spent.**

---

## 📋 Free Providers Overview

| Provider | Best Free Model | Free Quota | Speed | Credit Card? |
| :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini-3.8-flash` / `gemini-2.0-flash` | **1,500 requests/day, 15 RPM** | ⚡ Blazing | **NO** |
| **Groq Cloud** | `qwen/qwen3.8-27b` & `whisper-large-v3-turbo` | **14,400 requests/day, 30 RPM** | ⚡⚡ Ultra-fast (<0.3s) | **NO** |
| **OpenRouter** | `meta-llama/llama-3.3-70b-instruct:free` | Dozens of `:free` models | Fast | **NO** |
| **Mistral AI** | `mistral-small-latest` | Free Experimentation tier | Fast | **NO** |
| **Zhipu AI (Z.ai)** | `glm-4-flash` / `glm-5.3-flash` | Free tier on BigModel | Fast | **NO** |
| **Ollama** | `llama3.2:latest`, `qwen2.5:7b` | **Unlimited (Runs 100% Offline)** | Local Hardware | **NO** |
| **Picovoice** | Wake word (`"jarvis"`) | Free Forever (3 devices) | Real-time | **NO** |

---

## 1. Google Gemini API (Recommended Primary Brain)

Google AI Studio provides generous free access to Gemini models with native function/tool calling.

### How to Get Your Free Key:
1. Open your browser and navigate to **[Google AI Studio](https://aistudio.google.com/)**.
2. Sign in with your standard Google Account.
3. Click the blue **"Get API key"** button in the top-left or top-right corner.
4. Click **"Create API key in new project"** (or select an existing Google Cloud project).
5. Copy the generated key (starts with `AIzaSy...` or `AQ...`).
6. Paste it into your `.env` file:
   ```env
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-3.8-flash
   ```

---

## 2. Groq Cloud (Ultra-Fast LLM & Free Whisper STT)

Groq provides specialized LPU hardware running open-source models at 500+ tokens/second, plus free Whisper speech-to-text.

### How to Get Your Free Key:
1. Visit **[Groq Console](https://console.groq.com/)**.
2. Sign up or log in using GitHub or Google.
3. In the left navigation menu, click **"API Keys"**.
4. Click **"Create API Key"**, give it a name (e.g. `Jarvis`), and click **"Submit"**.
5. Copy your key (starts with `gsk_...`).
6. Paste it into your `.env` file:
   ```env
   GROQ_API_KEY=your_key_here
   GROQ_MODEL=qwen/qwen3.8-27b
   STT_MODEL=whisper-large-v3-turbo
   ```

> [!TIP]
> Groq's Whisper API is used by JARVIS for voice input. Having `GROQ_API_KEY` active gives you instant voice transcription.

---

## 3. OpenRouter (Access Hundreds of Free Open-Source Models)

OpenRouter aggregates models from Meta, Mistral, Qwen, DeepSeek, and Google, offering completely free `:free` endpoints.

### How to Get Your Free Key:
1. Go to **[OpenRouter.ai](https://openrouter.ai/)**.
2. Click **"Sign In"** (top right) using Google, Discord, or MetaMask.
3. Click on your profile icon and select **"Keys"** (or go to `https://openrouter.ai/keys`).
4. Click **"Create Key"**, name it `Jarvis`, and set credit limit to `$0` (free).
5. Copy your key (starts with `sk-or-v1-...`).
6. Paste into your `.env`:
   ```env
   OPENROUTER_API_KEY=your_key_here
   OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
   ```

Popular free models on OpenRouter (use any with `:free`):
- `meta-llama/llama-3.3-70b-instruct:free`
- `deepseek/deepseek-r1:free`
- `google/gemini-2.0-flash-exp:free`
- `mistralai/mistral-7b-instruct:free`

---

## 4. Mistral AI (La Plateforme)

Mistral provides European multilingual intelligence with free access for experimentation.

### How to Get Your Free Key:
1. Go to **[Mistral AI Console](https://console.mistral.ai/)**.
2. Sign up with Google, GitHub, or email.
3. Go to **"API Keys"** in the sidebar.
4. Click **"Create new key"**, copy the secret key.
5. Paste into `.env`:
   ```env
   MISTRAL_API_KEY=your_key_here
   MISTRAL_MODEL=mistral-small-latest
   ```

---

## 5. Zhipu AI / Z.ai (GLM Models)

Zhipu AI offers the GLM series (`glm-4-flash`, `glm-5.3-flash`), free for developers.

### How to Get Your Free Key:
1. Go to **[BigModel.cn](https://bigmodel.cn/)** or **[Z.ai](https://z.ai/)**.
2. Register an account and navigate to the developer API console.
3. Generate an API Key under **"API Keys" / "API 密钥"**.
4. Paste into `.env`:
   ```env
   ZAI_API_KEY=your_key_here
   ZAI_MODEL=glm-4-flash
   ```

---

## 6. Picovoice Porcupine (Hands-Free Wake Word "Jarvis")

To let JARVIS continuously listen in the background and activate when you say *"Jarvis"*, Picovoice provides a free personal tier.

### How to Get Your Free AccessKey:
1. Navigate to **[Picovoice Console](https://console.picovoice.ai/)**.
2. Sign up with your email, Google, or GitHub.
3. Your **AccessKey** will be displayed on the main dashboard.
4. Copy the AccessKey and paste into `.env`:
   ```env
   PICOVOICE_ACCESS_KEY=your_access_key_here
   WAKE_WORD=jarvis
   ```

> [!NOTE]
> If `PICOVOICE_ACCESS_KEY` is left blank, JARVIS will seamlessly use Push-to-Talk (`--ptt`) or continuous voice listening mode (`--voice`).

---

## 7. Ollama (100% Offline, Zero Internet, Unlimited Free AI)

If you have a modern PC and want JARVIS to work completely offline without any API keys or internet connection:

### Setup:
1. Download Ollama for Windows from **[ollama.com](https://ollama.com/download)**.
2. Install and launch Ollama.
3. Open PowerShell or Command Prompt and download a fast model:
   ```powershell
   ollama run llama3.2:latest
   ```
4. Ollama automatically runs a local OpenAI-compatible server at `http://localhost:11434/v1`.
5. In `.env`, add `ollama` to your `PROVIDER_ORDER`:
   ```env
   PROVIDER_ORDER=gemini,groq,openrouter,mistral,zai,ollama
   OLLAMA_MODEL=llama3.2:latest
   ```

---

## 8. Summary of Your `.env` Configuration

Here is how your `.env` looks when fully configured:

```env
# ============ IDENTITY ============
ASSISTANT_NAME=Jarvis
USER_TITLE=Sir
WAKE_WORD=jarvis

# ============ FREE LLM KEYS ============
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
MISTRAL_API_KEY=your_mistral_key
ZAI_API_KEY=your_zai_key
PICOVOICE_ACCESS_KEY=your_picovoice_key

# Provider priority order (auto-fallback if one fails or rate limits)
PROVIDER_ORDER=gemini,groq,openrouter,mistral,zai,ollama

# Optional model overrides
GEMINI_MODEL=gemini-3.8-flash
GROQ_MODEL=qwen/qwen3.8-27b
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free

# ============ VOICE SETTINGS ============
TTS_VOICE=en-GB-RyanNeural
TTS_RATE=+8%
STT_LANGUAGE=en
STT_MODEL=whisper-large-v3-turbo

# ============ BEHAVIOUR ============
HOME_CITY=
MAX_HISTORY_TURNS=12
TEMPERATURE=0.55
MAX_TOKENS=650
VERBOSE=false
```

Enjoy your fully autonomous, zero-cost J.A.R.V.I.S. assistant!
