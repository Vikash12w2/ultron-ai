import json
import re
from pathlib import Path
from core.prompt import SYSTEM_PROMPT
from core.llm import OllamaProvider
from tools.registry import ToolRegistry
from core.intent_router import route_request, RoutedRequest
from core.text_similarity import normalize

class Agent:
    def __init__(self, database, model="qwen3:1.7b", host="http://127.0.0.1:11434", approval=None, status=None):
        import json
        roots=json.loads(database.get_setting("allowed_roots","null"))
        self.db,self.provider,self.registry=database,OllamaProvider(model,host),ToolRegistry(roots)
        self.approval=approval or (lambda _name,_args,_description:False)
        self.status=status or (lambda _message:None)
    def respond(self,conversation_id,user_text):
        self.db.add_message(conversation_id,"user",user_text)
        rows=self.db.messages(conversation_id)
        # A short failure report such as “no, it didn't open” refers to the most recent website-opening request in this chat. Retry that action with its original target instead of asking the model to guess.
        if re.search(r"\b(?:not|didn['’]?t|did not|hasn['’]?t|never)\b.*\b(?:open(?:ed)?|work(?:ing)?)\b",user_text.casefold()):
            for previous in reversed(rows[:-1]):
                if previous["role"]!="user": continue
                prior=route_request(previous["content"])
                if prior and prior.kind=="tool" and any(name=="open_website" for name,_ in prior.calls):
                    retry=RoutedRequest("tool",[call for call in prior.calls if call[0]=="open_website"])
                    answer=self._respond_routed(user_text,retry)
                    self.db.add_message(conversation_id,"assistant",answer)
                    return answer
        routed=route_request(user_text)
        # Preserve a just-used local file-search scope when the user follows
        # with a shortened restatement of the same filename.
        if routed and routed.kind=="find_files_all" and not routed.calls[0][1].get("extension"):
            current_query=normalize(routed.calls[0][1].get("query",""))
            for previous in reversed(rows[:-1]):
                if previous["role"]!="user":continue
                prior=route_request(previous["content"])
                prior_args=None
                if prior and prior.kind=="find_files_all":prior_args=prior.calls[0][1]
                elif prior and prior.kind=="tool":
                    prior_args=next((args for name,args in prior.calls if name=="find_files"),None)
                if prior_args and normalize(prior_args.get("query",""))==current_query:
                    if prior.kind=="find_files_all" or prior_args.get("extension") or prior_args.get("directory"):
                        routed=prior
                        break
        if routed:
            answer=self._respond_routed(user_text,routed)
            self.db.add_message(conversation_id,"assistant",answer)
            return answer
        history=[{"role":r["role"],"content":r["content"]} for r in rows if r["role"] in ("user","assistant")]
        # Keep history below the model's modest context window.
        while len(history)>1 and sum(len(m["content"]) for m in history)>15000: history.pop(0)
        folders=", ".join(f"{p.name} ({p})" for p in self.registry.fs.security.roots)
        messages=[{"role":"system","content":SYSTEM_PROMPT.replace("$ALLOWED_FOLDERS",folders)},*history]
        for step in range(5):
            reply=self.provider.chat(messages,self.registry.model_specs())
            if not reply.tool_calls:
                answer=reply.text.strip() or "I didn't get a response from the local model."
                self.db.add_message(conversation_id,"assistant",answer)
                return answer
            assistant={"role":"assistant","content":reply.text or "","tool_calls":[{"function":{"name":c["name"],"arguments":c["arguments"]}} for c in reply.tool_calls]}
            messages.append(assistant)
            for call in reply.tool_calls:
                name,args=call.get("name",""),call.get("arguments",{})
                result=self._invoke_tool(user_text,name,args)
                messages.append({"role":"tool","content":json.dumps(result,ensure_ascii=False,default=str),"name":name})
            self.status(f"Completed tool step {step+1} of 5")
        answer="I stopped after five tool calls to avoid getting stuck. Please tell me what to do next."
        self.db.add_message(conversation_id,"assistant",answer)
        return answer

    def _invoke_tool(self,request,name,args):
        result=None;status="failed";approval_status="not_required"
        try:
            permission=self.registry.permission(name)
            if permission=="approval":
                args=self.registry.approval_arguments(name,args)
                approval_status="approved" if self.approval(name,args,self.registry.describe(name,args)) else "rejected"
                if approval_status!="approved":
                    result={"error":"The user rejected this action. Do not retry it."};status="rejected"
                else:
                    self.status(f"Running approved action: {name}")
                    result=self.registry.execute(name,args);status="completed"
            else:
                if name=="web_search":self.status(f"Searching the web: {args.get('query','')}")
                result=self.registry.execute(name,args);status="completed"
                if name=="find_files" and result==[] and "resume" not in request.casefold():
                    explicitly_scoped=any(re.search(rf"\b{re.escape(root.name)}\b",request,re.IGNORECASE) for root in self.registry.fs.security.roots) or bool(re.search(r"\b[A-Za-z]:[\\/]|\\\\",request))
                    if not explicitly_scoped:
                        searched=[];matches=[]
                        for root in self.registry.fs.security.roots:
                            searched.append(str(root))
                            if Path(args.get("directory","")).expanduser().resolve()==root.resolve():
                                continue
                            matches.extend(self.registry.fs.find_files(str(root),args.get("query",""),args.get("extension","")))
                        if matches:
                            result=matches[:100]
                        else:
                            result={"matches":[],"searched_directories":searched,"message":"No matching files were found in the configured allowed folders."}
        except Exception as exc:result={"error":str(exc)}
        self.db.log_action(request,name,args,approval_status,status,result)
        return result

    def _respond_routed(self,request,routed):
        if routed.kind=="response":return routed.response
        if routed.kind in ("latest_resume","find_resume_all","find_files_all"):
            self.status("Searching configured folders for resumes…")
            matches=[]
            if routed.kind=="find_files_all":
                query=routed.calls[0][1]["query"];extension=routed.calls[0][1].get("extension","")
                self.status(f"Searching configured folders for filenames similar to: {query}")
                for root in self.registry.fs.security.roots:
                    matches.extend(self.registry.fs.find_files(str(root),query,extension))
                if not matches:
                    kind="PDF files" if extension==".pdf" else "files"
                    return f"I couldn't find {kind} matching ‘{query}’ in the configured Desktop, Documents, or Downloads folders."
                lines=[f"I found {len(matches)} matching file(s) in your configured folders:"]
                lines.extend(f"- {item.get('name')} — {item.get('path')}" for item in matches[:40])
                if len(matches)>40:lines.append("Showing the first 40 matches.")
                return "\n".join(lines)
            for root in self.registry.fs.security.roots:
                result=self._invoke_tool(request,"find_files",{"directory":str(root),"query":"resume"})
                if isinstance(result,list):matches.extend(result)
            if routed.kind=="find_resume_all":
                if not matches:return "I couldn't find a file with ‘resume’ in its name in the configured Desktop, Documents, or Downloads folders. Tell me another filename or folder to search."
                lines=[f"I found {len(matches)} matching file(s) in your configured folders:"]
                lines.extend(f"- {item.get('name')} — {item.get('path')}" for item in matches[:40])
                if len(matches)>40:lines.append("Showing the first 40 matches.")
                return "\n".join(lines)
            supported={".pdf",".doc",".docx",".rtf",".txt",".odt"}
            candidates=[]
            for match in matches:
                path=Path(match["path"])
                if path.suffix.casefold() in supported:
                    try:candidates.append((path.stat().st_mtime,path))
                    except OSError:pass
            if not candidates:
                return "I couldn't find a resume in the configured Desktop, Documents, or Downloads folders. Tell me another folder or filename to search."
            path=max(candidates,key=lambda item:item[0])[1]
            result=self._invoke_tool(request,"open_document",{"path":str(path)})
            if isinstance(result,dict) and result.get("error"):return f"I found {path.name}, but couldn't open it: {result['error']}"
            return f"Opened your most recently modified matching resume: {path.name}."

        results=[]
        for name,args in routed.calls:
            if name!="web_search":self.status(self._tool_status(name,args))
            results.append((name,args,self._invoke_tool(request,name,args)))
        if not results:return routed.response
        name,args,result=results[-1]
        if isinstance(result,dict) and result.get("error"):
            return f"I couldn't complete that: {result['error']}"
        if name=="open_app":
            status=result.get("status")
            if status=="launched":return f"Opened {result.get('app',args.get('app'))}."
            if status=="already_running":return f"{result.get('app',args.get('app'))} is already running; I sent the request to open it again."
            if status=="failed":return f"I couldn't open {result.get('app',args.get('app'))}: {result.get('reason','unknown launch error')}"
        if name=="open_website":
            if result.get("status")=="sent_to_running_instance":return f"I sent the request to open {result['url']} in the running Chrome instance."
            browser="Chrome" if result.get("browser")=="Chrome" else "your default browser"
            return f"Opened {result['url']} in {browser}."
        if name=="web_search":
            if not result:return f"I searched for {args['query']}, but the search provider returned no results."
            lines=[f"Web results for: {args['query']}"]
            for item in result[:6]:
                lines.append(f"- {item.get('title') or item.get('url')} — {item.get('snippet','')}\n  {item.get('url','')}")
            return "\n".join(lines)
        if name in ("list_files","find_files"):
            title="Folder contents" if name=="list_files" else "Matching files"
            if not result:return f"I didn't find any matching files in {args.get('directory')}."
            lines=[f"{title} in {args.get('directory')} ({len(result)} shown):"]
            lines.extend(f"- {item.get('name')} — {item.get('path')}" for item in result[:40])
            if len(result)>40:lines.append("Showing the first 40 matches.")
            return "\n".join(lines)
        return f"Completed {name}: {json.dumps(result,ensure_ascii=False,default=str)}"

    @staticmethod
    def _tool_status(name,args):
        if name=="web_search":return f"Searching the web: {args.get('query','')}"
        if name=="open_app":return f"Opening {args.get('app','application')}…"
        if name=="open_website":return f"Opening {args.get('url','website')}…"
        if name in ("list_files","find_files"):return f"Searching files in {args.get('directory','folder')}…"
        return f"Running {name}…"
