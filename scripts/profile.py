import argparse
import base64
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "profile"
SNAPSHOT = ROOT / "data" / "profile.json"
USER = "sorried"
BG = "#181819"
FG = "#f1eeea"
MUTED = "#aaa6a5"
LINE = "#363435"
ACCENT = "#e6a58e"
GLYPHS = {}
LANGUAGES = {
    "Python": ("python", "#9bbde1"),
    "Swift": ("swift", "#efa18d"),
    "JavaScript": ("javascript", "#e7d58c"),
    "TypeScript": ("typescript", "#91b5ee"),
    "Rust": ("rust", "#d9b49d"),
    "HTML": ("html5", "#da9bb2"),
    "CSS": ("css", "#b0a0e2"),
    "Shell": ("gnubash", "#a9c5ac"),
    "Go": ("go", "#8ec9cf"),
    "Dockerfile": ("docker", "#91b5ee"),
}
PROJECTS = [
    ("xyecoc-ipa", "Swift", "iOS", "A SwiftUI client for xyecoc.com mail. Multiple accounts, offline access and automatic IPA builds.", "mail client"),
    ("freshupdate", "TypeScript", "Telegram", "Release notifications for freshGram. Built with grammY and SQLite.", "release bot"),
    ("disable-shorts", "JavaScript", "Chrome", "Hides YouTube Shorts and Playables from feeds, search and navigation. Includes an on/off toggle.", "browser extension"),
]


def api(path, query=None):
    command = ["gh", "api", path]
    command += ["-f", f"query={query}"] if query else ["--paginate", "--slurp"]
    result = json.loads(subprocess.check_output(command, text=True, timeout=90))
    if query:
        if result.get("errors"):
            raise RuntimeError(result["errors"])
        return result["data"]
    if isinstance(result[0], list):
        return [item for page in result for item in page]
    return result[0]


def refresh():
    profile = api(f"users/{USER}")
    repos = api(f"users/{USER}/repos?type=owner&per_page=100")
    repos = [repo for repo in repos if not repo["private"]]
    languages = Counter()
    for repo in repos:
        if not repo["fork"] and repo["language"]:
            languages.update(api(f"repos/{USER}/{repo['name']}/languages"))
    result = api("graphql", f'''query {{
      user(login: "{USER}") {{
        contributionsCollection {{
          contributionCalendar {{
            totalContributions
            weeks {{ contributionDays {{ date contributionCount contributionLevel }} }}
          }}
        }}
      }}
    }}''')
    calendar = result["user"]["contributionsCollection"]["contributionCalendar"]
    data = {
        "updated": datetime.now(timezone.utc).date().isoformat(),
        "followers": profile["followers"],
        "repositories": profile["public_repos"],
        "stars": sum(repo["stargazers_count"] for repo in repos if not repo["fork"]),
        "languages": dict(languages.most_common()),
        "calendar": calendar,
        "projects": {
            repo["name"]: {"stars": repo["stargazers_count"]}
            for repo in repos if repo["name"] in {project[0] for project in PROJECTS}
        },
    }
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(data, indent=2) + "\n")
    return data


@lru_cache
def font(family):
    name, weight = ("Unbounded", 600) if family == "heading" else ("Manrope", 500)
    variable = TTFont(ROOT / "assets" / "fonts" / f"{name}.ttf")
    return instantiateVariableFont(variable, {"wght": weight}, inplace=True)


@lru_cache
def glyph(family, char):
    face = font(family)
    name = face.getBestCmap()[ord(char)]
    glyphs = face.getGlyphSet()
    pen = SVGPathPen(glyphs)
    glyphs[name].draw(pen)
    return pen.getCommands(), glyphs[name].width


def measure(value, size=20, family="body"):
    return sum(glyph(family, char)[1] for char in str(value)) * size / font(family)["head"].unitsPerEm


