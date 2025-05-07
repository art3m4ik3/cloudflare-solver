# Cloudflare Challenge TurnStile Solver

Asynchronous Python solution for bypassing Cloudflare's anti-bot turnstile challenges and obtaining the `cf_clearance` cookie.

## Features

-   **Asynchronous** - Built with `asyncio` and `Playwright` for high performance
-   **Stealthy** - Uses Camoufox and BrowserForge for realistic browser fingerprinting
-   **Modular** - Clean OOP design with dataclasses for cookie handling
-   **Configurable** - Customize retries, delays, OS fingerprint, and more
-   **Logging** - Built-in debug logging for troubleshooting

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

### Basic Example

```python
from main import CloudflareSolver
import asyncio

async def main():
    solver = CloudflareSolver(
        headless=True,  # Run in headless mode
        os=["windows"],  # Windows fingerprint
    )

    cookie = await solver.solve("https://protected-site.com")

    if cookie:
        print(f"Cookie obtained: {cookie.name}={cookie.value}")
    else:
        print("Failed to solve Cloudflare challenge")

asyncio.run(main())
```

### Advanced Configuration

```python
solver = CloudflareSolver(
    sleep_time=5,  # Longer delay before clicking challenge
    headless=False,  # Show browser window
    os=["macos"],  # macOS fingerprint
    debug=True,  # Enable verbose logging
    retries=50  # More attempts to find challenge
)
```

## API Reference

### `CloudflareCookie` Dataclass

Represents the Cloudflare clearance cookie with validation:

-   `name`: Cookie name (typically "cf_clearance")
-   `value`: Cookie value
-   `domain`: Cookie domain
-   `path`: Cookie path
-   `expires`: Expiration timestamp
-   `http_only`: HTTP Only flag
-   `secure`: Secure flag
-   `same_site`: SameSite policy

### `CloudflareSolver` Class

#### Parameters:

-   `sleep_time`: Delay before clicking challenge (default: 3)
-   `headless`: Run browser in headless mode (default: True)
-   `os`: OS fingerprint (default: ["windows"])
-   `debug`: Enable debug logging (default: False)
-   `retries`: Number of attempts to find challenge (default: 30)

#### Methods:

-   `solve(link: str)`: Solves Cloudflare challenge for given URL, returns `CloudflareCookie` or `None`

## How It Works

1. Launches a stealthy browser instance with realistic fingerprint
2. Navigates to the protected URL
3. Detects Cloudflare challenge iframe
4. Automatically clicks the verification checkbox
5. Extracts the `cf_clearance` cookie upon success
6. Returns the cookie as a validated dataclass object

## Important Note

> [!IMPORTANT]
> By using this repository or any code related to it, you agree to the [legal notice](LEGAL_NOTICE.md). The author is **not responsible for the usage of this repository nor endorses it**, nor is the author responsible for any copies, forks, re-uploads made by other users, or anything else related to this repository.
