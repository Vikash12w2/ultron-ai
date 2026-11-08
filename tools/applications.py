import os, subprocess, time, webbrowser
from pathlib import Path
from config import APPLICATIONS

class ApplicationTools:
    def __init__(self, registry=None): self.registry=registry or APPLICATIONS
    @staticmethod
    def process_ids(name):
        try: import psutil
        except ImportError: return set()
        return {p.pid for p in psutil.process_iter(["pid","name"]) if (p.info.get("name") or "").casefold()==name.casefold()}
    def open_app(self,app):
        key=app.casefold().replace(" ","")
        aliases={"visualstudiocode":"vscode","fileexplorer":"explorer","windowssettings":"settings"}
        key=aliases.get(key,key)
        if key not in self.registry: raise ValueError(f"'{app}' is not a registered application. Configure it in Settings first.")
        spec=self.registry[key]; before=self.process_ids(spec["process"])
        try:
            if spec.get("uri"):
                if os.name!="nt": raise RuntimeError("Windows Settings is only available on Windows.")
                os.startfile(spec["uri"])
            else:
                target=next((c for c in spec["candidates"] if Path(c).is_absolute() and Path(c).exists()),None)
                if not target: target=next((c for c in spec["candidates"] if not Path(c).is_absolute()),None)
                if not target: raise FileNotFoundError(f"Configured application path not found: {spec['candidates'][0]}")
                subprocess.Popen([target],shell=False)
        except Exception as exc: return {"status":"failed","app":spec["label"],"reason":str(exc)}
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            after=self.process_ids(spec["process"])
            if after-before:return {"status":"launched","app":spec["label"]}
            time.sleep(0.2)
        after=self.process_ids(spec["process"])
        if after and not (after-before): return {"status":"already_running","app":spec["label"]}
        return {"status":"failed","app":spec["label"],"reason":"No matching process appeared after the launch request."}
    def open_website(self,url):
        if not url.startswith(("https://","http://")): url="https://"+url
        from urllib.parse import urlparse
        parsed=urlparse(url)
        if parsed.scheme not in ("https","http") or not parsed.netloc: raise ValueError("Provide a valid http or https website address.")
        webbrowser.open(url); return {"url":url,"opened":True}
    def close_app(self,process):
        import psutil
        wanted=process.casefold(); found=[p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").casefold()==wanted]
        for p in found: p.terminate()
        return {"process":process,"requested_close":len(found)}
