_CACHE: dict[str, list[tuple[str, float]]] = {}


def get_cache(key: str):
    return _CACHE.get(key)


def set_cache(key: str, value: list[tuple[str, float]]):
    _CACHE[key] = value
