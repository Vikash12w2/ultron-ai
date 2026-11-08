from __future__ import annotations

from pathlib import Path

RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class PathDenied(ValueError):
    """Raised when a path is outside the allowed folders or otherwise unsafe."""


class PathSecurity:
    def __init__(self, roots: list[str] | list[Path]):
        if not roots:
            raise ValueError("At least one allowed folder is required.")
        self.roots = [Path(r).expanduser().resolve() for r in roots]

    def labels(self) -> list[str]:
        return [str(r) for r in self.roots]

    def describe_roots(self) -> str:
        return ", ".join(f"{r.name} ({r})" for r in self.roots)

    def resolve(self, value: str, *, must_exist: bool = True) -> Path:
        """Turn a user/model supplied path into a safe, absolute, canonical path.

        - Shorthands like "Downloads" or "Documents/notes.txt" map to the allowed folder of that name.
        - Symlinks, junctions and ".." are resolved before the containment check.
        """
        raw = str(value or "").strip().strip('"').strip("'")
        if not raw:
            raise PathDenied("No path was given.")
        if raw.startswith(("\\\\", "//")):
            raise PathDenied("Network paths are not allowed.")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            first, _, rest = raw.replace("\\", "/").partition("/")
            matches = {r.name.casefold(): r for r in self.roots}
            if first.casefold() not in matches:
                raise PathDenied(
                    f"'{raw}' isn't inside an allowed folder. Use a full path or one of: "
                    + ", ".join(r.name for r in self.roots)
                )
            path = matches[first.casefold()] / rest if rest else matches[first.casefold()]
        try:
            resolved = path.resolve(strict=must_exist)
        except FileNotFoundError:
            raise PathDenied(f"Not found: {path}") from None
        except OSError as exc:
            raise PathDenied(f"Couldn't access {path}: {exc}") from None
        for part in resolved.parts[1:]:
            if ":" in part:
                raise PathDenied("Alternate data stream paths are not allowed.")
            if part.rstrip(" .").split(".")[0].upper() in RESERVED_NAMES:
                raise PathDenied("Reserved Windows device names are not allowed.")
        if not any(resolved == root or resolved.is_relative_to(root) for root in self.roots):
            raise PathDenied(f"{resolved} is outside ULTRON's allowed folders.")
        return resolved
