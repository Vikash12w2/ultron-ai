import json
from typing import Any
from tools.filesystem import FilesystemTools
from tools.applications import ApplicationTools
from tools.system_info import system_info
from tools.web_search import web_search

class ToolRegistry:
    def __init__(self, roots=None):
        self.fs=FilesystemTools() if roots is None else FilesystemTools(__import__('security.path_security',fromlist=['PathSecurity']).PathSecurity(roots)); self.apps=ApplicationTools()
        self.specs={
            "list_files":({"type":"function","function":{"name":"list_files","description":"List files in an allowed folder, optionally filtering extension or filename query.","parameters":{"type":"object","properties":{"directory":{"type":"string"},"extension":{"type":"string"},"query":{"type":"string"}},"required":["directory"]}}},self.fs.list_files,"auto"),
            "find_files":({"type":"function","function":{"name":"find_files","description":"Recursively find matching filenames under an allowed folder.","parameters":{"type":"object","properties":{"directory":{"type":"string"},"query":{"type":"string"},"extension":{"type":"string"}},"required":["directory","query"]}}},self.fs.find_files,"auto"),
            "read_file":({"type":"function","function":{"name":"read_file","description":"Read a requested supported text or PDF file in an allowed folder.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},self.fs.read_file,"auto"),
            "open_document":({"type":"function","function":{"name":"open_document","description":"Open a non-executable document using its Windows default application.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},self.fs.open_path,"auto"),
            "open_with_editor":({"type":"function","function":{"name":"open_with_editor","description":"Open a file in VS Code or Notepad; never execute it.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},lambda path:self.fs.open_path(path,True),"auto"),
            "open_app":({"type":"function","function":{"name":"open_app","description":"Open a registered Windows application by name.","parameters":{"type":"object","properties":{"app":{"type":"string"}},"required":["app"]}}},self.apps.open_app,"auto"),
            "open_website":({"type":"function","function":{"name":"open_website","description":"Open a user requested http or https website.","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}},self.apps.open_website,"auto"),
            "system_info":({"type":"function","function":{"name":"system_info","description":"Read live CPU, RAM, disk, or process information from Windows.","parameters":{"type":"object","properties":{"kind":{"type":"string","enum":["overview","cpu","ram","disk","processes"]}},"required":[]}}},system_info,"auto"),
            "web_search":({"type":"function","function":{"name":"web_search","description":"Search the public web for current information. The UI will show the exact query before sending it.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},web_search,"auto"),
            "create_folder":({"type":"function","function":{"name":"create_folder","description":"Create a new folder inside an allowed folder.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},self.fs.create_folder,"approval"),
            "create_text_file":({"type":"function","function":{"name":"create_text_file","description":"Create a new UTF-8 text file inside an allowed folder.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},self.fs.create_text_file,"approval"),
            "close_app":({"type":"function","function":{"name":"close_app","description":"Close a named process. Requires user approval.","parameters":{"type":"object","properties":{"process":{"type":"string"}},"required":["process"]}}},self.apps.close_app,"approval"),
        }
    def model_specs(self): return [spec for spec,_,_ in self.specs.values()]
    def execute(self,name,args):
        if name not in self.specs: raise ValueError(f"Unregistered tool: {name}")
        if not isinstance(args,dict): raise ValueError("Tool arguments must be an object.")
        schema=self.specs[name][0]["function"]["parameters"]
        allowed=set(schema.get("properties",{})); unknown=set(args)-allowed
        missing=set(schema.get("required",[]))-set(args)
        if unknown or missing: raise ValueError(f"Invalid arguments (unknown: {sorted(unknown)}, missing: {sorted(missing)}).")
        for key,value in args.items():
            if key in allowed and not isinstance(value,str): raise ValueError(f"Argument '{key}' must be text.")
        return self.specs[name][1](**args)
    def permission(self,name):
        if name not in self.specs: raise ValueError(f"Unregistered tool: {name}")
        return self.specs[name][2]
    def describe(self,name,args):
        if name in ("create_folder","create_text_file"): return f"{name.replace('_',' ').title()}\nPath: {args.get('path')}" + (f"\nContent: {args.get('content','')[:400]}" if name=="create_text_file" else "")
        if name=="close_app": return f"Close process: {args.get('process')}"
        if name=="web_search": return f"Send this query to the external web search provider:\n{args.get('query')}"
        return json.dumps(args,ensure_ascii=False)

    def approval_arguments(self,name,args):
        """Resolve protected paths before presenting the approval; execution re-resolves them."""
        args=dict(args)
        if name in ("create_folder","create_text_file"):
            args["path"]=str(self.fs.security.resolve(args["path"],allow_missing=True))
        return args
