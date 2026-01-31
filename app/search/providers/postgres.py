from typing import Iterable
from app.search.types import SearchResult


class PostgresSearchProvider:
    def index_items(self, _docs: Iterable[tuple[str, str]]) -> None:
        raise NotImplementedError("postgres search provider not wired")

    def index_outfits(self, _docs: Iterable[tuple[str, str]]) -> None:
        raise NotImplementedError("postgres search provider not wired")

    def search_items(self, _text: str, _limit: int) -> SearchResult:
        raise NotImplementedError("postgres search provider not wired")

    def search_outfits(self, _text: str, _limit: int) -> SearchResult:
        raise NotImplementedError("postgres search provider not wired")
