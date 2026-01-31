from app.services.search import SearchService
from app.services.search.indexer import rebuild_indexes


if __name__ == "__main__":
    rebuild_indexes(SearchService())
    print("search indexes rebuilt")
