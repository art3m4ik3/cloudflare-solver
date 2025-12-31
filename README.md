# Cloudflare Challenge Solver

Asynchronous Python solution for bypassing Cloudflare's anti-bot challenges, supporting both **Challenge** (cookie-based) and **Turnstile** (token-based) types.

## Features

- **Dual Challenge Support** - Handles both Challenge (`cf_clearance` cookie) and Turnstile (token) types
- **Asynchronous** - Built with `asyncio` and `Playwright` for high performance
- **Stealthy** - Uses Camoufox and BrowserForge for realistic browser fingerprinting
- **Modular** - Clean OOP design with dataclasses for results handling
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

### Advanced Configuration

```python
solver = CloudflareSolver(
    challenge_type=ChallengeType.TURNSTILE,  # or ChallengeType.CHALLENGE
    sleep_time=5,  # Longer delay before clicking challenge
    headless=False,  # Show browser window
    os=["macos"],  # macOS fingerprint
    debug=True,  # Enable verbose logging
    retries=50,  # More attempts to find challenge
    proxy="http://user:pass@host:port"  # Use a proxy server
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

### `CloudflareSolver` Class

#### Parameters:

- `challenge_type`: Type of challenge to solve - `ChallengeType.CHALLENGE` or `ChallengeType.TURNSTILE` (default: `ChallengeType.CHALLENGE`)
- `sleep_time`: Delay before clicking challenge (default: 3)
- `headless`: Run browser in headless mode (default: True)
- `os`: OS fingerprint (default: ["windows"])
- `debug`: Enable debug logging (default: False)
- `retries`: Number of attempts to find challenge (default: 30)
- `proxy`: Proxy server URL (e.g., "http://user:pass@host:port") (default: None)

#### Methods:

- `solve(link: str)`: Solves Cloudflare challenge for given URL, returns `CloudflareCookie`, `TurnstileToken`, or `None`

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
