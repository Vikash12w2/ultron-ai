def web_search(query):
    if not query.strip(): raise ValueError("Search query cannot be empty.")
    try: from ddgs import DDGS
    except ImportError as exc: raise RuntimeError("Web search needs ddgs. No search was sent; install dependencies to enable this feature.") from exc
    return [{"title":r.get("title",""),"url":r.get("href",""),"snippet":r.get("body","")} for r in DDGS().text(query,max_results=6)]
