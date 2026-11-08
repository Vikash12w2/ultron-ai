from pathlib import Path
from security.path_security import PathSecurity

TEXT_EXTENSIONS={".txt",".md",".py",".cpp",".h",".java",".json",".csv",".log",".yaml",".yml",".toml",".ini"}
EXECUTABLE_EXTENSIONS={".exe",".bat",".cmd",".ps1",".py",".pyw",".lnk",".msi",".vbs",".js",".com"}

class FilesystemTools:
    def __init__(self, security=None): self.security=security or PathSecurity()
    def list_files(self,directory,extension="",query=""):
        root=self.security.resolve(directory)
        if not root.is_dir(): raise ValueError(f"Not a folder: {root}")
        ext=extension.casefold(); needle=query.casefold()
        matches=[]
        for item in root.iterdir():
            if (not ext or item.suffix.casefold()==ext) and (not needle or needle in item.name.casefold()):
                matches.append({"name":item.name,"path":str(item),"type":"folder" if item.is_dir() else "file"})
        return matches[:100]
    def find_files(self,directory,query,extension=""):
        root=self.security.resolve(directory); ext=extension.casefold(); needle=query.casefold(); out=[]
        if not root.is_dir(): raise ValueError(f"Not a folder: {root}")
        for base, dirs, files in __import__('os').walk(root):
            dirs[:]=[d for d in dirs if not d.startswith(".")]
            for name in files:
                p=Path(base)/name
                if needle in name.casefold() and (not ext or p.suffix.casefold()==ext):
                    out.append({"name":name,"path":str(p)})
                    if len(out)>=100:return out
        return out
    def read_file(self,path):
        p=self.security.resolve(path)
        if p.suffix.casefold()==".pdf":
            try: from pypdf import PdfReader
            except ImportError as exc: raise RuntimeError("PDF reading needs the optional pypdf dependency.") from exc
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)[:20000]
        if p.suffix.casefold() not in TEXT_EXTENSIONS: raise ValueError(f"Reading {p.suffix} files is not supported.")
        if p.stat().st_size > 2_000_000: raise ValueError("That file is larger than the 2 MB reading limit.")
        return p.read_text(encoding="utf-8",errors="replace")[:20000]
    def create_folder(self,path):
        p=self.security.resolve(path,allow_missing=True); p.mkdir(parents=True,exist_ok=False)
        return {"path":str(p),"exists":p.is_dir()}
    def create_text_file(self,path,content):
        p=self.security.resolve(path,allow_missing=True)
        if p.exists(): raise FileExistsError(f"File already exists: {p}")
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(content,encoding="utf-8",newline="\n")
        return {"path":str(p),"exists":p.is_file()}
    def open_path(self,path,editor=False):
        p=self.security.resolve(path)
        if p.suffix.casefold() in EXECUTABLE_EXTENSIONS and not editor: raise ValueError("Executable files cannot be opened with the default app. Use open_with_editor.")
        if editor:
            import subprocess
            choices=["code.exe","notepad.exe"]
            for executable in choices:
                try: subprocess.Popen([executable,str(p)],shell=False); return {"path":str(p),"editor":executable}
                except OSError: continue
            raise RuntimeError("Couldn't find VS Code or Notepad to open the file safely.")
        if __import__('os').name!="nt": raise RuntimeError("Opening documents is supported on Windows only.")
        __import__('os').startfile(str(p)); return {"path":str(p),"opened":True}
