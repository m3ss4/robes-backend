def validate_query(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError("query must be a string")
