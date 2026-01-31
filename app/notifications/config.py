from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationsConfig:
    provider: str = "log"
