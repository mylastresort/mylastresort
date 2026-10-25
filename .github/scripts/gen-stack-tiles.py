#!/usr/bin/env python3
"""Generate the rounded stack tiles used by the README.

Each tile is a 256x256 SVG: a rounded card plus the brand glyph, with a
`prefers-color-scheme` rule so one file serves both GitHub themes.

    python3 .github/scripts/gen-stack-tiles.py [--style brand|tonal] [--out DIR]

Glyphs come from Simple Icons (https://simpleicons.org). Colours follow the
style's palette rules; every glyph is kept above the WCAG 3:1 non-text
contrast ratio against its own card in both themes.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SIZE = 256
RADIUS = 56
GLYPH = 136
SCALE = GLYPH / 24  # Simple Icons artwork lives in a 24x24 viewBox

PAGE_LIGHT = "#FFFFFF"
PAGE_DARK = "#0D1117"
STROKE_UNITS = 4  # hairline at 44px display (256 / 44)

# (alt text, simpleicons slug, brand colour, file name)
ICONS = [
    ("Python", "python", "3776AB", "python"),
    ("Rust", "rust", "000000", "rust"),
    ("C", "c", "A8B9CC", "c"),
    ("C++", "cplusplus", "00599C", "cpp"),
    ("TypeScript", "typescript", "3178C6", "typescript"),
    ("OCaml", "ocaml", "EC6813", "ocaml"),
    ("Docker", "docker", "2496ED", "docker"),
    ("Go", "go", "00ADD8", "go"),
    ("Kubernetes", "kubernetes", "326CE5", "kubernetes"),
    ("NumPy", "numpy", "013243", "numpy"),
    ("Pandas", "pandas", "150458", "pandas"),
    ("scikit-learn", "scikitlearn", "F7931E", "scikit-learn"),
    ("PyTorch", "pytorch", "EE4C2C", "pytorch"),
    ("React", "react", "61DAFB", "react"),
]

# MNE-Python has no Simple Icons entry, so its tile is a letterform.
TEXT_TILE = ("MNE", "MNE-Python", "00A896", "mne")


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def hexed(colour: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*colour)


def mix(fg: str, bg: str, weight: float) -> str:
    """Return `weight` of fg blended into bg (0 = bg, 1 = fg)."""
    a, b = rgb(fg), rgb(bg)
    return hexed(tuple(round(b[i] + (a[i] - b[i]) * weight) for i in range(3)))


def luminance(colour: tuple[int, int, int]) -> float:
    channels = []
    for c in colour:
        c = c / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(rgb(a)), luminance(rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def push_to_contrast(fg: str, bg: str, target: float) -> str:
    """Darken or lighten fg until it clears target contrast against bg."""
    if contrast(fg, bg) >= target:
        return fg
    toward = "#000000" if luminance(rgb(bg)) > 0.5 else "#FFFFFF"
    for step in range(2, 101, 2):
        candidate = mix(toward, fg, step / 100)
        if contrast(candidate, bg) >= target:
            return candidate
    return toward


def palette(brand: str, style: str) -> dict[str, str]:
    """Card fill, hairline, and glyph colours for both themes."""
    brand = "#" + brand.lstrip("#").upper()
    if style == "brand":
        # white is the brand-conventional glyph; only fall back to ink when
        # white cannot clear the 3:1 non-text contrast ratio
        white = contrast("#FFFFFF", brand)
        glyph_light = "#FFFFFF" if white >= 3.0 else "#0D1117"
        glyph_dark = glyph_light
        fills = {"light": brand, "dark": brand}
        strokes = {"light": "#000000", "dark": "#FFFFFF"}
        opacities = {"light": "0.10", "dark": "0.14"}
    else:  # tonal: brand-tinted surface, brand glyph
        fills = {
            "light": mix(brand, PAGE_LIGHT, 0.14),
            "dark": mix(brand, PAGE_DARK, 0.30),
        }
        # a near-black brand tinted into the dark page is invisible; lift the
        # surface until the card separates from the page again
        for _ in range(12):
            if contrast(fills["dark"], PAGE_DARK) >= 1.28:
                break
            fills["dark"] = mix("#FFFFFF", fills["dark"], 0.05)
        strokes = {
            "light": mix(brand, PAGE_LIGHT, 0.55),
            "dark": mix(brand, PAGE_DARK, 0.62),
        }
        opacities = {"light": "0.55", "dark": "0.55"}
        glyph_light = push_to_contrast(brand, fills["light"], 4.5)
        glyph_dark = push_to_contrast(brand, fills["dark"], 4.5)
    return {
        "fill": fills,
        "stroke": strokes,
        "opacity": opacities,
        "glyph": {"light": glyph_light, "dark": glyph_dark},
    }


def fetch_glyph(slug: str) -> str:
    url = f"https://cdn.simpleicons.org/{slug}"
    request = urllib.request.Request(url, headers={"User-Agent": "stack-tiles"})
    try:
        body = urllib.request.urlopen(request, timeout=20).read().decode()
    except urllib.error.URLError as error:  # pragma: no cover - network only
        sys.exit(f"cannot fetch {url}: {error}")
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    return body.split(">", 1)[1].rsplit("</svg>", 1)[0].strip()


def svg(alt: str, colours: dict, body: str = "", label: str | None = None) -> str:
    if label is None:
        content = (
            f'  <g class="g" transform="translate({(SIZE - GLYPH) // 2} '
            f'{(SIZE - GLYPH) // 2}) scale({SCALE:.4f})">{body}</g>'
        )
    else:
        content = (
            '  <g class="g" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" '
            'font-size="84" font-weight="700" text-anchor="middle">\n'
            f'    <text x="{SIZE // 2}" y="{SIZE // 2}" dy="0.35em">{label}</text>\n'
            "  </g>"
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
        f'viewBox="0 0 256 256" role="img" aria-label="{alt}">\n'
        f"  <title>{alt}</title>\n"
        "  <style>\n"
        f"    .c {{ fill: {colours['fill']['light']}; stroke: {colours['stroke']['light']};"
        f" stroke-opacity: {colours['opacity']['light']}; }}\n"
        f"    .g {{ fill: {colours['glyph']['light']}; }}\n"
        "    @media (prefers-color-scheme: dark) {\n"
        f"      .c {{ fill: {colours['fill']['dark']}; stroke: {colours['stroke']['dark']};"
        f" stroke-opacity: {colours['opacity']['dark']}; }}\n"
        f"      .g {{ fill: {colours['glyph']['dark']}; }}\n"
        "    }\n"
        "  </style>\n"
        f'  <rect class="c" x="{STROKE_UNITS // 2}" y="{STROKE_UNITS // 2}" '
        f'width="{SIZE - STROKE_UNITS}" height="{SIZE - STROKE_UNITS}" rx="{RADIUS}" '
        f'stroke-width="{STROKE_UNITS}"/>\n'
        f"{content}\n"
        "</svg>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", choices=("brand", "tonal"), default="brand")
    parser.add_argument("--out", default=str(ROOT / "assets" / "stack"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for alt, slug, brand, name in ICONS:
        colours = palette(brand, args.style)
        (out / f"{name}.svg").write_text(svg(alt, colours, fetch_glyph(slug)), encoding="utf-8")
        report.append((name, brand, colours))

    text, alt, brand, name = TEXT_TILE
    colours = palette(brand, args.style)
    (out / f"{name}.svg").write_text(svg(alt, colours, label=text), encoding="utf-8")
    report.append((name, brand, colours))

    width = max(len(r[0]) for r in report)
    print(f"{args.style} tiles -> {out}")
    print(f"{'tile'.ljust(width)}  card (light / dark)      glyph (light / dark)   contrast")
    for name, brand, colours in report:
        cl = contrast(colours["glyph"]["light"], colours["fill"]["light"])
        cd = contrast(colours["glyph"]["dark"], colours["fill"]["dark"])
        print(
            f"{name.ljust(width)}  {colours['fill']['light']} / {colours['fill']['dark']}  "
            f"{colours['glyph']['light']} / {colours['glyph']['dark']}   {cl:4.1f} / {cd:4.1f}"
        )


if __name__ == "__main__":
    main()
