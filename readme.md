# D2R Tooltip OCR via Vision LLM (OpenAI-compatible)

> ⚠️ **AI-generated project notice**: this README and script were written with help from an AI assistant. If something looks *too polished*, it probably is—try it anyway. 😉

Batch-extract **Diablo II: Resurrected** item tooltips from screenshots using a **Vision LLM** behind an **OpenAI-compatible** API (OpenAI, Groq, OpenRouter, LM Studio/Ollama OpenAI bridge, etc.).
No Tesseract/EasyOCR needed—the script sends each screenshot to your vision model and concatenates all outputs separated by `---`.

---

## What it does

* 🧠 Calls an **OpenAI-compatible** `POST /v1/chat/completions` with the screenshot encoded as a **base64 data URI**.
* 🧾 Returns the **raw tooltip text** (line breaks preserved).
* 🧹 Removes common footer UI lines:

  * `Shift + Left Click to Unequip`
  * `Ctrl + Left Click to Move`
  * `Shift + Left Click to Equip`
  * `Hold Shift to Compare`
  * `Left Click to Cast`
* 🧯 Prompted to **exclude the “other set items” list** at the bottom of set items.
* 🚦 Built-in **rate limiter** to avoid 429s (RPM & jitter configurable).
* 🔁 Processes a whole folder into **one `output.txt`** (`---` between items) with a progress bar.

> Note: this version sends the **full screenshot** to the model (no local cropping). Most vision models read the tooltip cleanly; the prompt asks to ignore non-tooltip text.

---

## Prerequisites

