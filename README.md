# Cloudflare Challenge Solver

Asynchronous Python solution for bypassing Cloudflare's anti-bot challenges, supporting both **Challenge** (cookie-based) and **Turnstile** (token-based) types.

## Features

- **Dual Challenge Support** - Handles both Challenge (`cf_clearance` cookie) and Turnstile (token) types
- **Asynchronous** - Built with `asyncio` and `Playwright` for high performance
- **Stealthy** - Uses Camoufox and BrowserForge for realistic browser fingerprinting
- **Browser Pool** - Pre-warmed browser pool eliminates cold-start overhead for high-throughput workloads
- **Smart Cache** - TTL-aware result cache keyed by domain; auto-derives TTL from `cf_clearance` cookie expiry
- **Batch Solving** - `solve_batch()` solves multiple URLs in parallel with optional concurrency cap
- **Callbacks** - `on_success` / `on_failure` hooks (sync or async) for easy pipeline integration
- **Timeout** - Per-call timeout via `asyncio.wait_for`
- **Modular** - Clean OOP design; all features are opt-in and composable
- **Configurable** - Customize retries, delays, OS fingerprint, and more
- **Logging** - Built-in debug logging for troubleshooting
- **Security** - Proxy support and humanization

## Installation

1. Install the package dependencies:

```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:

```bash
playwright install
```

## Usage

### Basic Example - Challenge Type (Cookie)

```python
from main import CloudflareSolver, ChallengeType
import asyncio

async def main():
    solver = CloudflareSolver(
        challenge_type=ChallengeType.CHALLENGE,
        headless=True,
        os=["windows"],
    )

    result = await solver.solve("https://nopecha.com/demo/cloudflare")

    if result:
        print(f"Cookie obtained: {result.name}={result.value}")
    else:
        print("Failed to solve Cloudflare challenge")

asyncio.run(main())
```

### Basic Example - Turnstile Type (Token)

```python
from main import CloudflareSolver, ChallengeType
import asyncio

async def main():
    solver = CloudflareSolver(
        challenge_type=ChallengeType.TURNSTILE,
        headless=True,
        os=["windows"],
    )

    result = await solver.solve("https://nopecha.com/captcha/turnstile")

    if result:
        print(f"Token obtained: {result.token}")
    else:
        print("Failed to solve Turnstile challenge")

asyncio.run(main())
```

### Proxy Usage

```python
from main import CloudflareSolver, ChallengeType
import asyncio

async def main():
    # "http://user:pass@host:port" || "http://host:port"
    proxy_url = "http://user:password@123.45.67.89:8080"

    solver = CloudflareSolver(
        challenge_type=ChallengeType.CHALLENGE,
        proxy=proxy_url,
        headless=True
    )

    result = await solver.solve("https://nopecha.com/demo/cloudflare")

    if result:
        print(f"Success! Cookie: {result.value[:20]}...")

asyncio.run(main())
```

### Browser Pool

Keep `N` browsers alive and reuse them across requests — no cold-start per call:

```python
from main import CloudflareSolver, ChallengeType, BrowserPool
import asyncio

async def main():
    async with BrowserPool(size=3, headless=True, os=["windows"]) as pool:
        solver = CloudflareSolver(
            challenge_type=ChallengeType.TURNSTILE,
            pool=pool,
        )
        result = await solver.solve("https://nopecha.com/captcha/turnstile")

asyncio.run(main())
```

> When `pool` is set, `headless`, `os`, and `proxy` on `CloudflareSolver` are ignored — configure them on `BrowserPool` instead.

### Cache (TTL-aware)

Avoid re-solving the same domain while a result is still valid. For Challenge type, TTL is auto-computed from the cookie's own expiry:

```python
from main import CloudflareSolver, ChallengeType, ChallengeCache
import asyncio

