"""Small, dependency-free fuzzy matching helpers for short search terms."""
from difflib import SequenceMatcher
import re


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def similar_word(value: str, candidate: str, threshold: float = 0.70) -> bool:
    value, candidate = normalize(value), normalize(candidate)
    if not value or not candidate:
        return False
    if value == candidate:
        return True
    if min(len(value), len(candidate)) < 4 or abs(len(value)-len(candidate)) > max(1, len(candidate)//3):
        return False
    score=SequenceMatcher(None, value, candidate).ratio()
    if value.isdigit() and candidate.isdigit():
        return score >= 0.85
    return score >= threshold


def phrase_in_text(text: str, phrase: str, threshold: float = 0.70) -> bool:
    words=normalize(text).split()
    targets=normalize(phrase).split()
    if not targets:
        return False
    # Join adjacent tokens too, so "you tube" and "you-tube" can match YouTube.
    for start in range(len(words)):
        for size in range(1, min(4, len(words)-start)+1):
            chunk="".join(words[start:start+size])
            target="".join(targets)
            if similar_word(chunk,target,threshold):
                return True
    return False


def fuzzy_contains(name: str, query: str) -> bool:
    """Match every query word against a filename, allowing small spelling errors."""
    name_words=normalize(name).split()
    query_words=normalize(query).split()
    if not query_words:
        return True
    joined_name="".join(name_words)
    joined_query="".join(query_words)
    if joined_query in joined_name:
        return True
    return all(any(similar_word(word,part) for part in name_words) for word in query_words)


def correct_known_terms(text: str, vocabulary: set[str]) -> str:
    """Correct only command/entity keywords, leaving arbitrary query terms alone."""
    def replace(match):
        token=match.group(0)
        best=max(vocabulary,key=lambda word:SequenceMatcher(None,token.casefold(),word).ratio())
        score=SequenceMatcher(None,token.casefold(),best).ratio()
        if token.casefold()==best:
            return token
        if len(token)>=4 and score>=0.70 and abs(len(token)-len(best))<=max(1,len(best)//3):
            return best
        return token
    return re.sub(r"[A-Za-z0-9]+",replace,text)