def text(x, y, value, size=20, color=FG, family="body", anchor="start"):
    value = str(value)
    scale = size / font(family)["head"].unitsPerEm
    advance = measure(value, size, family)
    if anchor == "end":
        x -= advance
    elif anchor == "middle":
        x -= advance / 2
    uses = []
    cursor = 0
    for char in value:
        key = f"{family}-{ord(char)}"
        path, width = glyph(family, char)
        GLYPHS[key] = path
        uses.append(f'<use xlink:href="#{key}" transform="translate({cursor:.2f} 0)"/>')
        cursor += width
    return f'<g aria-label="{escape(value, quote=True)}" fill="{color}" transform="translate({x:.2f} {y}) scale({scale:.6f} {-scale:.6f})">{"".join(uses)}</g>'


def paragraph(x, y, value, width, size=20, color=MUTED):
    lines = []
    current = ""
    for word in value.split():
        candidate = f"{current} {word}".strip()
        if current and measure(candidate, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return "".join(text(x, y + i * size * 1.5, row, size, color) for i, row in enumerate(lines))


def line(x1, y1, x2, y2, color=LINE):
    return f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}"/>'


def rect(x, y, width, height, color, extra=""):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}" {extra}/>'


def motion(body, name, delay=0):
    return f'<g class="{name}" style="animation-delay:{delay}s">{body}</g>'


def arrow(x, y):
    return f'<path d="M{x} {y + 16}l16-16m-14 0h14v14" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'


@lru_cache
def icon_paths(name):
    root = ET.parse(ROOT / "assets" / "icons" / f"{name}.svg").getroot()
    return "".join(f'<path d="{node.attrib["d"]}"/>' for node in root.findall("{http://www.w3.org/2000/svg}path"))


def icon(name, x, y, size=24, color=FG):
    paths = icon_paths(name) if name else '<path d="m8 5-7 7 7 7 2-2-5-5 5-5zm8 0-2 2 5 5-5 5 2 2 7-7z"/>'
    return f'<g transform="translate({x} {y}) scale({size / 24})" fill="{color}" aria-label="{name or "code"} icon">{paths}</g>'


def section(title, width, note=""):
    body = text(32, 45, title, 22, family="heading")
    if note:
        body += text(width - 32, 43, note, 18 if width < 800 else 15, MUTED, anchor="end")
    return body


def save(name, height, title, body, width):
    definitions = "".join(f'<path id="{key}" d="{path}"/>' for key, path in GLYPHS.items())
    GLYPHS.clear()
    style = '''
    .turn { transform-box: fill-box; transform-origin: center; animation: turn 28s linear infinite; }
    .float { animation: float 6s ease-in-out infinite; }
    .plane { animation: plane 5s ease-in-out infinite; }
    .nudge { animation: nudge 4s ease-in-out infinite; }
    .reveal { animation: reveal .8s ease-out backwards; }
    .bar { animation: appear 1.3s ease-out; }
    .heat { animation: appear .8s ease-out backwards; }
    .scan { animation: scan 7s ease-in-out infinite; }
    @keyframes turn { to { transform: rotate(360deg); } }
    @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
    @keyframes plane { 0%, 70%, 100% { transform: translate(0, 0); } 35% { transform: translate(4px, -3px); } }
    @keyframes nudge { 0%, 65%, 100% { transform: translate(0, 0); } 35% { transform: translate(3px, -3px); } }
    @keyframes reveal { from { transform: translateY(6px); opacity: .5; } to { transform: translateY(0); opacity: 1; } }
    @keyframes appear { from { opacity: .65; } to { opacity: 1; } }
    @keyframes scan { 0%, 100% { transform: translateX(0); opacity: .3; } 50% { transform: translateX(var(--travel)); opacity: .9; } }
    @media (prefers-reduced-motion: reduce) {
      .turn, .float, .plane, .nudge, .reveal, .bar, .heat, .scan { animation: none; }
      .scan { display: none; }
    }
    '''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">
