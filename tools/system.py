from __future__ import annotations

import os


def system_info(kind: str = "overview") -> dict:
    import psutil

    kind = (kind or "overview").casefold()
    gb = 1024 ** 3
    if kind in ("ram", "memory"):
        m = psutil.virtual_memory()
        return {"ram_available_gb": round(m.available / gb, 2), "ram_used_gb": round(m.used / gb, 2),
                "ram_total_gb": round(m.total / gb, 2), "ram_percent": m.percent}
    if kind == "cpu":
        return {"cpu_percent": psutil.cpu_percent(interval=0.4), "logical_cores": psutil.cpu_count()}
    if kind == "disk":
        d = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
        return {"disk_free_gb": round(d.free / gb, 1), "disk_total_gb": round(d.total / gb, 1), "disk_percent": d.percent}
    if kind == "battery":
        b = psutil.sensors_battery()
        if b is None:
            return {"battery": "No battery found."}
        return {"battery_percent": round(b.percent), "plugged_in": b.power_plugged,
                "minutes_left": None if b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                else b.secsleft // 60}
    if kind == "processes":
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            mem = p.info.get("memory_info")
            procs.append((mem.rss if mem else 0, p.info.get("name") or "?"))
        top = sorted(procs, reverse=True)[:15]
        return {"top_processes_by_memory": [{"name": n, "ram_mb": round(r / 1024 ** 2)} for r, n in top]}
    m = psutil.virtual_memory()
    return {"cpu_percent": psutil.cpu_percent(interval=0.4), "ram_available_gb": round(m.available / gb, 2),
            "ram_used_gb": round(m.used / gb, 2), "ram_total_gb": round(m.total / gb, 2), "ram_percent": m.percent}
