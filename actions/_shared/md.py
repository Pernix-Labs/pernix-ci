"""Markdown table helpers for step summaries."""

ELLIPSIS = "\u2026"


def cell(s, max=500):
    """Escape a value for a markdown table cell and cap its length."""
    text = "" if s is None else str(s)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > max:
        text = text[: max - 1] + ELLIPSIS
    return text.replace("|", "\\|").replace("\n", "<br>")


def table(headers, rows, limit=200):
    """Render a markdown table, keeping at most `limit` rows."""
    rows = list(rows)
    lines = [
        "| " + " | ".join(cell(h) for h in headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    out = "\n".join(lines) + "\n"
    omitted = len(rows) - limit
    if omitted > 0:
        out += "\n%d more rows omitted\n" % omitted
    return out
