class RuleBasedStrategy:
    name = "rules"

    def recommend(self, _user_id: str) -> list[tuple[str, float]]:
        return []
