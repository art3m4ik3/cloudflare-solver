import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from playwright.async_api import Page
from camoufox.async_api import AsyncCamoufox
from browserforge.fingerprints import Screen

logger = logging.getLogger(__name__)


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
        """Validate cookie data."""

        if not self.name or not self.value:
            raise ValueError("Cookie name and value must be set")

    @classmethod
    def from_json(cls, cookie_data: Dict[str, Any]) -> "CloudflareCookie":
        """Create CloudflareCookie from dictionary."""

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
        """Validate token data."""

        if not self.token:
            raise ValueError("Token must be set")


class CloudflareSolver:
    """Solver for Cloudflare anti-bot challenges."""

    def __init__(
        self,
        challenge_type: ChallengeType = ChallengeType.CHALLENGE,
        sleep_time: int = 5,
        headless: bool = True,
        os: Optional[List[str]] = None,
        debug: bool = False,
        retries: int = 30,
        proxy: Optional[str] = None,
    ) -> None:
        """Initialize solver with given parameters."""

        self.challenge_type = challenge_type
        self.cf_clearance: Optional[CloudflareCookie] = None
        self.turnstile_token: Optional[TurnstileToken] = None
        self.sleep_time = sleep_time
        self.headless = headless
        self.os = os or ["windows"]
        self.debug = debug
        self.retries = retries
        self.proxy = proxy

        if debug:
            logging.basicConfig(level=logging.DEBUG)

    async def _human_click(self, page: Page, x: float, y: float) -> None:
        """Move mouse to coordinates with random steps and click."""

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
        """Extract Turnstile token from hidden input field."""

        try:
            for _ in range(self.retries):
                token_inputs = await page.query_selector_all(
                    'input[name="cf-turnstile-response"]'
                )

                for token_input in token_inputs:
                    token = await token_input.get_attribute("value")

                    if token and len(token) > 10:
                        logger.debug("Turnstile token found")
                        return token

                await asyncio.sleep(1)

            logger.debug("Turnstile token not found")
            return None
        except Exception as e:
            logger.error(f"Error extracting Turnstile token: {e}")
            return None

    async def solve(
        self, link: str
    ) -> Optional[Union[CloudflareCookie, TurnstileToken]]:
        """Solve Cloudflare challenge and return result based on challenge type."""

        proxy_config = {"server": self.proxy} if self.proxy else None

        try:
            async with AsyncCamoufox(
                headless=self.headless,
                os=self.os,
                screen=Screen(max_width=1920, max_height=1080),
                proxy=proxy_config,
            ) as browser:
                page = await browser.new_page()
                await page.goto(link)

                for _ in range(self.retries):
                    if await self._find_and_click_challenge_frame(page):
                        await asyncio.sleep(1)
                        break
                    await asyncio.sleep(1)

                if self.challenge_type == ChallengeType.CHALLENGE:
                    cookies = await page.context.cookies()

                    cf_clearance_cookie = next(
                        (
                            cookie
                            for cookie in cookies
                            if cookie.get("name") == "cf_clearance"
                        ),
                        None,
                    )

                    if cf_clearance_cookie:
                        logger.debug(
                            "cf_clearance cookie found: %s", cf_clearance_cookie
                        )
                        cookie_dict: Dict[str, Any] = dict(cf_clearance_cookie)
                        self.cf_clearance = CloudflareCookie.from_json(cookie_dict)
                    else:
                        logger.debug("cf_clearance cookie not found")

                        if self.debug:
                            await page.screenshot(path="debug_failed_challenge.png")

                    return self.cf_clearance

                elif self.challenge_type == ChallengeType.TURNSTILE:
                    token = await self._get_turnstile_token(page)

                    if token:
                        self.turnstile_token = TurnstileToken(token=token)
                    else:
                        logger.debug("Turnstile token not found")
                        if self.debug:
                            await page.screenshot(path="debug_failed_turnstile.png")

                    return self.turnstile_token

        except Exception as e:
            logger.error(f"Error solving Cloudflare challenge: {e}")
            return None


if __name__ == "__main__":
    print("Turnstile Example")
    solver = CloudflareSolver(
        challenge_type=ChallengeType.TURNSTILE,
        proxy="http://127.0.0.1:10808",
        debug=True,
        headless=False,
    )
    result = asyncio.run(solver.solve("https://nopecha.com/captcha/turnstile"))

    if result:
        if isinstance(result, CloudflareCookie):
            print(f"Cookie: {result.name} = {result.value}")
        elif isinstance(result, TurnstileToken):
            print(f"Token: {result.token}")
    else:
        print("Failed to solve challenge")

    print("\nChallenge Example")
    solver_challenge = CloudflareSolver(
        challenge_type=ChallengeType.CHALLENGE,
        proxy="http://127.0.0.1:10808",
        debug=True,
        headless=False,
    )
    result_challenge = asyncio.run(
        solver_challenge.solve("https://nopecha.com/demo/cloudflare")
    )

    if result_challenge:
        if isinstance(result_challenge, CloudflareCookie):
            print(f"Cookie: {result_challenge.name} = {result_challenge.value}")
            print(f"Domain: {result_challenge.domain}")
            print(f"Expires: {result_challenge.expires}")
        elif isinstance(result_challenge, TurnstileToken):
            print(f"Token: {result_challenge.token}")
    else:
        print("Failed to solve challenge")
