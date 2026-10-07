"""SEC transport checks run entirely against mocked HTTP responses."""
from __future__ import annotations

import hashlib
import os

import pytest
import requests

from financial_historian import sec_client
from financial_historian.sec_client import SecAccessError, SecClient


URL = "https://data.sec.gov/submissions/CIK0000000001.json"


class Response:
    def __init__(self, body=b'{"ok": true}', status=200, headers=None, chunks=None):
        self.body = body
        self.status_code = status
        self.headers = headers or {}
        self.chunks = chunks
        self.closed = False

    def iter_content(self, _size):
        yield from self.chunks if self.chunks is not None else [self.body]

    def close(self):
        self.closed = True


@pytest.fixture
def clock(monkeypatch):
    state = {"now": 1000.0, "sleeps": []}

    def sleep(seconds):
        state["sleeps"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(sec_client.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(sec_client.time, "sleep", sleep)
    monkeypatch.setattr(SecClient, "_last_request", 0.0)
    return state


@pytest.fixture
def client(tmp_path, clock):
    # This identity is only used with mocked requests and is never sent externally.
    return SecClient("Unit tests fixture@example.test", tmp_path / "cache")


def respond(monkeypatch, client, responses):
    pending = iter(responses)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        result = next(pending)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client.session, "get", get)
    return calls


def cache_path(client, url=URL):
    return client.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".cache")


@pytest.mark.parametrize("url", [
    "http://data.sec.gov/submissions/CIK1.json",
    "https://sec.gov.evil.test/record",
    "https://example.test/record",
    "https://data.sec.gov:8443/record",
    "https://user:secret@data.sec.gov/record",
    "file:///tmp/record",
])
def test_external_or_non_https_source_is_rejected_before_request(client, monkeypatch, url):
    calls = respond(monkeypatch, client, [])
    with pytest.raises(ValueError, match="official SEC HTTPS"):
        client.get_bytes(url)
    assert not calls


def test_tls_verification_keeps_requests_default_and_identifying_header(client, monkeypatch):
    calls = respond(monkeypatch, client, [Response()])
    assert client.get_json(URL) == {"ok": True}
    assert client.session.verify is True
    assert calls[0][1].get("verify", True) is True
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["timeout"] == (15, 60)
    assert "FinancialHistorian" in client.session.headers["User-Agent"]


def test_pacing_applies_across_separate_clients(tmp_path, clock):
    first = SecClient("Fixture first@example.test", tmp_path / "first")
    second = SecClient("Fixture second@example.test", tmp_path / "second")
    first._pace()
    second._pace()
    first._pace()
    assert clock["sleeps"] == pytest.approx([0.2, 0.2])
    assert clock["now"] == pytest.approx(1000.4)


def test_fresh_cache_reuses_bytes_and_refresh_replaces_atomically(client, monkeypatch):
    original, refreshed = Response(b"original"), Response(b"newer")
    calls = respond(monkeypatch, client, [original, refreshed])
    assert client.get_bytes(URL) == b"original"
    assert client.get_bytes(URL) == b"original"
    assert len(calls) == 1
    assert client.get_bytes(URL, refresh=True) == b"newer"
    assert client.get_bytes(URL) == b"newer"
    assert len(calls) == 2
    assert original.closed and refreshed.closed
    assert not list(client.cache_dir.glob("*.tmp"))


def test_expired_cache_fetches_again(client, monkeypatch):
    calls = respond(monkeypatch, client, [Response(b"old"), Response(b"updated")])
    client.get_bytes(URL)
    old_time = sec_client.time.time() - 100
    os.utime(cache_path(client), (old_time, old_time))
    assert client.get_bytes(URL, ttl=10) == b"updated"
    assert len(calls) == 2


def test_cache_evicts_oldest_entries_and_new_data_is_repeatable(client, monkeypatch):
    monkeypatch.setattr(client, "CACHE_LIMIT", 12)
    oldest = client.cache_dir / "old.cache"
    newer = client.cache_dir / "new.cache"
    oldest.write_bytes(b"12345")
    newer.write_bytes(b"abcde")
    os.utime(oldest, (1, 1))
    os.utime(newer, (2, 2))
    calls = respond(monkeypatch, client, [Response(b"fresh")])
    assert client.get_bytes(URL) == b"fresh"
    assert not oldest.exists()
    assert newer.exists()
    assert sum(p.stat().st_size for p in client.cache_dir.glob("*.cache")) <= 12
    assert client.get_bytes(URL) == b"fresh"
    assert len(calls) == 1


