# ULTRON

Personal desktop assistant for Windows. Device actions run on a local model. General and web questions can use
free cloud APIs; those requests may include earlier local model replies, which can summarize device information.

| Kind of request | Who answers | Fallback |
|---|---|---|
| Files, apps, system info (anything on this PC) | Local Qwen3 1.7B via Ollama | – |
| General questions, explanations, coding help | Groq | Gemini → local |
| Current info / web | Gemini with Google Search | Groq + DuckDuckGo → local + DuckDuckGo |
| Speech-to-text | Local Whisper (always) | – |

## Setup

Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For microphone input and spoken replies, also install the optional voice packages:

```bash
pip install -r requirements-voice.txt
```

Ollama: install from https://ollama.com, then `ollama pull qwen3:1.7b`. Local Qwen runs with medium reasoning
effort enabled; answers may take longer than when thinking is disabled.

Free API keys (optional, but needed for cloud answers):
- Groq: https://console.groq.com/keys
- Gemini: https://aistudio.google.com/apikey

Paste them in **Settings → AI**. They're stored in Windows Credential Manager (not in any file).
`GROQ_API_KEY` / `GEMINI_API_KEY` environment variables also work.

Run:

```bash
python main.py
```

First run downloads a small embedding model for routing (~130 MB, `BAAI/bge-small-en-v1.5`). Until it's
there, or if it can't download, routing uses keyword rules only. First voice use downloads Whisper base (~150 MB).
For spoken replies pick a Piper voice `.onnx` (with its `.onnx.json`) in Settings → Voice & data.
Deep male voices that suit ULTRON: `en_US-ryan-high` or `en_GB-alan-medium` (from huggingface.co/rhasspy/piper-voices).

## Voice mode

**Voice mode** button in the header, or **Ctrl+Alt+Space** from anywhere (even with the window hidden).
A full-window core shows what ULTRON is doing: listening, thinking or speaking. It pulses with your voice and its own.

- Just talk. It stops recording after about 1.8 seconds of silence, transcribes locally (Whisper), answers, says the
  reply out loud (Piper), then listens again.
- Hands-free listening calibrates to room noise on each turn. Adjust **Hands-free mic sensitivity** in Settings →
  Voice & data if your voice is quiet or the room is noisy. ULTRON waits longer through pauses and retries brief
  audio interruptions.
- Same routing, privacy and approvals as typed chat. Approval dialogs still pop up, so nothing is sent on voice alone.
- Say "stop", "goodbye" or "exit voice mode", or press **Esc**, to leave. **Space** pauses/resumes.
- Each voice session starts a new chat, so you can read it later in the sidebar.
- Off in low-memory mode.

Voice effect (Settings → General): **ULTRON synthetic** (default) makes the Piper voice a bit deeper and slower
with a faint metallic edge and short echo. Choose **None** for the plain voice.
Core colour: crimson, ice blue or gold (same tab).

## Running in the background

- Closing the window keeps ULTRON in the system tray (turn off in Settings → General → "Keep running in the background").
  Scheduled voice messages still go out while it's in the tray.
- Tray icon: click to open; right-click for Open / Voice mode / Quit.
- **Ctrl+Alt+U** brings the window back from anywhere.
- Settings → General → **Start with Windows** starts it in the tray at login (adds a `pythonw main.py --background`
  entry under `HKCU\...\Run`; untick to remove it).
- Only one ULTRON runs at a time; starting it again just shows the existing window.
- To fully exit: tray → Quit.

## Who writes messages

Emails and voice-message text are written by the cloud models (Groq → Gemini), because the local 1.7B model
writes poorly. The cloud gets **only what you typed in that message**, with email addresses and phone numbers
removed, plus "write an email/voice message". It never gets contacts, numbers, file contents or earlier device
turns. If the chat has used file/system content, or cloud AI is off, the text is written locally instead.
Set "Your name" in Settings → Email & contacts so messages are signed properly.

## WhatsApp voice messages

"Send Rahul a voice message saying I'll be 15 minutes late"
"Voice message Priya at 6 pm: the meeting moved to 7"
"Record a voice message for Rahul" (your own voice, via a Record / Stop / Play dialog)

ULTRON makes a real WhatsApp-style voice note (OGG Opus), opens Rahul's chat (WhatsApp Desktop, or wa.me in the
browser) and copies the voice note. **You press Ctrl+V, then Send.** ULTRON never logs into or automates your
WhatsApp account, so there's no ban risk, and sending always stays with you.

- ULTRON's own voice needs a Piper voice (Settings → Voice & data).
- Save WhatsApp numbers in Settings → Email & contacts (10-digit numbers get the default country code, 91).
- Scheduled messages show in the right panel. When one is due, ULTRON opens the chat, copies the note and shows a
  Windows notification. ULTRON has to be running; anything missed while it was closed is prepared at the next start.
