"""SVG charts for the ranking benchmark's reports, written as text with no dependencies.

The same output serves both reports. Saved as a file, a chart carries its own
styles and follows the reader's light or dark setting. Placed in the
interactive page, it leaves the styles to the page (`standalone=False`), and
every mark carries a `data-tip` the page shows on hover and on keyboard focus.

Colours are roles, not values: `STYLE` maps each role to the documented palette
for light and for dark. Text is always ink; only marks wear series colours.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape, quoteattr

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
WIDTH = 760

# Role -> (light, dark). Sequential steps q1..q7 run light to dark on a light
# surface and dark to light on a dark one, so "more" always stands out further
# from the surface. qt1..qt7 are the label colours inside those fills.
_ROLES = {
    "surface": ("#fcfcfb", "#1a1a19"),
    "ink": ("#0b0b0b", "#f0efec"),
    "ink2": ("#52514e", "#c3c2b7"),
    "muted": ("#898781", "#898781"),
    "grid": ("#e1e0d9", "#2c2c2a"),
    "axis": ("#c3c2b7", "#383835"),
    "s1": ("#2a78d6", "#3987e5"),
    "s2": ("#eb6834", "#d95926"),
    "quiet": ("#898781", "#898781"),
    "quiet2": ("#c3c2b7", "#52514e"),
    "neg": ("#e34948", "#e66767"),
    "q1": ("#cde2fb", "#0d366b"), "q2": ("#9ec5f4", "#184f95"), "q3": ("#6da7ec", "#256abf"),
    "q4": ("#3987e5", "#3987e5"), "q5": ("#256abf", "#6da7ec"), "q6": ("#184f95", "#9ec5f4"),
    "q7": ("#0d366b", "#cde2fb"),
    "qt1": ("#0b0b0b", "#ffffff"), "qt2": ("#0b0b0b", "#ffffff"), "qt3": ("#0b0b0b", "#ffffff"),
    "qt4": ("#ffffff", "#ffffff"), "qt5": ("#ffffff", "#0b0b0b"), "qt6": ("#ffffff", "#0b0b0b"),
    "qt7": ("#ffffff", "#0b0b0b"),
}


def _variables(mode: int) -> str:
    return " ".join(f"--kz-{role}: {values[mode]};" for role, values in _ROLES.items())


RULES = f"""
.kz {{ font-family: {FONT}; }}
.kz .surface {{ fill: var(--kz-surface); }}
.kz text {{ fill: var(--kz-ink2); font-size: 12px; }}
.kz .title {{ fill: var(--kz-ink); font-size: 14px; font-weight: 600; }}
.kz .sub {{ fill: var(--kz-ink2); font-size: 12px; }}
.kz .tick {{ fill: var(--kz-muted); font-size: 11px; font-variant-numeric: tabular-nums; }}
.kz .value {{ fill: var(--kz-ink); font-size: 11px; font-variant-numeric: tabular-nums; }}
.kz .head {{ fill: var(--kz-ink); font-size: 12px; font-weight: 600; }}
.kz .grid {{ stroke: var(--kz-grid); stroke-width: 1; }}
.kz .axis {{ stroke: var(--kz-axis); stroke-width: 1; }}
.kz .whisker {{ stroke: var(--kz-ink2); stroke-width: 1.5; }}
.kz .line {{ stroke: var(--kz-s1); stroke-width: 2; fill: none; stroke-linejoin: round; stroke-linecap: round; }}
.kz .dot {{ fill: var(--kz-s1); stroke: var(--kz-surface); stroke-width: 2; }}
.kz .s1 {{ fill: var(--kz-s1); }} .kz .s2 {{ fill: var(--kz-s2); }}
.kz .quiet {{ fill: var(--kz-quiet); }} .kz .quiet2 {{ fill: var(--kz-quiet2); }}
.kz .neg {{ fill: var(--kz-neg); }}
.kz .cell-text {{ font-size: 10.5px; font-variant-numeric: tabular-nums; }}
.kz .inside {{ fill: #ffffff; font-size: 11px; font-variant-numeric: tabular-nums; }}
.kz .inside.dark {{ fill: #0b0b0b; }}
""" + "".join(
    f".kz .q{i} {{ fill: var(--kz-q{i}); }} .kz .qt{i} {{ fill: var(--kz-qt{i}); }}\n" for i in range(1, 8))

# For a chart saved as its own file: the variables on the chart itself.
STANDALONE_STYLE = (
    f".kz {{ {_variables(0)} }}\n@media (prefers-color-scheme: dark) {{ .kz {{ {_variables(1)} }} }}\n" + RULES)

# For charts inside a page: the variables on a root element, following the
# reader's setting and a theme switch that wins over it either way.
PAGE_STYLE = (
    f".viz-root {{ color-scheme: light; {_variables(0)} }}\n"
    f"@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme=\"light\"])) .viz-root "
    f"{{ color-scheme: dark; {_variables(1)} }} }}\n"
    f":root[data-theme=\"dark\"] .viz-root {{ color-scheme: dark; {_variables(1)} }}\n" + RULES)


def text_width(text: str, size: float = 12) -> float:
    """A cautious estimate of rendered width; there are no font metrics here."""
    return len(text) * size * 0.6


def percent(value, digits: int = 0) -> str:
    return "" if value is None else f"{value * 100:.{digits}f}%"


def _nice_step(span: float, count: int) -> float:
    raw = span / max(1, count)
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for multiple in (1, 2, 2.5, 5, 10):
        if raw <= multiple * magnitude:
            return multiple * magnitude
    return 10 * magnitude


def nice_ticks(top: float, count: int = 5) -> list:
    """Round tick values from 0 up to at least `top`."""
    if top <= 0:
        return [0, 1]
    step = _nice_step(top, count)
    ticks = [0]
    while ticks[-1] < top - 1e-9:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def _number(value: float) -> str:
    if value >= 10000:
        return f"{value / 1000:.0f}K"
    return f"{value:,.0f}" if value == int(value) else f"{value:,.1f}"


class Chart:
    """Collects SVG elements; `svg()` wraps them with the title, the surface and the styles."""

    def __init__(self, title: str, subtitle: str, height: float, width: float = WIDTH):
        self.title, self.subtitle = title, subtitle
        self.width, self.height = width, height
        self.parts = []
        self.top = 54 if subtitle else 36

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def text(self, x: float, y: float, content: str, cls: str = "", anchor: str = "start", extra: str = "") -> None:
        cls_attr = f' class="{cls}"' if cls else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{cls_attr}{extra}>{escape(content)}</text>')

    def line(self, x1: float, y1: float, x2: float, y2: float, cls: str) -> None:
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"/>')

    def mark(self, shape: str, tip: str) -> None:
        """A data mark. `shape` is an element without its closing '/>'."""
        self.add(f'{shape} data-tip={quoteattr(tip)} tabindex="0"/>')

    def svg(self, standalone: bool = True) -> str:
        style = f"<style>{STANDALONE_STYLE}</style>" if standalone else ""
        label = quoteattr(f"{self.title}. {self.subtitle}" if self.subtitle else self.title)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" class="kz" role="img" aria-label={label} '
                f'viewBox="0 0 {self.width:.0f} {self.height:.0f}" width="{self.width:.0f}" height="{self.height:.0f}">'
                f"{style}"
                f'<rect class="surface" width="{self.width:.0f}" height="{self.height:.0f}" rx="8"/>')
        titles = f'<text x="16" y="24" class="title">{escape(self.title)}</text>'
        if self.subtitle:
            titles += f'<text x="16" y="42" class="sub">{escape(self.subtitle)}</text>'
        return head + titles + "".join(self.parts) + "</svg>\n"


def _bar_path(x0: float, x1: float, y: float, h: float) -> str:
    """A horizontal bar from the baseline x0 to x1: square at the baseline, rounded at the data end."""
    r = min(4.0, h / 2, abs(x1 - x0))
    s = 1 if x1 >= x0 else -1
    return (f"M{x0:.1f},{y:.1f} H{x1 - s * r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} "
            f"V{y + h - r:.1f} Q{x1:.1f},{y + h:.1f} {x1 - s * r:.1f},{y + h:.1f} H{x0:.1f} Z")


def _legend(chart: Chart, series: list, y: float, x: float = 16) -> None:
    """Swatch and name per series, in one row. `series` is [(class, name), ...]."""
    for cls, name in series:
        chart.add(f'<rect x="{x:.1f}" y="{y - 9:.1f}" width="10" height="10" rx="2" class="{cls}"/>')
        chart.text(x + 15, y, name)
        x += 15 + text_width(name) + 18


# ----------------------------------------------------------------------------
# the charts

def ranked_bars(title: str, subtitle: str, rows: list, standalone: bool = True) -> str:
    """Horizontal bars for shares between 0 and 1, in the order given.

    rows: [{'label', 'value', 'lo', 'hi', 'quiet' (optional), 'tip'}]. A quiet
    row is drawn in gray: a reference, not one of the things compared.
    """
    gutter = max(text_width(row["label"]) for row in rows) + 28
    pitch, thick = 22, 14
    chart = Chart(title, subtitle, 54 + len(rows) * pitch + 34)
    left, right = gutter, chart.width - 64
    scale = lambda v: left + (right - left) * v  # noqa: E731
    top = chart.top + 6
    bottom = top + len(rows) * pitch
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        chart.line(scale(tick), top, scale(tick), bottom, "axis" if tick == 0 else "grid")
        chart.text(scale(tick), bottom + 16, percent(tick), "tick", "middle")
    for i, row in enumerate(rows):
        y = top + i * pitch + (pitch - thick) / 2
        chart.text(left - 10, y + thick - 3, row["label"], "", "end")
        if row["value"] is None:
            continue
        cls = "quiet" if row.get("quiet") else "s1"
        chart.mark(f'<path d="{_bar_path(left, scale(row["value"]), y, thick)}" class="{cls}"', row["tip"])
        end = scale(row["value"])
        if row.get("lo") is not None:
            chart.line(scale(row["lo"]), y + thick / 2, scale(row["hi"]), y + thick / 2, "whisker")
            end = scale(row["hi"])
        chart.text(end + 6, y + thick - 3, percent(row["value"], 1), "value")
    return chart.svg(standalone)


def grid(title: str, subtitle: str, row_labels: list, column_labels: list, values: list, tips: list,
         standalone: bool = True, row_breaks: tuple = (), column_breaks: tuple = ()) -> str:
    """A table of shares between 0 and 1, each cell shaded by its value and printed as a percentage.

    values[r][c] is a share or None. `row_breaks` and `column_breaks` are
    indices that start a new block, set off by a little air.
    """
    cell_w, cell_h, gap, air = 25, 22, 2, 8
    gutter = max(text_width(label) for label in row_labels) + 26
    head = max(text_width(label, 11) for label in column_labels) * math.sin(math.radians(55)) + 14
    column_x = []
    x = gutter
    for c in range(len(column_labels)):
        if c in column_breaks:
            x += air
        column_x.append(x)
        x += cell_w
    width = max(WIDTH, x + max(text_width(label, 11) for label in column_labels) * math.cos(math.radians(55)) + 24)
    extra = air * len(row_breaks)
    chart = Chart(title, subtitle, 54 + head + len(row_labels) * cell_h + extra + 44, width)
    top = chart.top + head
    for c, label in enumerate(column_labels):
        x = column_x[c] + cell_w / 2
        chart.text(x, top - 8, label, "tick", "start", f' transform="rotate(-55 {x:.1f} {top - 8:.1f})"')
    y = top
    for r, label in enumerate(row_labels):
        if r in row_breaks:
            y += air
        chart.text(gutter - 10, y + cell_h - 7, label, "", "end")
        for c in range(len(column_labels)):
            value = values[r][c]
            if value is None:
                continue
            step = min(7, 1 + int(value / 0.15))
            x = column_x[c]
            chart.mark(f'<rect x="{x + gap / 2:.1f}" y="{y + gap / 2:.1f}" width="{cell_w - gap}" '
                       f'height="{cell_h - gap}" rx="2" class="q{step}"', tips[r][c])
            chart.text(x + cell_w / 2, y + cell_h - 7, f"{value * 100:.0f}", f"cell-text qt{step}", "middle",
                       ' pointer-events="none"')
        y += cell_h
    # The scale: seven steps with their bounds.
    lx, ly = gutter, y + 18
    chart.text(lx - 10, ly + 10, "Share, %", "tick", "end")
    for step in range(1, 8):
        chart.add(f'<rect x="{lx + (step - 1) * 34 + 1:.1f}" y="{ly:.1f}" width="32" height="12" rx="2" class="q{step}"/>')
        chart.text(lx + (step - 1) * 34, ly + 26, f"{(step - 1) * 15}", "tick", "middle")
    chart.text(lx + 7 * 34, ly + 26, "100", "tick", "middle")
    return chart.svg(standalone)


def stacked_bars(title: str, subtitle: str, rows: list, series: list, standalone: bool = True) -> str:
    """Horizontal bars, each one whole split into the same parts.

    rows: [{'label', 'parts': [share, ...], 'tips': [str, ...], 'gap_before' (optional)}].
    series: [(class, name), ...] in the order of the parts.
    """
    gutter = max(text_width(row["label"]) for row in rows) + 28
    pitch, thick, gap = 22, 14, 2
    extra = 8 * sum(1 for row in rows if row.get("gap_before"))
    chart = Chart(title, subtitle, 54 + 26 + len(rows) * pitch + extra + 34)
    left, right = gutter, chart.width - 28
    scale = lambda v: left + (right - left) * v  # noqa: E731
    _legend(chart, series, chart.top + 12)
    top = chart.top + 30
    bottom = top + len(rows) * pitch + extra
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        chart.line(scale(tick), top, scale(tick), bottom, "axis" if tick == 0 else "grid")
        chart.text(scale(tick), bottom + 16, percent(tick), "tick", "middle")
    y = top
    for row in rows:
        if row.get("gap_before"):
            y += 8
        by = y + (pitch - thick) / 2
        chart.text(left - 10, by + thick - 3, row["label"], "", "end")
        start = 0.0
        for (cls, _), part, tip in zip(series, row["parts"], row["tips"]):
            if part and part > 0:
                x0, x1 = scale(start), scale(start + part)
                if x1 - x0 > gap:
                    chart.mark(f'<rect x="{x0 + gap / 2:.1f}" y="{by:.1f}" width="{x1 - x0 - gap:.1f}" '
                               f'height="{thick}" rx="2" class="{cls}"', tip)
                    label = percent(part)
                    if x1 - x0 - gap > text_width(label, 11) + 10 and cls in ("s1", "s2", "quiet"):
                        chart.text((x0 + x1) / 2, by + thick - 3, label, "inside", "middle", ' pointer-events="none"')
                start += part
        y += pitch
    return chart.svg(standalone)


def diverging_bars(title: str, subtitle: str, rows: list, unit: str = "points", standalone: bool = True) -> str:
    """Bars to the right of zero (ahead) and to the left (behind), with their intervals.

    rows: [{'label', 'value', 'lo', 'hi', 'tip', 'gap_before' (optional)}], values in `unit`.
    """
    gutter = max(text_width(row["label"]) for row in rows) + 28
    pitch, thick = 22, 14
    extra = 8 * sum(1 for row in rows if row.get("gap_before"))
    chart = Chart(title, subtitle, 54 + 26 + len(rows) * pitch + extra + 34)
    left, right = gutter + 40, chart.width - 70
    reach = max(max(abs(row["lo"]), abs(row["hi"]), abs(row["value"])) for row in rows) or 1.0
    step = _nice_step(reach, 3)
    reach = step * math.ceil(reach / step - 1e-9)
    scale = lambda v: (left + right) / 2 + (right - left) / 2 * v / reach  # noqa: E731
    _legend(chart, [("s1", "ahead"), ("neg", "behind")], chart.top + 12)
    top = chart.top + 30
    bottom = top + len(rows) * pitch + extra
    tick = -reach
    while tick <= reach + 1e-9:
        chart.line(scale(tick), top, scale(tick), bottom, "axis" if abs(tick) < 1e-9 else "grid")
        chart.text(scale(tick), bottom + 16, f"{tick:+.0f}" if tick else "0", "tick", "middle")
        tick += step
    chart.text(right + 8, bottom + 16, unit, "tick")
    y = top
    for row in rows:
        if row.get("gap_before"):
            y += 8
        by = y + (pitch - thick) / 2
        chart.text(gutter - 10, by + thick - 3, row["label"], "", "end")
        cls = "s1" if row["value"] >= 0 else "neg"
        chart.mark(f'<path d="{_bar_path(scale(0), scale(row["value"]), by, thick)}" class="{cls}"', row["tip"])
        chart.line(scale(row["lo"]), by + thick / 2, scale(row["hi"]), by + thick / 2, "whisker")
        if row["value"] >= 0:
            chart.text(scale(row["hi"]) + 6, by + thick - 3, f"{row['value']:+.1f}", "value")
        else:
            chart.text(scale(row["lo"]) - 6, by + thick - 3, f"{row['value']:+.1f}", "value", "end")
        y += pitch
    return chart.svg(standalone)


def _plot_frame(chart: Chart, left: float, top: float, size_w: float, size_h: float, x_ticks: list, y_ticks: list,
                x_label: str, y_label: str, x_format, y_format) -> tuple:
    x_top, y_top = x_ticks[-1], y_ticks[-1]
    sx = lambda v: left + size_w * v / x_top  # noqa: E731
    sy = lambda v: top + size_h - size_h * v / y_top  # noqa: E731
    for tick in y_ticks:
        chart.line(left, sy(tick), left + size_w, sy(tick), "axis" if tick == 0 else "grid")
        chart.text(left - 8, sy(tick) + 4, y_format(tick), "tick", "end")
    for tick in x_ticks:
        chart.text(sx(tick), top + size_h + 16, x_format(tick), "tick", "middle")
    chart.line(left, top, left, top + size_h, "axis")
    chart.text(left + size_w / 2, top + size_h + 36, x_label, "", "middle")
    chart.text(left - 46, top - 10, y_label, "")
    return sx, sy


def calibration_line(title: str, subtitle: str, points: list, standalone: bool = True) -> str:
    """Stated probability against the share that was right, with the line where the two are equal.

    points: [{'stated', 'right', 'n', 'tip'}], in order of stated probability.
    """
    size = 300
    chart = Chart(title, subtitle, 54 + size + 78)
    left, top = 76, chart.top + 22
    ticks = [0, 0.25, 0.5, 0.75, 1.0]
    sx, sy = _plot_frame(chart, left, top, size, size, ticks, ticks, "Probability stated", "Share right",
                         percent, percent)
    chart.line(sx(0), sy(0), sx(1), sy(1), "axis")
    chart.text(sx(1) + 8, sy(1) + 4, "stated = observed", "tick")
    if points:
        path = " ".join(f"{'M' if i == 0 else 'L'}{sx(p['stated']):.1f},{sy(p['right']):.1f}" for i, p in enumerate(points))
        chart.add(f'<path d="{path}" class="line"/>')
        for p in points:
            chart.mark(f'<circle cx="{sx(p["stated"]):.1f}" cy="{sy(p["right"]):.1f}" r="5" class="dot"', p["tip"])
    return chart.svg(standalone)


def grouped_columns(title: str, subtitle: str, categories: list, series: list, x_label: str,
                    standalone: bool = True) -> str:
    """Columns side by side per category, for two series of shares.

    series: [{'name', 'class', 'values': [share, ...], 'tips': [str, ...]}].
    """
    height = 220
    chart = Chart(title, subtitle, 54 + 26 + height + 62)
    left, top = 60, chart.top + 34
    right = chart.width - 24
    top_value = max(max(v for v in s["values"]) for s in series) or 1.0
    ticks = nice_ticks(top_value, 4)
    sy = lambda v: top + height - height * v / ticks[-1]  # noqa: E731
    _legend(chart, [(s["class"], s["name"]) for s in series], chart.top + 12)
    for tick in ticks:
        chart.line(left, sy(tick), right, sy(tick), "axis" if tick == 0 else "grid")
        chart.text(left - 8, sy(tick) + 4, percent(tick), "tick", "end")
    band = (right - left) / len(categories)
    thick = min(24, (band - 10) / len(series) - 2)
    for c, category in enumerate(categories):
        x = left + c * band + (band - len(series) * (thick + 2)) / 2
        for s, one in enumerate(series):
            value = one["values"][c]
            if value > 0:
                x0, y0 = x + s * (thick + 2), sy(value)
                r = min(4.0, thick / 2, sy(0) - y0)
                path = (f"M{x0:.1f},{sy(0):.1f} V{y0 + r:.1f} Q{x0:.1f},{y0:.1f} {x0 + r:.1f},{y0:.1f} "
                        f"H{x0 + thick - r:.1f} Q{x0 + thick:.1f},{y0:.1f} {x0 + thick:.1f},{y0 + r:.1f} "
                        f"V{sy(0):.1f} Z")
                chart.mark(f'<path d="{path}" class="{one["class"]}"', one["tips"][c])
        chart.text(left + c * band + band / 2, top + height + 16, category, "tick", "middle")
    chart.text((left + right) / 2, top + height + 38, x_label, "", "middle")
    return chart.svg(standalone)


def scatter(title: str, subtitle: str, points: list, x_label: str, y_label: str, standalone: bool = True) -> str:
    """One dot per point. points: [{'x', 'y', 'tip'}]."""
    height = 280
    chart = Chart(title, subtitle, 54 + height + 78)
    left, top = 76, chart.top + 22
    width = chart.width - left - 40
    x_ticks = nice_ticks(max((p["x"] for p in points), default=1), 6)
    y_ticks = nice_ticks(max((p["y"] for p in points), default=1), 5)
    sx, sy = _plot_frame(chart, left, top, width, height, x_ticks, y_ticks, x_label, y_label, _number, _number)
    for p in points:
        chart.mark(f'<circle cx="{sx(p["x"]):.1f}" cy="{sy(p["y"]):.1f}" r="5" class="dot"', p["tip"])
    return chart.svg(standalone)