async def main():
    cache = ChallengeCache(default_ttl=1800)  # 30 min fallback TTL

    solver = CloudflareSolver(
        challenge_type=ChallengeType.CHALLENGE,
        cache=cache,
        headless=True,
    )

    # First call: hits the browser
    result1 = await solver.solve("https://nopecha.com/demo/cloudflare")
    # Second call: returned from cache instantly
    result2 = await solver.solve("https://nopecha.com/demo/cloudflare")

    # Manual invalidation when needed
    await cache.invalidate("nopecha.com")

asyncio.run(main())
```

### Batch Solving

Solve multiple URLs concurrently; results are returned in the same order as the input:

```python
from main import CloudflareSolver, ChallengeType, BrowserPool
import asyncio

async def main():
    urls = [
        "https://site-a.com/page",
        "https://site-b.com/page",
        "https://site-c.com/page",
    ]

    async with BrowserPool(size=3, headless=True) as pool:
        solver = CloudflareSolver(
            challenge_type=ChallengeType.CHALLENGE,
            pool=pool,
        )
        # concurrency=pool.size prevents over-saturating the pool
        results = await solver.solve_batch(urls, concurrency=pool.size)

    for url, result in zip(urls, results):
        if result:
            print(f"{url} -> {result.value[:20]}...")

asyncio.run(main())
```

### Callbacks (on_success / on_failure)

Plug into any pipeline with sync or async callbacks:

```python
from main import CloudflareSolver, ChallengeType, SolveResult
from typing import Optional
import asyncio

# Sync callback
def log_success(url: str, result: Optional[SolveResult]) -> None:
    print(f"[OK] {url}")

# Async callback
async def alert_failure(url: str, exc: Optional[Exception]) -> None:
    await some_alerting_service.notify(f"Failed: {url}, reason: {exc}")

solver = CloudflareSolver(
    challenge_type=ChallengeType.TURNSTILE,
    on_success=log_success,
    on_failure=alert_failure,
)

asyncio.run(solver.solve("https://nopecha.com/captcha/turnstile"))
```

### All Features Combined

```python
from main import CloudflareSolver, ChallengeType, BrowserPool, ChallengeCache, SolveResult
from typing import Optional
import asyncio

async def main():
    cache = ChallengeCache(default_ttl=1800)

    def on_success(url: str, result: Optional[SolveResult]) -> None:
        print(f"[OK] {url}")

    def on_failure(url: str, exc: Optional[Exception]) -> None:
        print(f"[FAIL] {url} — {exc}")

    async with BrowserPool(size=3, headless=True, proxy="http://user:pass@host:port") as pool:
        solver = CloudflareSolver(
            challenge_type=ChallengeType.CHALLENGE,
            pool=pool,
            cache=cache,
            on_success=on_success,
            on_failure=on_failure,
            timeout=60,   # seconds per solve call
            debug=True,
            retries=30,
        )
        results = await solver.solve_batch(urls, concurrency=pool.size)

