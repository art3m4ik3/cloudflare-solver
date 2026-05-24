import asyncio
import inspect
import logging
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from playwright.async_api import Page
from camoufox.async_api import AsyncCamoufox
from browserforge.fingerprints import Screen

logger = logging.getLogger(__name__)

SolveResult = Union["CloudflareCookie", "TurnstileToken"]
# Callback receives (url, result_or_none). Can be sync or async.
Callback = Callable[[str, Optional[SolveResult]], Union[None, Awaitable[None]]]


class ChallengeType(Enum):
    """Enum for Cloudflare challenge types."""

    CHALLENGE = "challenge"
    TURNSTILE = "turnstile"


@dataclass
class CloudflareCookie:
    """Dataclass representing Cloudflare challenge cookie."""

    name: str
    value: str
    domain: str
    path: str
    expires: int
    http_only: bool
    secure: bool
    same_site: str

    def __post_init__(self) -> None:
        if not self.name or not self.value:
            raise ValueError("Cookie name and value must be set")

    @classmethod
    def from_json(cls, cookie_data: Dict[str, Any]) -> "CloudflareCookie":
        return cls(
            name=cookie_data.get("name", ""),
            value=cookie_data.get("value", ""),
            domain=cookie_data.get("domain", ""),
            path=cookie_data.get("path", "/"),
            expires=cookie_data.get("expires", 0),
            http_only=cookie_data.get("httpOnly", False),
            secure=cookie_data.get("secure", False),
            same_site=cookie_data.get("sameSite", "Lax"),
        )


@dataclass
class TurnstileToken:
    """Dataclass representing Cloudflare Turnstile token."""

    token: str

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("Token must be set")


# ─── Cache ────────────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    result: SolveResult
    expires_at: float  # monotonic time