<title id="title">{escape(title)}</title>
<metadata>Unbounded 600 and Manrope 500. Font outlines under SIL OFL 1.1. Icons from Simple Icons.</metadata>
<defs>{definitions}</defs>
<style>{style}</style>
{rect(0, 0, width, height, BG)}
{body}
</svg>
'''
    suffix = "-mobile" if width < 800 else ""
    (OUTPUT / f"{name}{suffix}.svg").write_text(svg)


def intro(width):
    mobile = width < 800
    edge = width - 32
    avatar_size = 96 if mobile else 140
    cx, cy = width - (96 if mobile else 126), 108 if mobile else 120
    avatar = base64.b64encode((ROOT / "assets" / "avatar.png").read_bytes()).decode()
    body = text(28, 114, "sorried", 48 if mobile else 78, family="heading")
    body += text(32, 156, "Maya Moon / she/her", 20, MUTED)
    body += f'<circle class="turn" cx="{cx}" cy="{cy}" r="{avatar_size / 2 + 10}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-dasharray="72 18 10 18"/>'
    body += motion(f'<image x="{cx - avatar_size / 2}" y="{cy - avatar_size / 2}" width="{avatar_size}" height="{avatar_size}" xlink:href="data:image/png;base64,{avatar}"/>', "float")
    body += text(32, 226, "Bots, Swift apps & open source.", 23 if mobile else 26)
    body += text(32, 262, "Exploring Rust and interface design.", 20, MUTED)
    body += line(32, 290, edge, 290)
    body += text(32, 322, "Russia / RU + EN", 18 if mobile else 16, MUTED)
    body += text(edge, 322, "UTC+5", 18 if mobile else 16, MUTED, anchor="end")
    save("intro", 348, "sorried. Maya Moon, she/her. Bots, Swift apps and open source. Exploring Rust and UI. Russia. Russian and English. UTC+5.", body, width)


def contact(width):
    edge = width - 32
    body = rect(0, 0, width, 76, ACCENT)
    body += motion(icon("telegram", 32, 26, 24, BG), "plane")
    body += text(72, 48, "Telegram", 20, BG, "heading")
    body += text(edge, 47, "@i_sorried", 20, BG, anchor="end")
    save("contact", 76, "Telegram: @i_sorried", body, width)


def about(width):
    mobile = width < 800
    body = section("what I work on", width)
    rows = [
        ("swift", "Native apps", "SwiftUI apps for iOS and macOS. Mail clients, media tools and local workflows."),
        ("telegram", "Telegram", "Bots, userbot modules and desktop plugins. Telethon, grammY and release notifications."),
        ("go", "Learning", "Practising Go, exploring Rust and working on interface design."),
    ]
    step = 148 if mobile else 126
    for i, (slug, title, description) in enumerate(rows):
        y = 88 + i * step
        row = icon(slug, 32, y - 23, 24, ACCENT)
        row += text(72, y, title, 20, family="heading")
        row += paragraph(72, y + 33, description, width - 104, 20)
        body += motion(row, "reveal", i * .15)
        if i < len(rows) - 1:
            body += line(72, y + step - 35, width - 32, y + step - 35)
    save("about", 90 + len(rows) * step, "Native SwiftUI apps for iOS and macOS; Telegram bots, userbot modules and plugins; learning Go, Rust and UI design.", body, width)


def stack(width):
    mobile = width < 800
    column = (width - 32) / 2
    body = section("stack", width)
    items = [("python", "Python", "bots & automation"), ("swift", "Swift", "SwiftUI apps"), ("javascript", "JavaScript", "browser extensions"), ("typescript", "TypeScript", "grammY bots"), ("rust", "Rust", "exploring"), ("go", "Go", "learning"), ("linux", "Linux", "environment"), ("docker", "Docker", "containers")]
    for i, (slug, name, detail) in enumerate(items):
        x, y = 32 + i % 2 * column, 81 + i // 2 * 82
        body += motion(icon(slug, x, y + 2, 32), "float", -i * .7)
        body += text(x + 46, y + 22, name, 20 if mobile else 23)
        body += text(x + 46, y + 49, detail, 18 if mobile else 16, MUTED)
    body += line(32, 412, width - 32, 412)
    body += paragraph(32, 447, "SwiftUI / FFmpeg / Telethon / TgCrypto / grammY / SQLite", width - 64, 19)
    save("stack", 510 if mobile else 480, "Stack: Python, Swift, JavaScript, TypeScript, Rust, Go, Linux and Docker. SwiftUI, FFmpeg, Telethon, TgCrypto, grammY and SQLite.", body, width)


def languages(data, width):
    mobile = width < 800
    edge = width - 32
    values = sorted(data["languages"].items(), key=lambda item: item[1], reverse=True)
    if len(values) > 6:
        values = values[:5] + [("Other", sum(size for _, size in values[5:]))]
    total = sum(size for _, size in values)
    body = section("top languages", width)
    x = 32
    for i, (name, size) in enumerate(values):
        slug, color = LANGUAGES.get(name, (None, MUTED))
        segment = size / total * (width - 64)
        body += rect(round(x, 2), 74, round(segment, 2), 10, color, 'class="bar"')
        x += segment
        column = (width - 32) / 2
        row_x, row_y = 32 + i % 2 * column, 112 + i // 2 * 60
        body += icon(slug, row_x, row_y, 24, color)
        body += text(row_x + 36, row_y + 20, name, 18 if mobile else 21)
        percent = size / total * 100
        label = f"{percent:.1f}%" if percent >= .1 else "<0.1%"
        body += text(row_x + column - 32, row_y + 21, label, 19 if mobile else 20, MUTED, anchor="end")
    foot_y = 123 + ((len(values) + 1) // 2) * 60
    if not values:
        body += text(32, 124, "No public language data yet.", 20, MUTED)
        foot_y = 178
    body += line(32, foot_y - 21, edge, foot_y - 21)
    body += text(32, foot_y + 8, "Public code by bytes / forks excluded", 18 if mobile else 15, MUTED)
    save("languages", foot_y + 36, "Top languages by bytes in public non-fork repositories, refreshed daily.", body, width)


def activity(data, width):
    mobile = width < 800
    edge = width - 32
    calendar = data["calendar"]
    body = section("activity", width, data["updated"])
    metrics = [(calendar["totalContributions"], "contributions / year"), (data["repositories"], "public repos"), (data["followers"], "followers"), (data["stars"], "stars earned")]
    for i, (value, label) in enumerate(metrics):
        x = 32 + (i % 2) * 244 if mobile else 32 + i * 188
        offset = (i // 2) * 100 if mobile else 0
        body += text(x, 114 + offset, f"{value:,}", 38, family="heading")
        body += text(x, 145 + offset, label, 19 if mobile else 16, MUTED)
    offset = 100 if mobile else 0
    body += line(32, 174 + offset, edge, 174 + offset)
    body += text(32, 210 + offset, "last 26 weeks", 17, MUTED)
    shades = {"NONE": "#2e2c2d", "FIRST_QUARTILE": "#67483f", "SECOND_QUARTILE": "#986553", "THIRD_QUARTILE": "#bf836b", "FOURTH_QUARTILE": ACCENT}
    for week_index, week in enumerate(calendar["weeks"][-26:]):
        for day in week["contributionDays"]:
            weekday = (datetime.fromisoformat(day["date"]).weekday() + 1) % 7
            x, y = 58 + week_index * ((width - 98) / 26), 232 + offset + weekday * 18
            body += f'<g><title>{day["date"]}: {day["contributionCount"]} contributions</title>'
            body += motion(rect(round(x, 1), y, 12 if mobile else 21, 12, shades[day["contributionLevel"]]), "heat", week_index * .025) + '</g>'
    for y, label in [(262, "m"), (298, "w"), (334, "f")]:
        body += text(32, y + offset, label, 13, MUTED)
    body += text(32, 386 + offset, "updated daily", 18 if mobile else 15, MUTED)
    body += text(edge - 166, 386 + offset, "less", 17 if mobile else 13, MUTED)
    for i, color in enumerate(shades.values()):
        body += rect(edge - 132 + i * 17, 375 + offset, 12, 12, color)
    body += text(edge - 40, 386 + offset, "more", 17 if mobile else 13, MUTED)
    save("activity", 414 + offset, "GitHub activity. Contributions, public repositories, followers, stars and the last 26 weeks of contributions. Updated daily.", body, width)


def recent_stats(data):
    today = date.fromisoformat(data["updated"])
    days = {
        date.fromisoformat(day["date"]): day["contributionCount"]
        for week in data["calendar"]["weeks"] for day in week["contributionDays"]
        if date.fromisoformat(day["date"]) <= today
    }
    recent = [days.get(today - timedelta(days=i), 0) for i in range(30)]
    cursor = today if days.get(today, 0) else today - timedelta(days=1)
    current = 0
    while days.get(cursor, 0):
        current += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    if days:
        cursor = min(days)
        while cursor <= today:
            run = run + 1 if days.get(cursor, 0) else 0
            longest = max(longest, run)
            cursor += timedelta(days=1)
    return sum(recent), sum(count > 0 for count in recent), current, longest


def recent(data, width):
    mobile = width < 800
    totals = recent_stats(data)
    body = section("recent activity", width)
    labels = ["contributions / 30 days", "active days / 30 days", "current streak / days", "longest / past year"]
    for i, (value, label) in enumerate(zip(totals, labels)):
        x, y = 32 + (i % 2) * ((width - 32) / 2), 114 + (i // 2) * 104
        body += motion(text(x, y, value, 38, family="heading"), "reveal", i * .12)
        body += text(x, y + 32, label, 18 if mobile else 20, MUTED)
    body += line(32, 278, width - 32, 278)
    body += rect(32, 277, 48, 2, ACCENT, f'class="scan" style="--travel:{width - 112}px"')
    body += text(32, 312, "Streaks count consecutive contribution days.", 18, MUTED)
    title = f"Last 30 days: {totals[0]} contributions on {totals[1]} active days. Current streak: {totals[2]} days. Longest streak in the past year: {totals[3]} days."
    save("recent", 340, title, body, width)


def projects(data, width):
    mobile = width < 800
    edge = width - 32
    save("projects", 70, "Projects: click a project to open its repository.", section("projects", width, "open a repository"), width)
    for name, language, platform, description, kind in PROJECTS:
        slug, color = LANGUAGES[language]
        body = icon(slug, 32, 28, 32, color)
        body += text(82, 51, name, 23 if mobile else 27, family="heading")
        body += motion(arrow(edge - 16, 30), "nudge")
        body += paragraph(32, 91, description, width - 64, 20)
        offset = 70 if mobile else 36
        body += text(32, 128 + offset, f"{language} / {platform}", 19 if mobile else 16, MUTED)
        body += text(edge, 128 + offset, f'{data["projects"][name]["stars"]} stars', 19 if mobile else 16, MUTED, anchor="end")
        body += text(32, 158 + offset, kind, 18 if mobile else 16, MUTED)
        body += line(32, 178 + offset, edge, 178 + offset)
        save(name.lower(), 190 + offset, f"{name}. {description} {kind}.", body, width)


def render(data):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for width in (800, 520):
        intro(width)
        contact(width)
        about(width)
        stack(width)
        languages(data, width)
        activity(data, width)
        recent(data, width)
        projects(data, width)
        body = text(32, 45, "still here, still you.", 20, MUTED)
        body += icon("github", width - 56, 24, 24, MUTED)
        save("footer", 76, "Still here, still you.", body, width)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    data = refresh() if args.refresh else json.loads(SNAPSHOT.read_text())
    render(data)
    print(f"Rendered profile from {data['updated']} to {OUTPUT.relative_to(ROOT)}")
