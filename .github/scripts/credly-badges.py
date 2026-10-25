#!/usr/bin/env python3
"""Write every badge on the public Credly profile into README.md.

One JSON request to https://www.credly.com/users/<user>/badges.json, newest
first, expired badges dropped, each badge linked to its verification page with
its issue date underneath. No dependency on a third-party action and no
grouping: one grid, in date order.

GitHub strips CSS from READMEs, so a caption can only be pinned under an image
with a table cell - image cell, caption cell, 6 per row. Each row is its own
centred table so a short final row stays centred.

A 404 (no such profile) or a profile with no badges is not a failure: the
placeholder line is kept and the run succeeds.

Usage: credly-badges.py [README_PATH]      user from CREDLY_USERNAME
       credly-badges.py --file badges.json [README_PATH]   (offline test)
"""

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

USER = os.environ.get("CREDLY_USERNAME", "samy-tamim")
API = "https://www.credly.com/users/{user}/badges.json"

COLUMNS = 6
THUMB = 100
CELL = THUMB + 36  # px around the badge; keeps captions off the next cell
PLACEHOLDER = "_Badges sync automatically after certification._"

START = "<!-- CREDLY-BADGES:START -->"
END = "<!-- CREDLY-BADGES:END -->"


def fetch(url: str, attempts: int = 3) -> dict:
    """GET the JSON API, retrying transient failures but not a wrong username."""
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "credly-badges-readme"},
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if 400 <= error.code < 500 and error.code != 429:
                raise
            if attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(5 * attempt)
    raise SystemExit("unreachable")  # pragma: no cover


def fetch_badges(user: str) -> list[dict]:
    """Every badge on the profile, following Credly's own pagination links."""
    url = API.format(user=user)
    badges, seen = [], set()
    while url and url not in seen:
        seen.add(url)
        page = fetch(url)
        data = page.get("data")
        if not isinstance(data, list):
            raise SystemExit(f"ERROR: unexpected API payload for {url}")
        badges += data
        url = (page.get("metadata") or {}).get("next_page_url")
        if url and not url.startswith("https://www.credly.com/users/"):
            raise SystemExit(f"ERROR: refusing to follow {url}")
    return badges


def as_date(badge: dict, key: str) -> date | None:
    try:
        return date.fromisoformat(str(badge.get(key) or ""))
    except ValueError:
        return None


def select(badges: list[dict], today: date) -> list[dict]:
    """Drop expired and imageless badges, newest first, undated ones last."""
    alive = []
    for badge in badges:
        if not (badge.get("badge_template") or {}).get("image_url"):
            continue
        expires = as_date(badge, "expires_at_date")
        if expires is None or expires >= today:
            alive.append(badge)

    dated = [badge for badge in alive if as_date(badge, "issued_at_date")]
    dated.sort(key=lambda badge: as_date(badge, "issued_at_date"), reverse=True)
    return dated + [badge for badge in alive if not as_date(badge, "issued_at_date")]


def cells(badge: dict) -> tuple[str, str]:
    """The anchor for one badge and the caption that goes under it."""
    template = badge.get("badge_template") or {}
    name = html.escape(template.get("name") or "Badge", quote=True)
    image = (template.get("image_url") or "").replace(
        "images.credly.com/images/", f"images.credly.com/size/{THUMB}x{THUMB}/images/"
    )
    link = html.escape(f"https://www.credly.com/badges/{badge.get('id', '')}", quote=True)
    anchor = (
        f'<a href="{link}" title="{name}">'
        f'<img src="{html.escape(image, quote=True)}" alt="{name}" '
        f'width="{THUMB}" height="{THUMB}"></a>'
    )

    lines = [(badge.get("issued_at_date") or "")[:10] or "—"]
    expires = (badge.get("expires_at_date") or "")[:10]
    if expires:
        lines.append(f"exp. {expires}")
    return anchor, "<sub>" + "<br>".join(lines) + "</sub>"


def render(badges: list[dict]) -> str:
    """One flat grid: 6 badges per row, one caption row under each image row."""
    if not badges:
        return PLACEHOLDER

    blocks = []
    for start in range(0, len(badges), COLUMNS):
        row = [cells(badge) for badge in badges[start:start + COLUMNS]]
        images = "".join(f'<td align="center" width="{CELL}">{a}</td>' for a, _ in row)
        captions = "".join(f'<td align="center">{c}</td>' for _, c in row)
        blocks += [
            '<table align="center">',
            f"<tr>{images}</tr>",
            f"<tr>{captions}</tr>",
            "</table>",
            "",
        ]
    return "\n".join(blocks).rstrip()


def write(readme: Path, section: str) -> bool:
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"ERROR: {START} / {END} markers missing from {readme}.")

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{START}\n{section}\n{END}{tail}"
    if updated == text:
        return False
    readme.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument("--file", help="read a saved badges.json instead of the API")
    parser.add_argument("--user", default=USER)
    args = parser.parse_args()

    readme = Path(args.readme)
    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        badges = payload.get("data") or []
    else:
        try:
            badges = fetch_badges(args.user)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            badges = []
            print(f"Credly user '{args.user}' has no public badge JSON (404).")

    shown = select(badges, date.today())
    if not shown:
        print(f"No badges to show ({len(badges)} on the profile). Placeholder kept.")
        changed = write(readme, PLACEHOLDER)
    else:
        changed = write(readme, render(shown))
        print(
            f"Wrote {len(shown)} badge(s) to {readme}."
            if changed
            else f"{readme} already up to date ({len(shown)} badge(s))."
        )

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"count={len(shown)}\n")
            handle.write(f"changed={'true' if changed else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
