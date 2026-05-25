from skillvitals.tokens import estimate_tokens, humanize


def test_estimate_tokens_uses_four_chars_per_token():
    assert estimate_tokens("a" * 40) == 10
    assert estimate_tokens("") == 0
    # rounds up partial tokens
    assert estimate_tokens("a" * 41) == 11


def test_humanize_thousands():
    assert humanize(2100) == "2.1k"
    assert humanize(950) == "950"
    assert humanize(0) == "0"
    assert humanize(1000) == "1.0k"
    assert humanize(12345) == "12.3k"
