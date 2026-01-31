from typing import Iterable, Dict


class SearchIndex:
    def __init__(self) -> None:
        self._docs: Dict[str, str] = {}

    def upsert(self, doc_id: str, text: str) -> None:
        self._docs[doc_id] = text

    def bulk_upsert(self, docs: Iterable[tuple[str, str]]) -> None:
        for doc_id, text in docs:
            self._docs[doc_id] = text

    def all_docs(self) -> Dict[str, str]:
        return dict(self._docs)
