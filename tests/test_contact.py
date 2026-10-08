"""SEC header validation using invalid-domain identities, never live SEC calls."""
import pytest
from financial_historian.contact import validate_contact


def test_contact_strips_surrounding_space():
    assert validate_contact("  Offline Fixture  ", " offline@example.invalid ") == "Offline Fixture offline@example.invalid"


@pytest.mark.parametrize("name,email", [
    ("", "offline@example.invalid"),
    ("Offline\r\nInjected: value", "offline@example.invalid"),
    ("Offline\x00Fixture", "offline@example.invalid"),
    ("Offline Fixture", "offline@example.invalid\r\nInjected: value"),
    ("Offline Fixture", "not-an-email"),
    ("Offline Fixture", "offline@localhost"),
    ("Offline Fixture", "off line@example.invalid"),
    ("Offline Fixture", "offline@例.invalid"),
    ("東京", "offline@example.invalid"),
    ("x" * 250, "offline@example.invalid"),
])
def test_invalid_contact_cannot_become_http_header(name, email):
    with pytest.raises(ValueError):
        validate_contact(name, email)
