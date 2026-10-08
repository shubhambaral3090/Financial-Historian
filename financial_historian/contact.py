"""Tab-session SEC contact handling. No disk persistence or logging."""
from pathlib import Path
import re

import streamlit.components.v1 as components


def validate_contact(name: str, email: str) -> str:
    name, email = name.strip(), email.strip()
    if not name or any(ord(c) < 32 or ord(c) == 127 for c in name + email):
        raise ValueError("Enter your name or organization on one line.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid contact email.")
    if len(f"{name} {email}") > 250:
        raise ValueError("Keep your name and email to 250 characters combined.")
    try:
        name.encode("latin-1")
        email.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Use a Latin-letter name and an ASCII email for the SEC HTTP header.") from None
    return f"{name} {email}"


_bridge = components.declare_component(
    "financial_historian_tab_contact", path=str(Path(__file__).with_name("contact_component")),
)


def browser_contact(contact: dict | None = None):
    """Recover this tab's contact after reload; never put identity in a URL."""
    return _bridge(contact=contact, key="sec_tab_contact", default=None)
