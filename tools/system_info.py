def system_info(kind="overview"):
    try: import psutil
    except ImportError as exc: raise RuntimeError("System monitoring needs the optional psutil dependency.") from exc
    kind=kind.casefold()
    if kind in ("ram","memory"):
        m=psutil.virtual_memory(); return {"available_gb":round(m.available/1024**3,2),"used_gb":round(m.used/1024**3,2),"total_gb":round(m.total/1024**3,2),"percent":m.percent}
    if kind=="cpu": return {"cpu_percent":psutil.cpu_percent(interval=0.35),"logical_cores":psutil.cpu_count()}
    if kind=="disk":
        import os
        d=psutil.disk_usage(os.environ.get("SystemDrive","C:")+"\\"); return {"total_gb":round(d.total/1024**3,1),"free_gb":round(d.free/1024**3,1),"percent":d.percent}
    if kind=="processes": return [{"name":p.info.get("name"),"pid":p.info.get("pid")} for p in psutil.process_iter(["name","pid"])][:100]
    m=psutil.virtual_memory()
    return {"cpu_percent":psutil.cpu_percent(interval=0.35),"ram_used_gb":round(m.used/1024**3,2),"ram_total_gb":round(m.total/1024**3,2),"ram_available_gb":round(m.available/1024**3,2),"ram_percent":m.percent}