* [**Python 3.9+** (3.10/3.11 OK)](https://www.python.org/downloads/)
* [**pip** (or uv/pipx)](https://pip.pypa.io/en/stable/installation/)
* A **vision-capable** model exposed via an **OpenAI-compatible** API
  ([OpenAI “GPT-4o”](https://platform.openai.com/docs/models), [Groq vision models](https://console.groq.com/docs/vision), [OpenRouter](https://openrouter.ai/models), or a local OpenAI bridge).

---

## Installation

```bash
# 1) clone
git clone <your-fork-url>
cd D2R-AI-Item-Tracker

# 2) virtual env (recommended)
python -m venv venv
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS/Linux
source venv/bin/activate

# 3) deps
pip install -r requirements.txt
```

`requirements.txt`:

```
opencv-python
numpy
Pillow
requests
python-dotenv
tqdm
```

---

## Configure `.env`

Create a `.env` in the repo root. You can point it at **OpenAI**, **Groq**, or another OpenAI-compatible router.

### OpenAI example

```env
VISION_ENDPOINT=https://api.openai.com/v1/chat/completions
VISION_MODEL=gpt-4o
VISION_API_KEY=sk-your-openai-key

# Optional tuning
MAX_WORKERS=1          # keep 1 for strict RPM limits
MAX_RETRIES=3
RETRY_DELAY=10
REQUEST_TIMEOUT=120

# Rate limiting (helps avoid 429s)
RATE_LIMIT_RPM=30      # requests per minute
RATE_JITTER_MS=200     # small random delay to avoid bursts
```

### Groq example

Groq provides **free access** to their hosted LLaMA vision models, but you’ll need to log in with a **Google account** (no other login methods supported at the moment).

1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign in with your Google account
3. Open the **API Keys** section in the left menu
4. Click **Create Key** — you’ll get a key that looks like `gsk_...`

Add that key to your `.env` file:

```env
VISION_ENDPOINT=https://api.groq.com/openai/v1/chat/completions
VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
VISION_API_KEY=gsk_your_key_here
MAX_WORKERS=1
RATE_LIMIT_RPM=30
RATE_JITTER_MS=200
```

> **Note:** Groq’s free tier has limits (around 30 requests/minute). Keep `MAX_WORKERS=1` and leave rate limiting enabled in the script to avoid 429 errors.

---

## How to run

```bash
# Windows (PowerShell)
python d2r_tooltip_vision_client.py "C:\Users\<you>\Documents\Diablo II Resurrected\Screenshots" output.txt

# macOS/Linux
python d2r_tooltip_vision_client.py "/Users/<you>/Library/Application Support/Blizzard/Diablo II Resurrected/Screenshots" output.txt
```

* The script scans the folder for `.png/.jpg/.jpeg`, sends each screenshot to your Vision LLM, and writes **`output.txt`**.
* Each item block is separated by:

```
---
```

---

## Environment knobs (mapped to code)

* `VISION_ENDPOINT` – OpenAI-compatible `/v1/chat/completions`
* `VISION_MODEL` – model id exposed by your endpoint (must support **images**)
* `VISION_API_KEY` – your key/token
* `MAX_WORKERS` – concurrent images (keep **1** for strict RPMs)
* `MAX_RETRIES` – request retries on network/5xx
* `RETRY_DELAY` – backoff base (seconds)
* `REQUEST_TIMEOUT` – per request timeout (seconds)
* `RATE_LIMIT_RPM` – requests per minute (global, thread-safe)
* `RATE_JITTER_MS` – small random delay added after each request

---

## Example output (snippet)

```
THUNDERSTROKE
MATRIARCHAL JAVELIN
THROW DAMAGE: 103 TO 195
ONE-HAND DAMAGE: 88 TO 159
QUANTITY: 120 OF 120
(AMAZON ONLY)
REQUIRED DEXTERITY: 151
REQUIRED STRENGTH: 107
REQUIRED LEVEL: 69

JAVELIN CLASS - VERY FAST ATTACK SPEED
20% CHANCE TO CAST LEVEL 14 LIGHTNING ON STRIKING
+4 TO JAVELIN AND SPEAR SKILLS (AMAZON ONLY)
+15% INCREASED ATTACK SPEED
+196% ENHANCED DAMAGE
ADDS 1-511 LIGHTNING DAMAGE
-15% TO ENEMY LIGHTNING RESISTANCE
+3 TO LIGHTNING BOLT (AMAZON ONLY)

SHIFT + LEFT CLICK TO UNEQUIP
CTRL + LEFT CLICK TO MOVE
---
ENIGMA
Scarab Husk
'Jah Ith Ber'
Defense: 1302
Durability: 30 of 30
Required Strength: 95
Required Level: 65
+2 to all Skills
+45% Faster Run/Walk
+1 to Teleport
+15% Enhanced Defense
+756 Defense
+65 to Strength [based on character level]
Increase Maximum Life 5%
Physical Damage Received Reduced by 8%
+14 Life After Each Kill
+15% Damage Taken Goes to Mana
87% Better Chance of Getting Magic Items [based on character level]
Increase Maximum Durability 10%
Socketed (3)
```

---

## Troubleshooting

* **401/403 Unauthorized**
  Check `VISION_API_KEY`, `VISION_ENDPOINT`, and that your model supports **image inputs**.

* **429 Too Many Requests**
  Lower `MAX_WORKERS` (prefer `1`). Set `RATE_LIMIT_RPM` to your provider’s limit and keep `RATE_JITTER_MS` > 0.

* **Empty text**
  Some models struggle with very small UI. Use native resolution screenshots and default UI scale. Try another vision model.

* **PowerShell policy blocks venv activate**

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

---

## Security & Privacy

* `.env` holds your API key. **Do not commit it.**
* Screenshots are sent to your configured endpoint—treat accordingly.

---

## License

MIT License
Copyright (c) 2025 Vladimir Damov

(see `LICENSE` for full text)

---

### Quick Start (TL;DR)

```bash
git clone <repo>
cd D2R-AI-Item-Tracker
python -m venv venv
.\venv\Scripts\Activate.ps1   # or: source venv/bin/activate
pip install -r requirements.txt

# .env (Groq example)
echo VISION_ENDPOINT=https://api.groq.com/openai/v1/chat/completions > .env
echo VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct >> .env
echo VISION_API_KEY=gsk_your_key_here >> .env
echo MAX_WORKERS=1 >> .env
echo RATE_LIMIT_RPM=30 >> .env
echo RATE_JITTER_MS=200 >> .env

python d2r_tooltip_vision_client.py "C:\Users\<you>\Documents\Diablo II Resurrected\Screenshots" output.txt
```
