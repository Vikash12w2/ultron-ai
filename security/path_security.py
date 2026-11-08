from pathlib import Path
import os
from config import ALLOWED_ROOTS

RESERVED = {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}

class PathDenied(ValueError): pass

class PathSecurity:
    def __init__(self, roots=None):
        self.roots = [Path(p).expanduser().resolve() for p in (roots or ALLOWED_ROOTS)]
    def resolve(self, value, allow_missing=False):
        raw = str(value).strip().strip('"')
        if not raw or raw.startswith(("\\\\", "//")):
            raise PathDenied("Empty paths and network paths are not allowed.")
        p = Path(raw).expanduser()
        if not p.is_absolute():
            shorthand = {r.name.casefold(): r for r in self.roots}
            first = raw.replace("\\", "/").split("/",1)[0].casefold()
            if first in shorthand:
                suffix = raw.replace("\\", "/").split("/",1)
                p = shorthand[first] / (suffix[1] if len(suffix)>1 else "")
            else:
                raise PathDenied("Use a full path or a configured folder such as Documents or Downloads.")
        resolved = p.resolve(strict=not allow_missing)
        for part in resolved.parts:
            if ":" in part and part != resolved.anchor:
                raise PathDenied("Alternate data stream paths are not allowed.")
            if part.rstrip(" .").split(".")[0].upper() in RESERVED:
                raise PathDenied("Reserved Windows device names are not allowed.")
        if not any(resolved == root or root in resolved.parents for root in self.roots):
            raise PathDenied("That path is outside ULTRON's configured allowed folders.")
        return resolved
    def root_labels(self): return [str(p) for p in self.roots]
