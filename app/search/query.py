from typing import Iterable
from app.search.utils import normalize_text


def score_query(query: str, corpus: Iterable[tuple[str, str]]) -> list[tuple[str, float]]:
    q = normalize_text(query)
    results: list[tuple[str, float]] = []
    for doc_id, text in corpus:
        t = normalize_text(text)
        if not q:
            score = 0.0
        else:
            score = 1.0 if q in t else 0.0
        if score > 0.0:
            results.append((doc_id, score))
    return sorted(results, key=lambda x: x[1], reverse=True)
