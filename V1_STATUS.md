# ULTRON V1 completion notes

Last checked: 2026-11-08

V1 is not fully complete. This file tracks the remaining work so it is not lost between development sessions.

## Verified

- Offline acceptance suite: 47 passed, 9 skipped on the last run.
- Live acceptance: 7 passed. The web-search test timed out in the sandbox; the same provider returned results when retried with network access.
- Qwen local conversation, app launch checks, and fixture file operations passed in the live suite.
- Faster-Whisper local model loads successfully. Piper generated a WAV sample and speaker playback completed.
- Python voice packages and local Whisper/Piper model files are installed and configured.

## Remaining

- **Microphone input:** the last live capture attempt failed to open the default Windows input stream (`PortAudio -9999`, Windows MME error 1). Alternate host APIs also failed or returned no captured samples. Re-test after Windows input-device access/driver setup is confirmed.
- **Tool timeouts:** the app has no general enforced timeout for tool operations. Add bounded execution and clear timeout reporting.
- **Web retrieval:** web search currently returns result snippets and links. Fetch pages and summarize retrieved content through the local model to complete the blueprint workflow.
- **Battery status:** CPU, RAM, disk, and process reporting are present; battery reporting is missing.
- **Model runtime status:** the UI reports whether the configured model is installed, not whether Ollama currently has it loaded or unloaded.
- **Symlink/junction acceptance:** path resolution follows links and checks the resolved path, but the symlink-escape test skipped because this Windows account could not create the test symlink. Re-run on an account/environment that supports the test.
- **Final live acceptance:** re-run the full live suite once the microphone issue is resolved and verify the current external-search environment.

The blueprint marks `run_python_script()` as a feature that may be postponed; it is intentionally not implemented. Cloud reasoning, wake words, long-term semantic memory, shell access, and browser automation are outside V1 scope.
