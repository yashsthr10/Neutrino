from pkg.parser import parse_request


def handle(raw: str) -> list[str]:
    return parse_request(raw)


class Router:
    def parse_request(self, raw: str) -> list[str]:
        return parse_request(raw)