def test_transient_server_and_rate_limit_responses_retry_then_succeed(client, monkeypatch, clock):
    unavailable = Response(status=503)
    rate_limit = Response(status=429, headers={"Retry-After": "1"})
    success = Response(b"retrieved")
    calls = respond(monkeypatch, client, [unavailable, rate_limit, success])
    assert client.get_bytes(URL) == b"retrieved"
    assert len(calls) == 3
    assert all(r.closed for r in (unavailable, rate_limit, success))
    assert clock["sleeps"] == [2, 1]


def test_exhausted_retry_is_bounded_and_does_not_create_cache(client, monkeypatch):
    responses = [Response(status=503) for _ in range(3)]
    calls = respond(monkeypatch, client, responses)
    with pytest.raises(SecAccessError, match="HTTP 503"):
        client.get_bytes(URL)
    assert len(calls) == 3
    assert all(r.closed for r in responses)
    assert not cache_path(client).exists()


def test_network_error_does_not_expose_proxy_credentials_or_contact(client, monkeypatch):
    secret_error = requests.exceptions.ProxyError(
        "Failed proxy https://username:password@proxy.example.test; contact fixture@example.test"
    )
    respond(monkeypatch, client, [secret_error])
    with pytest.raises(SecAccessError) as caught:
        client.get_bytes(URL)
    message = str(caught.value)
    assert "Cannot reach the SEC" in message
    assert "data.sec.gov" in message
    assert all(private not in message for private in ("username", "password", "proxy.example.test", "fixture@example.test"))


@pytest.mark.parametrize("status, message", [(403, "SEC refused"), (404, "unavailable (404)"), (418, "HTTP 418")])
def test_permanent_failures_have_actionable_safe_messages(client, monkeypatch, status, message):
    response = Response(status=status)
    calls = respond(monkeypatch, client, [response])
    with pytest.raises(SecAccessError) as caught:
        client.get_bytes(URL)
    assert message in str(caught.value)
    assert "fixture@example.test" not in str(caught.value)
    assert response.closed
    assert len(calls) == 1


def test_sec_redirect_is_followed_but_remains_https_and_explicit(client, monkeypatch):
    redirect = Response(status=302, headers={"Location": "https://www.sec.gov/files/company_tickers.json"})
    success = Response(b"official")
    calls = respond(monkeypatch, client, [redirect, success])
    assert client.get_bytes(URL) == b"official"
    assert [url for url, _ in calls] == [URL, "https://www.sec.gov/files/company_tickers.json"]
    assert all(kwargs["allow_redirects"] is False for _, kwargs in calls)
    assert redirect.closed and success.closed


@pytest.mark.parametrize("destination", ["https://evil.example.test/steal", "http://www.sec.gov/files/data", "https://name:secret@www.sec.gov/record"])
def test_external_redirect_is_rejected_before_contacting_target(client, monkeypatch, destination):
    redirect = Response(status=302, headers={"Location": destination})
    calls = respond(monkeypatch, client, [redirect])
    with pytest.raises(ValueError, match="official SEC HTTPS"):
        client.get_bytes(URL)
    assert len(calls) == 1
    assert redirect.closed
    assert not cache_path(client).exists()


def test_oversized_stream_is_closed_without_caching_partial_bytes(client, monkeypatch):
    monkeypatch.setattr(client, "MAX_BYTES", 8)
    response = Response(chunks=[b"12345", b"67890"])
    respond(monkeypatch, client, [response])
    with pytest.raises(SecAccessError, match="safety limit"):
        client.get_bytes(URL)
    assert response.closed
    assert not cache_path(client).exists()


def test_interrupted_stream_does_not_expose_exception_or_cache_partial_data(client, monkeypatch):
    response = Response()

    def interrupted(_):
        yield b"partial"
        raise requests.ConnectionError("password in private proxy URL")

    monkeypatch.setattr(response, "iter_content", interrupted)
    respond(monkeypatch, client, [response])
    with pytest.raises(SecAccessError, match="download was interrupted") as caught:
        client.get_bytes(URL)
    assert "password" not in str(caught.value)
    assert response.closed
    assert not cache_path(client).exists()


@pytest.mark.parametrize("body, message", [(b"<html>blocked</html>", "unreadable"), (b"[1, 2]", "unexpected data format")])
def test_bad_json_is_reported_without_treating_it_as_financial_data(client, monkeypatch, body, message):
    respond(monkeypatch, client, [Response(body)])
    with pytest.raises(SecAccessError, match=message):
        client.get_json(URL)


@pytest.mark.parametrize("identity", ["", "Financial Historian", "user@example.test\r\nInjected: header"])
def test_invalid_contact_identity_is_rejected_before_session_use(tmp_path, identity):
    with pytest.raises(ValueError):
        SecClient(identity, tmp_path / "cache")
