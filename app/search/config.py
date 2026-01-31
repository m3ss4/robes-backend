from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    provider: str = "memory"
    max_results: int = 20
