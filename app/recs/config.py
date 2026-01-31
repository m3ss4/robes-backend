from dataclasses import dataclass


@dataclass(frozen=True)
class RecsConfig:
    max_results: int = 10
    strategy: str = "rules"
