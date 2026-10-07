"""Small, rate-limited SEC HTTPS client. No paid services or credentials."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests


class SecAccessError(RuntimeError):
    """An actionable SEC access failure, safe to display to the user."""


class SecClient:
    _lock = threading.Lock()
    _last_request = 0.0
    MAX_BYTES = 64 * 1024 * 1024
    CACHE_LIMIT = 250 * 1024 * 1024

    def __init__(self, user_agent: str, cache_dir: Path | None = None):
        # SEC requests must identify the application and a real contact.
        if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", user_agent or ""):
            raise ValueError("Enter your contact email in Settings before requesting SEC data.")
        if len(user_agent) > 250 or any(c in user_agent for c in "\r\n"):
            raise ValueError("The SEC contact must fit on a single short line.")
        try:
            user_agent.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("Use a name and email with Latin characters for the SEC request header.") from None
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[1] / "data" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"FinancialHistorian/0.1 {user_agent}",
            "Accept-Encoding": "gzip, deflate",
        })

    @staticmethod
    def _validate_url(url: str) -> None:
        u = urlsplit(url)
        if (u.scheme != "https" or u.hostname not in {"www.sec.gov", "data.sec.gov"}
                or u.username or u.password or u.port not in {None, 443}):
            raise ValueError("Only official SEC HTTPS sources are supported.")

    @classmethod
    def _pace(cls) -> None:
        # Global across client instances: at most five requests per second,
        # below SEC's ten requests/second limit. Requests are sequential.
        with cls._lock:
            delay = 0.2 - (time.monotonic() - cls._last_request)
            if delay > 0:
                time.sleep(delay)
            cls._last_request = time.monotonic()

    def _prune_cache(self) -> None:
        entries = []
        for p in self.cache_dir.glob("*.cache"):
            try:
                s = p.stat()
                entries.append((s.st_mtime, s.st_size, p))
            except FileNotFoundError:
                pass
        total = sum(s for _, s, _ in entries)
        for _, size, path in sorted(entries):
            if total <= self.CACHE_LIMIT:
                break
            try:
                path.unlink(missing_ok=True)
                total -= size
            except OSError:
                pass

    def get_bytes(self, url: str, ttl: int = 86400, refresh: bool = False) -> bytes:
        self._validate_url(url)
        cache = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".cache")
        if not refresh and cache.exists() and time.time() - cache.stat().st_mtime < ttl:
            return cache.read_bytes()
        current_url = url
        for redirect in range(4):
            self._validate_url(current_url)
            response = None
            for attempt in range(3):
                self._pace()
                try:
                    response = self.session.get(current_url, timeout=(15, 60),
                                                allow_redirects=False, stream=True)
                except requests.RequestException as exc:
                    # Never reflect proxy settings, request headers, or identity.
                    raise SecAccessError(
                        "Cannot reach the SEC. Check your internet connection and allow "
                        "data.sec.gov and www.sec.gov through the firewall. Try again later."
                    ) from None
                if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                retry = response.headers.get("Retry-After", "")
                wait = min(float(retry), 20.0) if retry.isdigit() else 2 ** (attempt + 1)
                response.close()
                time.sleep(wait)
            assert response is not None
            if response.status_code in {301, 302, 303, 307, 308}:
                destination = response.headers.get("Location")
                response.close()
                if not destination:
                    raise SecAccessError("The SEC returned an incomplete redirect. Try again later.")
                current_url = urljoin(current_url, destination)
                continue
            if response.status_code in {403, 429}:
                response.close()
                raise SecAccessError(
                    "The SEC refused this request. Check your SEC contact email in Settings "
                    "and network access, then wait a few minutes before trying again. "
                    "The SEC sometimes limits automated requests."
                )
            if response.status_code == 404:
                response.close()
                raise SecAccessError("The requested SEC record is unavailable (404).")
            if response.status_code != 200:
                status = response.status_code
                response.close()
                raise SecAccessError(f"The SEC returned HTTP {status}. Please try again later.")
            try:
                blocks = []
                total = 0
                for block in response.iter_content(128 * 1024):
                    total += len(block)
                    if total > self.MAX_BYTES:
                        raise SecAccessError("This SEC document exceeds the 64 MB safety limit; review it manually.")
                    blocks.append(block)
                data = b"".join(blocks)
            except requests.RequestException:
                raise SecAccessError("The SEC download was interrupted. Please try again.") from None
            finally:
                response.close()
            temporary = cache.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                temporary.write_bytes(data)
                temporary.replace(cache)
                self._prune_cache()
            finally:
                temporary.unlink(missing_ok=True)
            return data
        raise SecAccessError("The SEC returned too many redirects. Please try again later.")

    def get_json(self, url: str, ttl: int = 86400, refresh: bool = False) -> dict:
        try:
            payload = json.loads(self.get_bytes(url, ttl, refresh))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SecAccessError("The SEC returned an unreadable response instead of financial data.") from None
        if not isinstance(payload, dict):
            raise SecAccessError("The SEC returned an unexpected data format.")
        return payload
