import os
from app.search.config import SearchConfig
from app.search.providers.in_memory import InMemorySearchProvider
from app.search.providers.postgres import PostgresSearchProvider


class SearchService:
    def __init__(self, config: SearchConfig | None = None) -> None:
        self.config = config or SearchConfig(provider=os.getenv("SEARCH_PROVIDER", "memory"))
        if self.config.provider == "postgres":
            self.provider = PostgresSearchProvider()
        else:
            self.provider = InMemorySearchProvider()

    def search_items(self, text: str, limit: int | None = None):
        return self.provider.search_items(text, limit or self.config.max_results)

    def search_outfits(self, text: str, limit: int | None = None):
        return self.provider.search_outfits(text, limit or self.config.max_results)
