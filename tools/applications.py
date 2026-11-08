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
    def open_website(self,url,browser="default"):
        from urllib.parse import urlparse
        browser=(browser or "default").casefold()
        chrome_page=url.startswith("chrome://")
        if not url.startswith(("https://","http://","chrome://")): url="https://"+url
        parsed=urlparse(url)
        if chrome_page and browser!="chrome": raise ValueError("Chrome internal pages can only be opened explicitly in Chrome.")
        if parsed.scheme not in (("https","http","chrome") if browser=="chrome" else ("https","http")) or (parsed.scheme!="chrome" and not parsed.netloc):
            raise ValueError("Provide a valid http or https website address.")
        if chrome_page and url.rstrip("/").casefold()!="chrome://settings/manageprofile":
            raise ValueError("Only Chrome's profile manager page is allowed as an internal Chrome URL.")
        if browser=="chrome":
            if os.name!="nt": raise RuntimeError("Launching Chrome directly is supported on Windows only.")
            spec=self.registry.get("chrome")
            if not spec: raise RuntimeError("Chrome isn't registered in ULTRON settings.")
            target=next((c for c in spec["candidates"] if Path(c).is_absolute() and Path(c).exists()),None)
            if not target: target=next((c for c in spec["candidates"] if not Path(c).is_absolute()),None)
            if not target: raise FileNotFoundError(f"Chrome was not found. Checked: {spec['candidates'][0]}")
            before=self.process_ids(spec["process"])
            try: subprocess.Popen([target,url],shell=False)
            except OSError as exc: raise RuntimeError(f"Couldn't open {url} in Chrome: {exc}") from exc
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                after=self.process_ids(spec["process"])
                if after-before:return {"url":url,"browser":"Chrome","status":"launched"}
                if before:return {"url":url,"browser":"Chrome","status":"sent_to_running_instance"}
                time.sleep(0.2)
            raise RuntimeError("Chrome accepted the launch request but no Chrome process appeared.")
        opened=webbrowser.open(url)
        if not opened: raise RuntimeError(f"Windows didn't accept the request to open {url} in the default browser.")
        return {"url":url,"browser":"default","status":"opened"}
    def close_app(self,process):
        import psutil
        wanted=process.casefold(); found=[p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").casefold()==wanted]
        for p in found: p.terminate()
        return {"process":process,"requested_close":len(found)}
