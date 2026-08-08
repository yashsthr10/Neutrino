def parse_request(raw: str) -> list[str]:
    if raw is None:
        return []
    return raw.strip().split()


def unused_helper() -> None:
    pass