class ChallengeCache:
    """In-memory cache for solved challenges keyed by (domain, challenge_type).

    For Challenge type, TTL is derived from the cf_clearance cookie's own
    expiry timestamp when available. For Turnstile and fallback cases,
    ``default_ttl`` (seconds) is used.

    Example::

        cache = ChallengeCache(default_ttl=1800)
        solver = CloudflareSolver(cache=cache)
    """

    def __init__(self, default_ttl: float = 1800.0) -> None:
        self.default_ttl = default_ttl
        self._store: Dict[Tuple[str, str], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(
        self, domain: str, challenge_type: ChallengeType
    ) -> Optional[SolveResult]:
        """Return cached result if still valid, otherwise None."""
        async with self._lock:
            key = (domain, challenge_type.value)
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                del self._store[key]
                logger.debug("Cache expired for %s [%s]", domain, challenge_type.value)
                return None
            return entry.result

    async def set(
        self,
        domain: str,
        challenge_type: ChallengeType,
        result: SolveResult,
        ttl: Optional[float] = None,
    ) -> None:
        """Store result. TTL is auto-computed from cookie expiry when not given."""
        async with self._lock:
            if ttl is None:
                if isinstance(result, CloudflareCookie) and result.expires > 0:
                    ttl = max(0.0, result.expires - time.time())
                else:
                    ttl = self.default_ttl
            key = (domain, challenge_type.value)
            self._store[key] = _CacheEntry(
                result=result,
                expires_at=time.monotonic() + ttl,
            )
            logger.debug(
                "Cached %s for %s (ttl=%.0fs)", challenge_type.value, domain, ttl
            )

    async def invalidate(
        self, domain: str, challenge_type: Optional[ChallengeType] = None
    ) -> None:
        """Invalidate cache for a domain (optionally only one challenge type)."""
        async with self._lock:
            if challenge_type is not None:
                self._store.pop((domain, challenge_type.value), None)
            else:
                for key in [k for k in self._store if k[0] == domain]:
                    del self._store[key]

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# ─── Browser Pool ─────────────────────────────────────────────────────────────


class BrowserPool:
    """Pool of pre-warmed Camoufox browser instances.

    Keeps ``size`` browsers alive and hands them out to concurrent solvers,
    eliminating the cold-start overhead of launching a new browser per request.

    Usage as async context manager (recommended)::

        async with BrowserPool(size=3, headless=True) as pool:
            solver = CloudflareSolver(pool=pool)
            result = await solver.solve(url)

    Or manual lifecycle::

        pool = BrowserPool(size=3)
        await pool.start()
        solver = CloudflareSolver(pool=pool)
        ...
        await pool.stop()
    """

    def __init__(
        self,
        size: int = 3,
        headless: bool = True,
        os: Optional[List[str]] = None,
        proxy: Optional[str] = None,
        screen: Optional[Screen] = None,
    ) -> None:
        self.size = size
        self._camoufox_kwargs: Dict[str, Any] = dict(
            headless=headless,
            os=os or ["windows"],
            screen=screen or Screen(max_width=1920, max_height=1080),
            proxy={"server": proxy} if proxy else None,
        )
        self._queue: asyncio.Queue = asyncio.Queue()
        self._cms: List[AsyncCamoufox] = []
        self._started = False

    async def start(self) -> None:
        """Launch all browser instances in the pool."""
        if self._started:
            return
        for _ in range(self.size):
            cm = AsyncCamoufox(**self._camoufox_kwargs)
            browser = await cm.__aenter__()
            self._cms.append(cm)
            await self._queue.put(browser)
        self._started = True
        logger.debug("BrowserPool started with %d browsers", self.size)

    async def stop(self) -> None:
        """Close all browser instances."""
        for cm in self._cms:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._cms.clear()
        self._started = False
        logger.debug("BrowserPool stopped")

    @asynccontextmanager
    async def acquire(self):
        """Async context manager that checks out a browser, then returns it."""
        browser = await self._queue.get()
        try:
            yield browser
        finally:
            await self._queue.put(browser)

    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _invoke(cb: Optional[Callback], url: str, result: Optional[SolveResult]) -> None:
    """Call a callback that may be sync or async."""
    if cb is None:
        return
    ret = cb(url, result)
    if inspect.isawaitable(ret):
        await ret


# ─── Solver ───────────────────────────────────────────────────────────────────


class CloudflareSolver:
    """Solver for Cloudflare anti-bot challenges.

    Parameters
    ----------
    challenge_type:
        Type of challenge — ``ChallengeType.CHALLENGE`` (cookie) or
        ``ChallengeType.TURNSTILE`` (token).
    sleep_time:
        Seconds to wait before clicking the challenge checkbox.
    headless:
        Run browser in headless mode. Ignored when ``pool`` is provided.
    os:
        OS fingerprint list (e.g. ``["windows"]``, ``["macos"]``, ``["linux"]``).
        Ignored when ``pool`` is provided.
    debug:
        Enable verbose logging and save failure screenshots.
    retries:
        Number of polling attempts when looking for the challenge frame / token.
    proxy:
        Proxy URL ``"http://user:pass@host:port"`` or ``"http://host:port"``.
        Ignored when ``pool`` is provided (configure proxy on the pool instead).
    pool:
        Pre-warmed :class:`BrowserPool`. When supplied, no new browser is
        launched per call — a pooled instance is borrowed instead.
    cache:
        :class:`ChallengeCache` instance for result reuse. When supplied,
        a successful result is stored and returned on subsequent calls for the
        same domain without launching a browser.
    on_success:
        Callable ``(url, result)`` invoked after every successful solve
        (including cache hits). May be a coroutine function.
    on_failure:
        Callable ``(url, exc_or_none)`` invoked when solving fails or times out.
        May be a coroutine function.
    timeout:
        Total seconds allowed for a single :meth:`solve` call. ``None`` means
        no limit.
    """

    def __init__(
        self,
        challenge_type: ChallengeType = ChallengeType.CHALLENGE,
        sleep_time: int = 5,
        headless: bool = True,
        os: Optional[List[str]] = None,
        debug: bool = False,
        retries: int = 30,
        proxy: Optional[str] = None,
        pool: Optional[BrowserPool] = None,
        cache: Optional[ChallengeCache] = None,
        on_success: Optional[Callback] = None,
        on_failure: Optional[Callback] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.challenge_type = challenge_type
        self.sleep_time = sleep_time
        self.headless = headless
        self.os = os or ["windows"]
        self.debug = debug
        self.retries = retries
        self.proxy = proxy
        self.pool = pool
        self.cache = cache
        self.on_success = on_success
        self.on_failure = on_failure
        self.timeout = timeout

        if debug:
            logging.basicConfig(level=logging.DEBUG)

    async def _human_click(self, page: Page, x: float, y: float) -> None:
        """Move mouse to coordinates with random jitter and click."""
        target_x = x + random.uniform(-5, 5)
        target_y = y + random.uniform(-5, 5)
        await page.mouse.move(target_x, target_y, steps=random.randint(10, 25))
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()

    async def _find_and_click_challenge_frame(self, page: Page) -> bool:
        """Find Cloudflare challenge frame and click the checkbox."""
        for frame in page.frames:
            if frame.url.startswith("https://challenges.cloudflare.com"):
                frame_element = await frame.frame_element()
                bounding_box = await frame_element.bounding_box()
                if not bounding_box:
                    continue
                checkbox_x = bounding_box["x"] + bounding_box["width"] / 9
                checkbox_y = bounding_box["y"] + bounding_box["height"] / 2
                await asyncio.sleep(self.sleep_time)
                await self._human_click(page, checkbox_x, checkbox_y)
                return True
        return False

    async def _get_turnstile_token(self, page: Page) -> Optional[str]:
        """Poll for Turnstile token in hidden input field."""
        try:
            for _ in range(self.retries):
                inputs = await page.query_selector_all(
                    'input[name="cf-turnstile-response"]'
                )
                for inp in inputs:
                    token = await inp.get_attribute("value")
                    if token and len(token) > 10:
                        logger.debug("Turnstile token found")
                        return token
                await asyncio.sleep(1)
            logger.debug("Turnstile token not found after %d retries", self.retries)
            return None
        except Exception as e:
            logger.error("Error extracting Turnstile token: %s", e)
            return None

    async def _solve_with_browser(
        self, browser: Any, link: str
    ) -> Optional[SolveResult]:
        """Run the solve flow inside an already-open browser instance."""
        ctx = await browser.new_context()
        try:
            page = await ctx.new_page()
            await page.goto(link)

            for _ in range(self.retries):
                if await self._find_and_click_challenge_frame(page):
                    await asyncio.sleep(1)
                    break
                await asyncio.sleep(1)

            if self.challenge_type == ChallengeType.CHALLENGE:
                cookies = await ctx.cookies()
                cf_cookie = next(
                    (c for c in cookies if c.get("name") == "cf_clearance"), None
                )
                if cf_cookie:
                    logger.debug("cf_clearance cookie found")
                    return CloudflareCookie.from_json(dict(cf_cookie))
                logger.debug("cf_clearance cookie not found")
                if self.debug:
                    await page.screenshot(path="debug_failed_challenge.png")
                return None

            else:  # TURNSTILE
                token = await self._get_turnstile_token(page)
                if token:
                    return TurnstileToken(token=token)
                logger.debug("Turnstile token not found")
                if self.debug:
                    await page.screenshot(path="debug_failed_turnstile.png")
                return None

        finally:
            await ctx.close()

    async def _do_solve(self, link: str) -> Optional[SolveResult]:
        """Dispatch to pool or create a fresh browser."""
        if self.pool is not None:
            async with self.pool.acquire() as browser:
                return await self._solve_with_browser(browser, link)
        else:
            proxy_config = {"server": self.proxy} if self.proxy else None
            async with AsyncCamoufox(
                headless=self.headless,
                os=self.os,
                screen=Screen(max_width=1920, max_height=1080),
                proxy=proxy_config,
            ) as browser:
                return await self._solve_with_browser(browser, link)

    async def solve(self, link: str) -> Optional[SolveResult]:
        """Solve Cloudflare challenge for the given URL.

        Returns :class:`CloudflareCookie`, :class:`TurnstileToken`, or ``None``
        on failure.
        """
        domain = urlparse(link).netloc

        # Cache lookup — skip browser entirely on hit
        if self.cache is not None:
            cached = await self.cache.get(domain, self.challenge_type)
            if cached is not None:
                logger.debug("Cache hit for %s", domain)
                await _invoke(self.on_success, link, cached)
                return cached

        try:
            coro = self._do_solve(link)
            if self.timeout is not None:
                result = await asyncio.wait_for(coro, timeout=self.timeout)
            else:
                result = await coro
        except asyncio.TimeoutError:
            logger.error("Timeout (%.1fs) solving challenge for %s", self.timeout, link)
            await _invoke(self.on_failure, link, None)
            return None
        except Exception as e:
            logger.error("Error solving Cloudflare challenge: %s", e)
            await _invoke(self.on_failure, link, e)
            return None

        if result is not None:
            if self.cache is not None:
                await self.cache.set(domain, self.challenge_type, result)
            await _invoke(self.on_success, link, result)
        else:
            await _invoke(self.on_failure, link, None)

        return result

    async def solve_batch(
        self,
        links: List[str],
        concurrency: Optional[int] = None,
    ) -> List[Optional[SolveResult]]:
        """Solve multiple URLs in parallel.

        Parameters
        ----------
        links:
            List of URLs to solve.
        concurrency:
            Maximum number of simultaneous solves. ``None`` or ``0`` means
            unlimited (all URLs started at once). When using a
            :class:`BrowserPool`, set this to ``pool.size`` or lower to avoid
            queuing more work than the pool can absorb at once.

        Returns
        -------
        list
            Results in the same order as ``links``. Failed entries are ``None``.

        Example::

            results = await solver.solve_batch(urls, concurrency=pool.size)
        """
        if not concurrency:
            return list(
                await asyncio.gather(*[self.solve(link) for link in links])
            )

        semaphore = asyncio.Semaphore(concurrency)

        async def _limited(link: str) -> Optional[SolveResult]:
            async with semaphore:
                return await self.solve(link)

        return list(await asyncio.gather(*[_limited(link) for link in links]))


# ─── Example usage ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    async def main() -> None:
        cache = ChallengeCache(default_ttl=1800)

        def on_success(url: str, result: Optional[SolveResult]) -> None:
            print(f"[OK] {url} -> {result}")

        def on_failure(url: str, exc: Optional[Exception]) -> None:
            print(f"[FAIL] {url} -> {exc}")

        # ── Pool + cache + callbacks example ──────────────────────────────
        async with BrowserPool(size=2, headless=False) as pool:
            solver = CloudflareSolver(
                challenge_type=ChallengeType.TURNSTILE,
                pool=pool,
                cache=cache,
                on_success=on_success,
                on_failure=on_failure,
                timeout=120,
                debug=True,
            )

            urls = [
                "https://nopecha.com/captcha/turnstile",
                "https://nopecha.com/captcha/turnstile",  # second call hits cache
            ]

            results = await solver.solve_batch(urls, concurrency=pool.size)
            for url, res in zip(urls, results):
                if res:
                    print(f"Token for {url}: {res.token[:30]}...")  # type: ignore[union-attr]

        # ── No-pool fallback (original behaviour) ─────────────────────────
        solo_solver = CloudflareSolver(
            challenge_type=ChallengeType.CHALLENGE,
            headless=False,
            debug=True,
            on_success=on_success,
            on_failure=on_failure,
        )
        result = await solo_solver.solve("https://nopecha.com/demo/cloudflare")
        if isinstance(result, CloudflareCookie):
            print(f"Cookie: {result.name}={result.value[:20]}...")

    asyncio.run(main())
