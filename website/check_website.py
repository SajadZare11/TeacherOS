from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

SITE_DIR = Path(__file__).resolve().parent
REQUIRED_FILES = (
    "index.html",
    "styles.css",
    "script.js",
    "site-config.js",
    "privacy.html",
    "terms.html",
)
TELEGRAM_URL_PATTERN = re.compile(
    r"telegramBotUrl\s*:\s*['\"](?P<url>[^'\"]+)['\"]",
    re.IGNORECASE,
)
TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")


class WebsiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.links: list[str] = []
        self.local_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids.add(element_id)

        if tag == "a":
            self.links.append(values.get("href") or "")
        elif tag == "script" and values.get("src"):
            self.local_assets.append(values["src"] or "")
        elif tag == "link" and values.get("rel") == "stylesheet":
            self.local_assets.append(values.get("href") or "")


def read_telegram_url(config: str) -> str | None:
    """Return only the configured telegramBotUrl value, ignoring comments."""
    match = TELEGRAM_URL_PATTERN.search(config)
    if not match:
        return None
    return match.group("url").strip()


def validate_telegram_url(url: str | None) -> str | None:
    if not url:
        return "site-config.js does not contain telegramBotUrl"

    if "YOUR_BOT_USERNAME" in url.upper():
        return "Replace the Telegram username placeholder in site-config.js"

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "t.me":
        return "telegramBotUrl must use this format: https://t.me/YourBotUsername"

    username = parsed.path.strip("/")
    if not TELEGRAM_USERNAME_PATTERN.fullmatch(username):
        return "Telegram username must contain 5-32 letters, numbers, or underscores"

    if not username.lower().endswith("bot"):
        return "Telegram bot usernames normally end with 'bot'"

    return None


def main() -> int:
    # Keep diagnostics reliable on Windows terminals whose default code page
    # cannot encode the intentional check-mark output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    problems: list[str] = []

    for filename in REQUIRED_FILES:
        path = SITE_DIR / filename
        if not path.is_file():
            problems.append(f"Missing required file: {filename}")
        elif path.stat().st_size == 0:
            problems.append(f"File is empty: {filename}")

    index_path = SITE_DIR / "index.html"
    css_path = SITE_DIR / "styles.css"
    config_path = SITE_DIR / "site-config.js"

    if index_path.is_file():
        parser = WebsiteParser()
        parser.feed(index_path.read_text(encoding="utf-8"))

        if parser.duplicate_ids:
            problems.append(
                "Duplicate HTML IDs: " + ", ".join(sorted(parser.duplicate_ids))
            )

        for asset in parser.local_assets:
            if asset and not asset.startswith(("http://", "https://", "//")):
                if not (SITE_DIR / asset).is_file():
                    problems.append(f"Missing local asset referenced by HTML: {asset}")

        for link in parser.links:
            if link.startswith("#") and len(link) > 1 and link[1:] not in parser.ids:
                problems.append(f"Broken page anchor: {link}")

    if css_path.is_file():
        css = css_path.read_text(encoding="utf-8")
        if css.count("{") != css.count("}"):
            problems.append("styles.css has unbalanced braces")

    telegram_url: str | None = None
    if config_path.is_file():
        config = config_path.read_text(encoding="utf-8")
        telegram_url = read_telegram_url(config)
        telegram_problem = validate_telegram_url(telegram_url)
        if telegram_problem:
            problems.append(telegram_problem)

    print("TeacherOS website check\n")
    if problems:
        for problem in problems:
            print(f"❌ {problem}")
        return 1

    print("✅ Required website files found")
    print("✅ Local assets and page anchors are valid")
    print("✅ CSS structure passed")
    print(f"✅ Telegram bot link configured: {telegram_url}")
    print("\n✅ Landing page check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
