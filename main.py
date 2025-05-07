import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from playwright.async_api import Page
from camoufox.async_api import AsyncCamoufox
from browserforge.fingerprints import Screen

logger = logging.getLogger(__name__)


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


class CloudflareSolver:
    """Solver for Cloudflare anti-bot challenges."""

    def __init__(
        self,
        sleep_time: int = 3,
        headless: bool = True,
        os: Optional[List[str]] = None,
        debug: bool = False,
        retries: int = 30,
    ) -> None:
        """Initialize solver with given parameters."""

        self.cf_clearance: Optional[CloudflareCookie] = None
        self.sleep_time = sleep_time
        self.headless = headless
        self.os = os or ["windows"]
        self.debug = debug
        self.retries = retries

        if debug:
            logging.basicConfig(level=logging.DEBUG)

    async def _find_and_click_challenge_frame(self, page: Page) -> bool:
        """Find Cloudflare challenge frame and click the checkbox."""
        for frame in page.frames:
            if frame.url.startswith("https://challenges.cloudflare.com"):
                frame_element = await frame.frame_element()
                bounding_box = await frame_element.bounding_box()

                checkbox_x = bounding_box["x"] + bounding_box["width"] / 9
                checkbox_y = bounding_box["y"] + bounding_box["height"] / 2

                await asyncio.sleep(self.sleep_time)
                await page.mouse.click(x=checkbox_x, y=checkbox_y)

                return True
        return False

    async def solve(self, link: str) -> Optional[CloudflareCookie]:
        """Solve Cloudflare challenge and return clearance cookie."""
        try:
            async with AsyncCamoufox(
                headless=self.headless,
                os=self.os,
                screen=Screen(max_width=1920, max_height=1080),
            ) as browser:
                page = await browser.new_page()
                await page.goto(link)

                for _ in range(self.retries):
                    if await self._find_and_click_challenge_frame(page):
                        await asyncio.sleep(1)
                        break
                    await asyncio.sleep(1)

                cookies = await page.context.cookies()

                cf_clearance_cookie = next(
                    (cookie for cookie in cookies if cookie["name"] == "cf_clearance"),
                    None,
                )

                if cf_clearance_cookie:
                    logger.debug("cf_clearance cookie found: %s", cf_clearance_cookie)
                    self.cf_clearance = CloudflareCookie.from_json(cf_clearance_cookie)
                else:
                    logger.debug("cf_clearance cookie not found")

                return self.cf_clearance
        except Exception as e:
            logger.error(f"Error solving Cloudflare challenge: {e}")
            return None


if __name__ == "__main__":
    solver = CloudflareSolver()
    cookie = asyncio.run(solver.solve("https://2ip.pro"))

    if cookie:
        print(cookie.name)
        print(cookie.value)
    else:
        print("Failed to get cookie")