- "What's scheduled?" / "cancel scheduled message 3".
- Voice notes are kept in `%LOCALAPPDATA%\ULTRON\voice_notes\`.

## Email

Settings → Email → "When I ask for an email":
- **Open a Gmail draft (default, no setup):** ULTRON writes the email and opens Gmail's compose window in
  Chrome with To/Subject/Body filled in. You press Send, or say "send it" and ULTRON presses Ctrl+Enter
  after you approve.
- **Send directly:** ULTRON writes it, shows it in an approval dialog where you can edit To, Subject and Body,
  and sends exactly what you approved. Needs a Gmail app password: turn on 2-Step Verification, create one at
  myaccount.google.com/apppasswords, and paste it with your Gmail address in Settings → Email.
  Gmail allows about 500 emails a day this way.

Save contacts in the same tab so "mail Rahul" works. Email requests always run on the local model
(contacts and emails are personal data), so the draft wording comes from Qwen; fix it in the dialog if needed.

## Applications and keyboard

ULTRON can launch built-in apps and other installed applications by executable name or full `.exe` path. If an
app name cannot be resolved, give ULTRON its executable path. Opening an unregistered app asks for approval. It
can type into any app window; typing into an unregistered app asks you to review the text first.
- Typing plain text into a built-in app: no approval.
- Anything that can send or submit asks first: every key or shortcut (Enter, Ctrl+Enter, Ctrl+S, ...) and
  any text containing line breaks (a line break is an Enter press). You can edit the text in the dialog.
- If the chat has read your files, typing into Chrome also asks (some sites save what you type without Enter).
- The Windows key is never used. Typing stops if the app loses focus, so clicking elsewhere stops it.
- Line breaks are fine in VS Code and Notepad (they're just new lines there). For VS Code, ULTRON first presses
  Ctrl+1 to put the cursor in the editor, so the text can't land in the terminal or chat panel. If you've changed
  VS Code's Ctrl+1 shortcut, change it back or this won't work.

## Privacy rules (how it's enforced)

- **Cloud agents have no device tools.** The chat agent has no tools at all; the web agent only has web search /
  page reading. They can't touch files or apps even if routing guesses wrong.
- **Cloud history can include local model replies.** Groq/Gemini receive general/web turns and the final text the
  local model replied with. A local reply may summarize device information. They do not receive local user prompts,
  application-generated errors, or raw tool/context results.
- **Device signals always win.** Paths, file names, "my files/laptop/...", open/close, RAM/CPU/battery etc. → local.
- **A request involving the device stays local.** Later general/web questions can use cloud, with only earlier local
  model reply text included from device turns.
- **`/local` at the start of a message** forces local. The "Allow cloud AI" checkbox turns cloud off entirely.
- Each reply shows who answered ("stayed on this PC" or "Cloud · Groq …") and any fallback reason.

Note: Gemini's free tier may use prompts to improve Google's products. Only cloud-routed messages go there.
With Gemini's built-in Google Search the search queries are made on Google's side, so ULTRON shows
"Searching the web with Gemini" rather than the exact query.

## Safety

- File name searches with no folder specified scan the user profile when using standard folders, or the common
  parent of custom folders. Dot-prefixed, AppData/cache and dependency directories are skipped, and searches stop
  after 6 seconds or 50 results. Reading,
  opening or changing files is still limited to Settings → Allowed folders. Paths are resolved (symlinks, junctions,
  `..`) before checking, and re-checked right before a change.
- Opening unregistered apps, creating files/folders, closing apps, sending email and pressing keys need approval. The dialog shows the exact
  path / recipients / keys and the full content.
- Script files cannot be launched through file opening. "Open" on `.py`/`.bat`/`.exe` refuses; `open_with_editor`
  opens them in VS Code/Notepad. There is no shell-command tool.
- Closing an app uses a normal close (`taskkill` without `/F`) and checks it actually closed.
- No shell tool, no installer, no delete.
- Everything is logged: header → **Action log**.

## Free-tier limits

When a provider hits its limit ULTRON moves to the next one and puts it on a cooldown:
- rate limit (429): the provider's retry time, or 60 s
- Gemini daily quota: until midnight Pacific (1:30 PM IST in winter, 12:30 PM in summer)
- Groq daily quota: 60 min (`quota_cooldown_minutes` in `providers.json`)
- rejected key: 24 h (fix the key in Settings)

The right panel shows each provider's state.

## Files

```
main.py                 start the app
config.py               defaults: paths, budgets, built-in apps
providers.json          cloud models and the order they're tried per task
core/
  router.py             local decision: device / web / chat
  providers.py          builds models, cooldowns
  agents.py             device agent (local only) + chat/web agents + tools wiring
  assistant.py          route → run → fall back → store
  history.py            history with the privacy split + size budget
  writer.py             cloud message writing (scrubbed request only)
  scheduler.py          scheduled tasks + "at 6 pm" / "in 30 minutes" parsing
  prompts.py, secrets.py
tools/                  files, apps, system, web, email, keyboard, whatsapp, clipboard
security/               path security, approval gate
memory/database.py      SQLite (chats, messages, settings, action log)
gui/                    PySide6 window, dialogs, background workers, theme
  voice_mode.py, orb.py voice mode window and the animated core
voice/                  mic recording, Whisper, Piper, voice effect, silence detection (listen.py)
assets/                 icons
tests/                  pytest suite
```

Data lives in `%LOCALAPPDATA%\ULTRON\` (database + downloaded models). Delete that folder to reset.
An existing V1 database there is upgraded in place.

## Changing things

- Cloud model ids: Settings → AI, or `providers.json` (check current ids in the Groq console / AI Studio).
- Order per task: `tasks` in `providers.json`.
- Context/size budgets: `config.py` (`HISTORY_CHARS`, `TOOL_OUTPUT_CHARS`). Ollama's default context is 4096;
  to raise it set the `OLLAMA_CONTEXT_LENGTH` environment variable before starting Ollama.
- Routing rules: `DEVICE_PATTERNS`, `WEB_PATTERN`, `EXAMPLES` in `core/router.py`.
- Built-in app aliases: `APPLICATIONS` and `APP_ALIASES` in `config.py`. Other apps can be named by executable or full `.exe` path.

## Tests

```bash
pip install pytest
python -m pytest
```

Tests use fake models, so they don't need Ollama, keys or internet.
