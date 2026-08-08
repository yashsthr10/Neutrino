from pkg.parser import parse_request


def test_parse_request():
    assert parse_request("a b") == ["a", "b"]
