from dataclasses import dataclass
import re
from core.text_similarity import correct_known_terms, phrase_in_text

ROOTS={"downloads":"Downloads","download":"Downloads","documents":"Documents","document":"Documents","desktop":"Desktop"}
SITES={
    "youtube":"https://www.youtube.com",
    "youtu.be":"https://www.youtube.com",
    "google":"https://www.google.com",
    "github":"https://github.com",
    "chatgpt":"https://chatgpt.com",
    "gmail":"https://mail.google.com",
}
SITE_PATTERNS={
    "youtube":r"\by\W*o\W*u\W*t\W*u\W*b\W*e\b",
    "youtu.be":r"\byoutu\W*be\b",
    "google":r"\bgoogle\b",
    "github":r"\bgithub\b",
    "chatgpt":r"\bchat\W*gpt\b",
    "gmail":r"\bg\W*mail\b",
}
ROUTING_WORDS={"open","visit","go","to","navigate","launch","show","search","look","up","find","for","web","internet","online","latest","newest","most","recent","resume","in","under","inside","my","the","downloads","download","documents","document","desktop","files","file","folder","contents","what","is","all","any","pdf","pdfs","chrome","browser","profile","create","make","add","list","tutorial","tutorials","news","current","cuda","youtube","google","github","chatgpt","gmail"}

@dataclass
class RoutedRequest:
    kind: str
    calls: list[tuple[str,dict]]
    response: str = ""

