"""HTTP-laag: identificeert zich eerlijk, volgt robots.txt, en stopt bij een blokkade."""
from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from .robots import RobotRules

USER_AGENT = "bmw-x1-marktoverzicht/0.1 (persoonlijk gebruik)"
ROBOTS_TOKEN = "bmw-x1-marktoverzicht"


class BlockedError(Exception):
    """De site weigert ons. We stoppen met deze site en proberen dit niet te omzeilen."""


class RequestLimitReached(Exception):
    pass


@dataclass
class Page:
    status: int
    url: str
    text: str


class Fetcher:
    def __init__(self, delay: float = 3.0, max_requests: int = 800, timeout: float = 45.0):
        self.delay = delay
        self.max_requests = max_requests
        self.timeout = timeout
        self.requests = 0
        self.skipped_by_robots: list[str] = []
        self._robots: dict[str, RobotRules | None] = {}
        self._last_request: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        elapsed = time.monotonic() - self._last_request.get(host, -1e9)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request[host] = time.monotonic()

    def _raw(self, url: str) -> Page:
        host = urlsplit(url).netloc
        self._wait(host)
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl-NL,nl;q=0.9",
            "Accept-Encoding": "gzip",
        })
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status, final = response.status, response.geturl()
        except urllib.error.HTTPError as error:
            body, status, final = error.read(), error.code, url
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return Page(status, final, body.decode("utf-8", "replace"))

    def _rules(self, url: str) -> RobotRules | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            try:
                page = self._raw(origin + "/robots.txt")
            except (urllib.error.URLError, TimeoutError) as error:
                raise BlockedError(f"robots.txt niet leesbaar: {error}") from error
            if page.status >= 500:
                raise BlockedError(f"robots.txt gaf HTTP {page.status}")
            if page.status in (401, 403):
                raise BlockedError(f"robots.txt gaf HTTP {page.status}")
            self._robots[origin] = RobotRules(page.text, ROBOTS_TOKEN) if page.status == 200 else None
        return self._robots[origin]

    def get(self, url: str) -> Page | None:
        """Haalt een pagina op. None = niet toegestaan door robots.txt of niet gevonden."""
        rules = self._rules(url)
        parts = urlsplit(url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        if rules and not rules.allowed(target):
            self.skipped_by_robots.append(url)
            return None
        if self.requests >= self.max_requests:
            raise RequestLimitReached(f"limiet van {self.max_requests} verzoeken bereikt")

        for attempt in range(3):
            self.requests += 1
            try:
                page = self._raw(url)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(10 * (attempt + 1))
                continue
            if page.status in (401, 403):
                raise BlockedError(f"HTTP {page.status} op {url}")
            if page.status in (429, 503):
                if attempt == 2:
                    raise BlockedError(f"HTTP {page.status} bleef terugkomen op {url}")
                time.sleep(60 * (attempt + 1))
                continue
            if page.status >= 500:
                if attempt == 2:
                    raise BlockedError(f"HTTP {page.status} bleef terugkomen op {url}")
                time.sleep(10 * (attempt + 1))
                continue
            return page if page.status == 200 else None
        return None
