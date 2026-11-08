import json
from core.prompt import SYSTEM_PROMPT
from core.llm import OllamaProvider
from tools.registry import ToolRegistry

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
        history=[{"role":r["role"],"content":r["content"]} for r in rows if r["role"] in ("user","assistant")]
        # Keep history below the model's modest context window.
        while len(history)>1 and sum(len(m["content"]) for m in history)>15000: history.pop(0)
        messages=[{"role":"system","content":SYSTEM_PROMPT},*history]
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
                result=None; status="failed"; approval_status="not_required"
                try:
                    permission=self.registry.permission(name)
                    if permission=="approval":
                        args=self.registry.approval_arguments(name,args)
                        approval_status="approved" if self.approval(name,args,self.registry.describe(name,args)) else "rejected"
                        if approval_status!="approved":
                            result={"error":"The user rejected this action. Do not retry it."}; status="rejected"
                        else:
                            self.status(f"Running approved action: {name}")
                            result=self.registry.execute(name,args); status="completed"
                    else:
                        if name=="web_search": self.status(f"Searching the web: {args.get('query','')}")
                        result=self.registry.execute(name,args); status="completed"
                except Exception as exc:
                    result={"error":str(exc)}
                self.db.log_action(user_text,name,args,approval_status,status,result)
                messages.append({"role":"tool","content":json.dumps(result,ensure_ascii=False,default=str),"name":name})
            self.status(f"Completed tool step {step+1} of 5")
        answer="I stopped after five tool calls to avoid getting stuck. Please tell me what to do next."
        self.db.add_message(conversation_id,"assistant",answer)
        return answer