def route_request(text: str) -> RoutedRequest | None:
    original=text.strip()
    corrected=correct_known_terms(original,ROUTING_WORDS)
    lower=corrected.casefold()
    if re.search(r"\b(?:create|make|add|new)\b.*\b(?:chrome|browser)\b.*\bprofile\b|\bprofile\b.*\b(?:chrome|browser)\b.*\b(?:create|make|add)\b",lower):
        return RoutedRequest("response",[],"ULTRON V1 can't create or select Chrome profiles automatically. I can open Chrome's profile manager so you can finish it there. Say ‘open Chrome profile manager’ if you want me to open it.")

    if re.search(r"\b(?:open|show|launch)\b",lower) and "chrome" in lower and "profile" in lower:
        return RoutedRequest("tool",[("open_website",{"url":"chrome://settings/manageProfile","browser":"chrome"})])

    # The newest resume is a file search followed by an automatic document open.
    if re.search(r"\b(?:open|show)\b",lower) and re.search(r"\b(?:latest|newest|most recent)\b",lower) and re.search(r"\bresume\b",lower):
        return RoutedRequest("latest_resume",[])

    # Explicit website/URL requests. This must precede the generic Chrome launch route.
    url_match=re.search(r"https?://[^\s<>\"']+",original,re.IGNORECASE)
    if re.search(r"\b(?:open|visit|go to|navigate to)\b",lower):
        url=""
        if url_match:
            url=url_match.group(0).rstrip(".,!?;:)")
        else:
            for site_name,site_url in SITES.items():
                if re.search(SITE_PATTERNS[site_name],lower) or phrase_in_text(lower,site_name):
                    url=site_url;break
            if not url:
                site=re.search(r"\b(?:open|visit|go to)\s+(?:the\s+)?([a-z0-9.-]+\.(?:com|org|net|edu|gov|io|ai)(?:/[^\s]*)?)",lower)
                if site: url="https://"+site.group(1)
        if url:
            browser="chrome" if "chrome" in lower else "default"
            return RoutedRequest("tool",[("open_website",{"url":url,"browser":browser})])

    if re.search(r"\b(?:open|launch|start)\b.*\b(?:google\s+)?chrome\b",lower):
        return RoutedRequest("tool",[("open_app",{"app":"chrome"})])

    # Search/list local folders before considering a web search.
    folder=None
    for alias,canonical in ROOTS.items():
        if re.search(rf"\b{alias}\b",lower):
            folder=canonical;break
    if folder and re.search(r"\b(?:find|search|look for)\b",lower):
        named_file=re.search(r"\b(?:files?\s+(?:named|called|matching|containing|like)\s+(?:like\s+)?|filename\s+(?:named\s+)?|pattern\s+(?:matching\s+)?)((?!in\s+).+)",corrected,re.IGNORECASE)
        if named_file:
            query=named_file.group(1).strip()
            query=re.sub(r"\s+(?:in|under|inside)\s+[A-Za-z]:[\\/].*$","",query,flags=re.IGNORECASE).strip()
            query=re.sub(r"\s+(?:in|on|from)\s+(?:(?:my\s+)?(?:device|computer|pc|laptop)\s+)?(?:my\s+)?(?:downloads?|documents?|desktop)(?:\s+folder)?\b.*$","",query,flags=re.IGNORECASE).strip()
            query=re.sub(r"\b(?:files?|documents?|pdfs?|named|called|matching|containing|filename|pattern|like)\b","",query,flags=re.IGNORECASE).strip().strip('"\'.,!?')
            extension=".pdf" if re.search(r"\bpdfs?\b",lower) else ""
            if query:return RoutedRequest("tool",[("find_files",{"directory":folder,"query":query,"extension":extension})])
        explicit_path=re.search(r"\b(?:in|under|inside)\s+([A-Za-z]:[\\/][^\s\"']+)",corrected,re.IGNORECASE)
        if explicit_path:
            prefix=corrected[:explicit_path.start()]
            prefix_query=re.search(r"\b(?:find|search for|look for)\s+(?:me\s+)?(?:my\s+|the\s+)?(.+)",prefix,re.IGNORECASE)
            if prefix_query:
                query=re.sub(r"\b(?:files?|documents?|named|called|matching|containing|filename|pattern|all|any|the|my|with|name)\b","",prefix_query.group(1),flags=re.IGNORECASE).strip().strip('"\'.,!?')
                directory=explicit_path.group(1).rstrip(".,!?;:)")
                if query:return RoutedRequest("tool",[("find_files",{"directory":directory,"query":query,"extension":""})])
        query_match=re.search(r"\b(?:find|search(?: for)?|look for)\s+(?:me\s+)?(?:my\s+|the\s+)?(.+?)\s+(?:in|under|inside)\s+(?:my\s+)?(?:downloads?|documents?|desktop)\b",corrected,re.IGNORECASE)
        if not query_match:
            query_match=re.search(r"\bsearch\s+(?:my\s+)?(?:downloads?|documents?|desktop)\s+for\s+(.+)",corrected,re.IGNORECASE)
        if query_match:
            query=query_match.group(1).strip()
            extension=""
            if re.search(r"\bpdfs?\b",lower): extension=".pdf"
            query=re.sub(r"\b(?:files?|documents?|pdfs?|named|called|matching|containing|filename|pattern|like)\b","",query,flags=re.IGNORECASE).strip()
            query=re.sub(r"\b(?:all|any|the|my|with|name)\b","",query).strip()
            return RoutedRequest("tool",[("find_files",{"directory":folder,"query":query,"extension":extension})])

    # Filename or identifier searches without a named folder should search all
    # configured roots directly; don't let the language model invent a path.
    file_query=re.search(r"\b(?:files?\s+(?:named|called|matching|containing|like)\s+(?:like\s+)?|filename\s+(?:named\s+)?|pattern\s+(?:matching\s+)?)((?!in\s+).+)",corrected,re.IGNORECASE)
    identifier_query=re.search(r"\b(?:find|search(?: for)?|look for)\s+(.+)",corrected,re.IGNORECASE)
    if not folder and (re.search(r"\b(?:find|search|look for)\b",lower) or bool(file_query)):
        query=file_query.group(1).strip() if file_query else (identifier_query.group(1).strip() if identifier_query and re.search(r"\d{4,}[_-][a-z0-9]+|\.[a-z0-9]{2,4}\b",identifier_query.group(1)) else "")
        extension=".pdf" if re.search(r"\bpdfs?\b",lower) else ""
        query=re.sub(r"\s+(?:in|on|from)\s+(?:my\s+)?(?:device|computer|pc|laptop|downloads?|documents?|desktop)\b.*$","",query,flags=re.IGNORECASE).strip()
        query=re.sub(r"\b(?:files?|documents?|pdfs?|named|called|matching|containing|filename|pattern|like|in|under|inside|on|from|my|the|all|any|device|computer|pc|laptop)\b","",query,flags=re.IGNORECASE).strip().strip('"\'.,!?')
        local_search=re.search(r"\b(?:my\s+)?(?:device|computer|pc|laptop|files?)\b",lower)
        if query or (extension and local_search):
            return RoutedRequest("find_files_all",[("find_files",{"query":query,"extension":extension})])

    # "Search Downloads" / "list what's in Downloads" means list folder contents.
    if folder and re.search(r"\b(?:list|show|search|what(?:'s| is))\b",lower):
        if re.search(r"\b(?:file|files|folder|contents|what(?:'s| is)|what files|search)\b",lower):
            return RoutedRequest("tool",[("list_files",{"directory":folder})])

    # A direct find request without an explicit location searches configured roots.
    if re.search(r"\b(?:find|search for|look for)\b.*\bresume\b",lower):
        return RoutedRequest("find_resume_all",[])

    # Explicit web-search intents use the external provider, which handles
    # relevance and common spelling correction in the query itself.
    if re.search(r"\b(?:search|look up)\b",lower) and not folder:
        m=re.search(r"\b(?:search|look up)\s+(?:the\s+)?(?:web|internet|online)\s+(?:for\s+)?(.+)",corrected,re.IGNORECASE)
        q=re.search(r"\b(?:search|look up)\s+(?:for\s+)?(.+)",corrected,re.IGNORECASE)
        query=(m.group(1) if m else q.group(1) if q else "").strip()
        if query:
            query=re.sub(r"\b(?:on the web|online|on the internet)\b","",query,flags=re.IGNORECASE).strip()
            return RoutedRequest("tool",[("web_search",{"query":query})])
    return None
