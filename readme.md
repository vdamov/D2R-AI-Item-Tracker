# D2R Tooltip OCR via Vision LLM (OpenAI-compatible)

Batch-extract **Diablo II: Resurrected** item tooltips from screenshots using a **Vision LLM** served over an **OpenAI-compatible** API (e.g., **Groq**, OpenRouter, vLLM/LM Studio/Ollama OpenAI bridge).
No Tesseract/EasyOCR needed—the script crops the tooltip with OpenCV, sends the crop to your vision model, and concatenates all outputs separated by `---`.

---

## Features

* 🔍 Auto-detects and crops the **tooltip panel** (OpenCV).
* 🧠 Sends the crop to an **OpenAI-compatible** `/v1/chat/completions` endpoint.
* 🧾 Returns the **raw tooltip text** (line breaks preserved).
* 🧹 Optionally **removes footer UI lines** like:

  * `Shift + Left Click to Unequip`
  * `Ctrl + Left Click to Move`
* 🗂 Processes a whole folder of screenshots into **one output.txt** (`---` between items).

---

## Prerequisites

* **Python 3.9+** (3.10/3.11 OK)
* **pip** (or uv/pipx)
* A **Vision-capable model** exposed via an **OpenAI-compatible** API

  * Example: **Groq** (OpenAI-compatible endpoint)
  * Note: not all providers/models support image inputs—ensure the model you select supports images.

---

## Installation

```bash
# 1) clone your repo
git clone <your-fork-url>
cd track-d2r-items   # or your repo folder

# 2) create & activate venv (recommended)
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# 3) install python deps
pip install -r requirements.txt
```

Your `requirements.txt` should include:

```
opencv-python
numpy
Pillow
requests
python-dotenv
```

---

## Using Groq (OpenAI-compatible)

You can use **Groq** as the backend.

### 1) Create an account & get an API key

* Go to **[https://console.groq.com](https://console.groq.com)** and sign in/sign up.
* Open **API Keys** and **create a key** (free tier is available for testing).
* Copy the key (looks like `gsk_...`).

> **Note:** Groq’s model catalog changes; verify that the **model** you select supports **image inputs** via the OpenAI-compatible API. If image input isn’t supported on your chosen model, use another provider (e.g., OpenRouter) or a local OpenAI-compatible server that serves a vision model.

### 2) Configure `.env`

Create a file named `.env` in the project root:

```env
# OpenAI-compatible endpoint (Groq)
VISION_ENDPOINT=https://api.groq.com/openai/v1/chat/completions

# A model name your endpoint exposes (must support images)
# Example placeholder:
VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# Your API key from https://console.groq.com (keep it secret)
VISION_API_KEY=gsk_your_key_here
```

> If you later switch providers (OpenRouter, etc.), change `VISION_ENDPOINT` and `VISION_MODEL` accordingly.

---

## How to run

```bash
# Windows (PowerShell)
python d2r_tooltip_vision_client.py "C:\Users\<you>\Documents\Diablo II Resurrected\Screenshots" output.txt

# macOS/Linux
python d2r_tooltip_vision_client.py "/Users/<you>/Library/Application Support/Blizzard/Diablo II Resurrected/Screenshots" output.txt
```

* The script walks the folder (`.png`, `.jpg`, `.jpeg`), crops each tooltip, sends it to your Vision LLM, and writes a single **output.txt**.
* Each item block is separated by:

  ```
  ---
  ```

---

## Configuration (inside the script)

* `SYSTEM_PROMPT` / `USER_PROMPT` – steer the model to output **only** tooltip text.
* The detector (`find_tooltip_panel`) masks dark/low-sat panels and scores candidates by size/shape; tweak thresholds if your UI theme differs.
* `clean_output()` removes common footer lines (Unequip/Move).

If you find the crop is wrong (e.g., it picked the stash panel), tighten the **area range** or use the improved scoring approach (prefer \~10% of screen area, verify text density). You can also add **debug dumps** of the cropped ROI to see what’s being sent.

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
...
```

---

## Troubleshooting

* **401/403 Unauthorized**

  * Check `VISION_API_KEY` in `.env`.
  * Ensure your endpoint is correct (`VISION_ENDPOINT`) and accepts OpenAI-style **/v1/chat/completions** calls.

* **Model doesn’t accept images**

  * Pick a **vision-capable** model from your provider. Some non-vision models will reject image inputs.
  * Alternative: run a local OpenAI-compatible server that serves vision models (e.g., vLLM/LM Studio/Ollama with OpenAI bridge).

* **Empty/garbled text**

  * The crop might be wrong. Adjust HSV thresholds in `find_tooltip_panel` or temporarily disable cropping and let the model read a broader region.
  * Increase screenshot clarity (native res, neutral gamma, UI scale 100–125%).

* **Windows PowerShell policy blocks venv activation**

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

---

## Security & Privacy

* Your API key is read from `.env`. **Do not** commit `.env` to git.
* Each image (cropped tooltip) is sent to your configured endpoint; keep that in mind for privacy.

---

## License

MIT (adjust as needed).

---

### Quick Start (TL;DR)

```bash
git clone <repo>
cd track-d2r-items
python -m venv venv
.\venv\Scripts\Activate.ps1   # or: source venv/bin/activate
pip install -r requirements.txt

# .env
echo VISION_ENDPOINT=https://api.groq.com/openai/v1/chat/completions > .env
echo VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct >> .env
echo VISION_API_KEY=gsk_your_key_here >> .env

python d2r_tooltip_vision_client.py "C:\Users\<you>\Documents\Diablo II Resurrected\Screenshots" output.txt
```