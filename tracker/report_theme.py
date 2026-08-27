"""
Single source of truth for report color-coding.

The dashboards define their red / amber(yellow) / green tokens once, in
static/tracker/styles.css (the `:root { --red: ...; }` block) and reuse
them via CSS classes like `.status-red`, `.status-yellow`, `.status-green`.

Reports (PDF via WeasyPrint, and Word via python-docx) need the *same*
colors, but they render outside of that stylesheet's cascade (PDFs are
built from a standalone HTML string, and .docx has no CSS at all). Rather
than hard-coding a second copy of the palette in the report code — which
would silently drift out of sync whenever someone tweaks the dashboard
colors — this module reads styles.css itself at render time and extracts:

  * `root_css`   — the raw `:root { ... }` variable declarations, which we
                    re-embed verbatim inside the report's <style> tag so
                    PDF output can use `var(--red)` etc. exactly like the
                    dashboards do.
  * `status_css` — the actual `.status-*` / `.pill--*` rule blocks from
                    the stylesheet, also re-embedded verbatim, so the PDF
                    report's status classes render identically to the
                    dashboard's.
  * `hex`        — the same tokens resolved to plain hex strings, for use
                    in the Word export, since .docx has no concept of CSS
                    variables and needs a literal RGBColor.

Because everything is read from styles.css on every call (nothing is
cached or duplicated), changing a color there is automatically reflected
in both report formats the next time they're generated.
"""
import re

from django.conf import settings

STYLES_CSS_PATH = settings.BASE_DIR / "static" / "tracker" / "styles.css"

# Status keywords used throughout the app (task_color / worst_color) mapped
# to the CSS variable name actually used in styles.css for that status.
_STATUS_TO_VAR = {
    "red": "red",
    "yellow": "amber",
    "green": "green",
}

_FALLBACK_HEX = {
    "red": "#C0392B",
    "red_bg": "#FBEAE7",
    "yellow": "#B8790F",
    "yellow_bg": "#FBF0DD",
    "green": "#3F7D3F",
    "green_bg": "#E9F2E6",
}


def _read_styles_css():
    try:
        return STYLES_CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def get_report_theme():
    """
    Returns a dict with:
      root_css   - str, the `:root { ... }` custom-property declarations
      status_css - str, the `.status-*` / `.pill--*` rule blocks
      hex        - dict of resolved hex colors for red/yellow/green (+ _bg)
                   for use where CSS variables aren't available (docx)
    """
    css_text = _read_styles_css()

    root_match = re.search(r":root\s*\{(.*?)\}", css_text, re.S)
    root_block = root_match.group(1).strip() if root_match else ""

    # Pull every rule whose selector list touches status/pill styling, so
    # the PDF report reuses the dashboard's actual color rules rather than
    # a hand-written approximation of them.
    status_rule_blocks = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css_text):
        if re.search(r"\.status-(red|yellow|green)\b|\.pill--", selector):
            status_rule_blocks.append(f"{selector.strip()} {{{body.strip()}}}")
    status_css = "\n".join(status_rule_blocks)

    tokens = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", root_block))

    hex_colors = {}
    for status, var_name in _STATUS_TO_VAR.items():
        hex_colors[status] = tokens.get(var_name, _FALLBACK_HEX[status])
        hex_colors[f"{status}_bg"] = tokens.get(f"{var_name}-bg", _FALLBACK_HEX[f"{status}_bg"])

    return {
        "root_css": root_block,
        "status_css": status_css,
        "hex": hex_colors,
    }


def hex_to_rgb(hex_str):
    """'#C0392B' -> (0xC0, 0x39, 0x2B), for docx.shared.RGBColor(*rgb)."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))