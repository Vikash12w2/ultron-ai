# ULTRON · Version 1

Local-first Windows assistant. The local blueprint, UI concept images, and icon assets are intentionally excluded from Git by `.gitignore`. Python 3.12+, PySide6, Ollama, and the local model are expected. Nothing is installed by the application. It does not create its local database until the app is launched.

## Start

1. Install Ollama separately and make a model available (`qwen3:1.7b` is the blueprint default; the model is configurable in Settings).
2. Install the core packages with `python -m pip install -r requirements.txt`.
3. Run `python main.py`.

ULTRON stores conversations, settings, and action logs in `%LOCALAPPDATA%\ULTRON\ultron.db`. File operations are restricted to Desktop, Documents, Downloads, and configured roots. Add additional roots in Settings. Create and close operations require approval; opening apps, websites, and documents follows the blueprint's automatic permission level. There is no shell or installer tool.

Optional speech packages are listed in `requirements-voice.txt`; voice capture is not enabled in this initial desktop build. Web search uses the `ddgs` provider and makes the query visible in task status. Ollama model calls stay local.

## Device changes

ULTRON itself does not install software. It asks in the app before creating folders/files or closing a process. You must separately approve package installation and any Ollama model download outside the application.
