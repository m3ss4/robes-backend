from typing import Protocol, Iterable
from app.search.types import SearchResult


class SearchProvider(Protocol):
    def index_items(self, docs: Iterable[tuple[str, str]]) -> None:
        ...

    def index_outfits(self, docs: Iterable[tuple[str, str]]) -> None:
        ...

    def search_items(self, text: str, limit: int) -> SearchResult:
        ...

    def search_outfits(self, text: str, limit: int) -> SearchResult:
        ...
