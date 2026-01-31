from typing import Protocol


class Strategy(Protocol):
    name: str

    def recommend(self, user_id: str) -> list[tuple[str, float]]:
        ...
