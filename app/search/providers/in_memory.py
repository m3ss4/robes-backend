from typing import Iterable
import time
from app.search.index import SearchIndex
from app.search.query import score_query
from app.search.types import SearchResult, SearchHit


class InMemorySearchProvider:
    def __init__(self) -> None:
        self._items = SearchIndex()
        self._outfits = SearchIndex()

    def index_items(self, docs: Iterable[tuple[str, str]]) -> None:
        self._items.bulk_upsert(docs)

    def index_outfits(self, docs: Iterable[tuple[str, str]]) -> None:
        self._outfits.bulk_upsert(docs)

    def search_items(self, text: str, limit: int) -> SearchResult:
        start = time.time()
        hits = score_query(text, self._items.all_docs().items())[:limit]
        return SearchResult([SearchHit(id=h[0], score=h[1]) for h in hits], int((time.time() - start) * 1000))

    def search_outfits(self, text: str, limit: int) -> SearchResult:
        start = time.time()
        hits = score_query(text, self._outfits.all_docs().items())[:limit]
        return SearchResult([SearchHit(id=h[0], score=h[1]) for h in hits], int((time.time() - start) * 1000))
