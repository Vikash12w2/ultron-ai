from __future__ import annotations

import os

SERVICE = "ULTRON"


def get_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import keyring
        return (keyring.get_password(SERVICE, name) or "").strip()
    except Exception:
        return ""


def set_key(name: str, value: str) -> None:
    import keyring
    value = (value or "").strip()
    if value:
        keyring.set_password(SERVICE, name, value)
    else:
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:
            pass


def has_key(name: str) -> bool:
    return bool(get_key(name))