asyncio.run(main())
```

### Advanced Configuration

```python
solver = CloudflareSolver(
    challenge_type=ChallengeType.TURNSTILE,  # or ChallengeType.CHALLENGE
    sleep_time=5,   # delay before clicking challenge
    headless=False, # show browser window
    os=["macos"],   # macOS fingerprint
    debug=True,     # verbose logging + failure screenshots
    retries=50,     # polling attempts for frame / token
    proxy="http://user:pass@host:port",
    timeout=90,     # abort after 90 s
)
```

## API Reference

### `ChallengeType` Enum

Defines the type of Cloudflare challenge to solve:

- `CHALLENGE` - Traditional challenge that returns `cf_clearance` cookie
- `TURNSTILE` - Turnstile challenge that returns a token from hidden input field

### `CloudflareCookie` Dataclass

Represents the Cloudflare clearance cookie (for Challenge type):

- `name`: Cookie name (typically "cf_clearance")
- `value`: Cookie value
- `domain`: Cookie domain
- `path`: Cookie path
- `expires`: Expiration timestamp
- `http_only`: HTTP Only flag
- `secure`: Secure flag
- `same_site`: SameSite policy

### `TurnstileToken` Dataclass

Represents the Turnstile token (for Turnstile type):

- `token`: Token value extracted from `cf-turnstile-response` input field

### `ChallengeCache` Class

TTL-aware in-memory result cache. Cache hits skip the browser entirely.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `default_ttl` | `float` | `1800.0` | Fallback TTL in seconds when expiry cannot be derived from the result |

**Methods:**

| Method | Description |
|--------|-------------|
| `get(domain, challenge_type)` | Return cached result or `None` if missing / expired |
| `set(domain, challenge_type, result, ttl=None)` | Store result; `ttl` auto-computed from cookie expiry when `None` |
| `invalidate(domain, challenge_type=None)` | Evict one or all challenge types for a domain |
| `clear()` | Clear all entries |

### `BrowserPool` Class

Pool of pre-warmed Camoufox browsers. Use as async context manager or call `start()`/`stop()` manually.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `size` | `int` | `3` | Number of browser instances to keep alive |
| `headless` | `bool` | `True` | Headless mode |
| `os` | `list[str]` | `["windows"]` | OS fingerprint |
| `proxy` | `str \| None` | `None` | Proxy URL |
| `screen` | `Screen \| None` | `None` | Custom screen size (BrowserForge `Screen`) |

**Methods:**

| Method | Description |
|--------|-------------|
| `start()` | Launch all browser instances |
| `stop()` | Close all browser instances |
| `acquire()` | Async context manager that checks out one browser from the pool |

### `CloudflareSolver` Class

#### Parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `challenge_type` | `ChallengeType` | `CHALLENGE` | `CHALLENGE` (cookie) or `TURNSTILE` (token) |
| `sleep_time` | `int` | `5` | Seconds to wait before clicking checkbox |
| `headless` | `bool` | `True` | Headless mode (ignored when `pool` is set) |
| `os` | `list[str]` | `["windows"]` | OS fingerprint (ignored when `pool` is set) |
| `debug` | `bool` | `False` | Verbose logging + failure screenshots |
| `retries` | `int` | `30` | Polling attempts for frame/token detection |
| `proxy` | `str \| None` | `None` | Proxy URL (ignored when `pool` is set) |
| `pool` | `BrowserPool \| None` | `None` | Pre-warmed browser pool |
| `cache` | `ChallengeCache \| None` | `None` | Result cache |
| `on_success` | `Callback \| None` | `None` | Called with `(url, result)` on success (sync or async) |
| `on_failure` | `Callback \| None` | `None` | Called with `(url, exc_or_none)` on failure (sync or async) |
| `timeout` | `float \| None` | `None` | Per-call timeout in seconds |

#### Methods:

| Method | Description |
|--------|-------------|
| `solve(link)` | Solve challenge for one URL. Returns `CloudflareCookie`, `TurnstileToken`, or `None` |
| `solve_batch(links, concurrency=None)` | Solve multiple URLs in parallel. Returns list in input order. `concurrency` caps simultaneous solves |

## How It Works

### Challenge Type (Cookie)

1. Launches a stealthy browser instance with realistic fingerprint
2. Navigates to the protected URL
3. Detects Cloudflare challenge iframe
4. Automatically clicks the verification checkbox
5. Extracts the `cf_clearance` cookie upon success
6. Returns the cookie as a validated dataclass object

### Turnstile Type (Token)

1. Launches a stealthy browser instance with realistic fingerprint
2. Navigates to the protected URL
3. Detects Cloudflare challenge iframe
4. Automatically clicks the verification checkbox
5. Extracts the token from `cf-turnstile-response` hidden input field
6. Returns the token as a validated dataclass object

## Important Note

> [!IMPORTANT]
> By using this repository or any code related to it, you agree to the [legal notice](LEGAL_NOTICE.md). The author is **not responsible for the usage of this repository nor endorses it**, nor is the author responsible for any copies, forks, re-uploads made by other users, or anything else related to this repository.
