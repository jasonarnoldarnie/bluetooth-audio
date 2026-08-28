#!/usr/bin/env python3
"""Render a Markdown document to PDF with no third-party dependencies.

    python md_to_pdf.py docs/design-overview.md
    python md_to_pdf.py docs/design-overview.md -o build/overview.pdf
    python md_to_pdf.py docs/design-overview.md --html-only   # keep the intermediate HTML

Why it exists: this is called from a git hook, so it must run on a bare machine with
nothing installed. It uses pandoc when pandoc is on PATH (better typography, real
footnotes) and otherwise falls back to headless Chrome or Edge, one of which is present
on any Windows box and on most Linux/macOS developer machines.

The bundled Markdown converter handles the subset these design documents actually use:
ATX headings, GFM tables, fenced and indented code, bullet and numbered lists,
blockquotes, horizontal rules, images, links, bold/italic/strikethrough and inline code.
It is deliberately not a general Markdown implementation - if a document starts needing
one, install pandoc rather than growing this file.

Exit codes: 0 rendered, 1 bad input, 2 no renderer available.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- #
# Markdown -> HTML
# --------------------------------------------------------------------------- #

_INLINE_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_ITALIC = re.compile(r"(?<![\*\w])\*(?=\S)([^\*]+?)(?<=\S)\*(?!\*)")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
_AUTOLINK = re.compile(r"(?<![\"'=(\[])\bhttps?://[^\s<>\)\]]+")


def _inline(text: str) -> str:
    """Convert inline Markdown in one line of already-plain text to HTML."""
    placeholders: list[str] = []

    def stash(markup: str) -> str:
        placeholders.append(markup)
        return f"\x00{len(placeholders) - 1}\x00"

    # Code spans win over every other inline rule, so they are extracted first and
    # re-inserted last. Otherwise `**` inside a code span gets bolded.
    text = _INLINE_CODE.sub(lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text, quote=False)
    text = _IMAGE.sub(lambda m: stash(f'<img src="{m.group(2)}" alt="{m.group(1)}">'), text)
    text = _LINK.sub(lambda m: stash(f'<a href="{m.group(2)}">{m.group(1)}</a>'), text)
    text = _AUTOLINK.sub(lambda m: stash(f'<a href="{m.group(0)}">{m.group(0)}</a>'), text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _STRIKE.sub(r"<del>\1</del>", text)

    for i, markup in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", markup)
    return text


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    # Split on pipes that are not escaped.
    cells = re.split(r"(?<!\\)\|", line)
    return [c.strip().replace("\\|", "|") for c in cells]


def _is_table_delimiter(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?[\s:|-]+\|[\s:|-]*", line)) and "-" in line


def _alignments(delim: str) -> list[str]:
    out = []
    for cell in _split_row(delim):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else "right" if right else "left")
    return out


def markdown_to_html_body(md: str) -> str:
    """Convert a Markdown document to an HTML fragment."""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    # Open list stack: each entry is ("ul"|"ol", indent_columns)
    stack: list[tuple[str, int]] = []
    i = 0

    def close_lists(to_indent: int = -1) -> None:
        while stack and stack[-1][1] > to_indent:
            out.append(f"</{stack.pop()[0]}>")

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code
        fence = re.match(r"^\s*(```+|~~~+)(.*)$", line)
        if fence:
            close_lists()
            marker = fence.group(1)[:3]
            lang = fence.group(2).strip().split()[0] if fence.group(2).strip() else ""
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                body.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        # Horizontal rule (before the list check: '---' is not a bullet)
        if re.fullmatch(r"\s*(\*\s*\*\s*\*[\s\*]*|-\s*-\s*-[\s-]*|_\s*_\s*_[\s_]*)", line):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # Heading
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading:
            close_lists()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        # Table: a header row followed by a delimiter row
        if "|" in stripped and i + 1 < len(lines) and _is_table_delimiter(lines[i + 1]):
            close_lists()
            headers = _split_row(line)
            aligns = _alignments(lines[i + 1])
            aligns += ["left"] * (len(headers) - len(aligns))
            out.append("<table><thead><tr>")
            for n, cell in enumerate(headers):
                out.append(f'<th style="text-align:{aligns[n]}">{_inline(cell)}</th>')
            out.append("</tr></thead><tbody>")
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                cells = _split_row(lines[i])
                out.append("<tr>")
                for n, cell in enumerate(cells):
                    align = aligns[n] if n < len(aligns) else "left"
                    out.append(f'<td style="text-align:{align}">{_inline(cell)}</td>')
                out.append("</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        # Blockquote (flattened - nesting is not used in these documents)
        if re.match(r"^\s{0,3}>", line):
            close_lists()
            body = []
            while i < len(lines) and re.match(r"^\s{0,3}>", lines[i]):
                body.append(re.sub(r"^\s{0,3}>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(b.strip() for b in body))}</blockquote>")
            continue

        # List item
        item = re.match(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$", line)
        if item:
            indent = len(item.group(1).expandtabs(4))
            kind = "ul" if item.group(2) in "-+*" else "ol"
            close_lists(indent)
            if not stack or stack[-1][1] < indent:
                stack.append((kind, indent))
                out.append(f"<{kind}>")
            elif stack[-1][0] != kind:
                out.append(f"</{stack.pop()[0]}>")
                stack.append((kind, indent))
                out.append(f"<{kind}>")
            out.append(f"<li>{_inline(item.group(3))}</li>")
            i += 1
            continue

        # Paragraph: consume until a blank line or a construct that starts a new block
        close_lists()
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip():
            nxt = lines[i]
            if re.match(r"^\s{0,3}(#{1,6}\s|>|```|~~~)", nxt) or re.match(
                r"^(\s*)([-+*]|\d+[.)])\s+", nxt
            ):
                break
            if "|" in nxt and i + 1 < len(lines) and _is_table_delimiter(lines[i + 1]):
                break
            para.append(nxt.strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")

    close_lists()
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Page shell
# --------------------------------------------------------------------------- #

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body {
  font: 10.5pt/1.5 "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
  color: #14171a; margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.25; margin: 1.35em 0 0.5em; page-break-after: avoid; }
h1 { font-size: 20pt; margin-top: 0; border-bottom: 2px solid #14171a; padding-bottom: 0.25em; }
h2 { font-size: 14pt; border-bottom: 1px solid #c9d1d9; padding-bottom: 0.2em; }
h3 { font-size: 11.5pt; }
h4, h5, h6 { font-size: 10.5pt; }
p, ul, ol, blockquote, table { margin: 0.55em 0; }
ul, ol { padding-left: 1.5em; }
li { margin: 0.15em 0; }
a { color: #0b5cad; text-decoration: none; word-break: break-word; }
code {
  font-family: "Cascadia Mono", Consolas, "SF Mono", monospace; font-size: 0.88em;
  background: #f2f4f7; border: 1px solid #e2e6ea; border-radius: 3px; padding: 0.08em 0.3em;
}
pre {
  background: #f7f8fa; border: 1px solid #e2e6ea; border-radius: 4px; padding: 0.7em 0.9em;
  overflow-x: auto; page-break-inside: avoid;
}
pre code { background: none; border: 0; padding: 0; font-size: 0.84em; line-height: 1.45; }
blockquote {
  border-left: 3px solid #b9c2cc; padding: 0.1em 0 0.1em 0.9em; color: #414a53; margin-left: 0;
}
table { border-collapse: collapse; width: 100%; font-size: 9pt; page-break-inside: auto; }
th, td { border: 1px solid #ccd3da; padding: 4px 7px; vertical-align: top; }
th { background: #eef1f5; font-weight: 600; text-align: left; }
tr { page-break-inside: avoid; }
tbody tr:nth-child(even) { background: #fafbfc; }
img { max-width: 100%; }
hr { border: 0; border-top: 1px solid #d6dce2; margin: 1.4em 0; }
.doc-stamp {
  font-size: 8pt; color: #6b7681; border-top: 1px solid #e2e6ea;
  margin-top: 2.5em; padding-top: 0.6em;
}
"""


def build_html(md_text: str, title: str, stamp: str | None) -> str:
    body = markdown_to_html_body(md_text)
    footer = f'<div class="doc-stamp">{html.escape(stamp)}</div>' if stamp else ""
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>\n{body}\n{footer}\n</body></html>\n"
    )


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

def _browser_candidates() -> list[str]:
    names = ["chrome", "google-chrome", "chromium", "chromium-browser", "msedge", "microsoft-edge"]
    found = [p for p in (shutil.which(n) for n in names) if p]
    for path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]:
        if os.path.exists(path):
            found.append(path)
    seen, ordered = set(), []
    for p in found:
        if p.lower() not in seen:
            seen.add(p.lower())
            ordered.append(p)
    return ordered


def render_with_browser(html_path: Path, pdf_path: Path) -> str | None:
    """Print an HTML file to PDF with headless Chrome/Edge. Returns the browser used."""
    for browser in _browser_candidates():
        with tempfile.TemporaryDirectory() as profile:
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=4000",
                f"--user-data-dir={profile}",
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired):
                continue
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return browser
        sys.stderr.write(
            f"  {Path(browser).name} failed: {proc.stderr.decode('utf-8', 'replace').strip()[:300]}\n"
        )
    return None


def render_with_pandoc(md_path: Path, pdf_path: Path) -> bool:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return False
    # pandoc's PDF output needs a LaTeX or wkhtmltopdf engine; if none is installed this
    # fails and we fall through to the browser path rather than erroring out.
    cmd = [
        pandoc, str(md_path), "-o", str(pdf_path),
        "--from", "gfm", "--standalone",
        "--variable", "geometry:a4paper,margin=18mm",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
        return True
    sys.stderr.write("  pandoc could not produce a PDF; falling back to a browser.\n")
    return False


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Markdown file to PDF, dependency-free.")
    ap.add_argument("markdown", type=Path, help="source .md file")
    ap.add_argument("-o", "--output", type=Path, help="output .pdf (default: alongside the source)")
    ap.add_argument("--title", help="document title (default: first H1, else the filename)")
    ap.add_argument("--stamp", help="footer line, e.g. 'Generated from commit abc1234'")
    ap.add_argument("--html-only", action="store_true", help="write the intermediate HTML and stop")
    ap.add_argument("--no-pandoc", action="store_true", help="skip pandoc even if installed")
    args = ap.parse_args()

    # Resolved, not relative: the browser is handed a file:// URI, and a relative path
    # cannot be expressed as one. Hooks always invoke this with relative paths.
    md_path: Path = args.markdown.resolve()
    if not md_path.is_file():
        sys.stderr.write(f"error: no such file: {md_path}\n")
        return 1

    pdf_path: Path = (args.output.resolve() if args.output else md_path.with_suffix(".pdf"))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    md_text = md_path.read_text(encoding="utf-8")
    title = args.title
    if not title:
        m = re.search(r"^\s{0,3}#\s+(.+)$", md_text, re.M)
        title = m.group(1).strip() if m else md_path.stem

    if args.html_only:
        out = pdf_path.with_suffix(".html")
        out.write_text(build_html(md_text, title, args.stamp), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    if not args.no_pandoc and render_with_pandoc(md_path, pdf_path):
        print(f"wrote {pdf_path} (pandoc)")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        # Written next to the source, not in the temp dir, so relative image paths resolve.
        html_path = md_path.parent / f".{md_path.stem}.render.html"
        html_path.write_text(build_html(md_text, title, args.stamp), encoding="utf-8")
        try:
            browser = render_with_browser(html_path, pdf_path)
        finally:
            html_path.unlink(missing_ok=True)
        del tmp

    if not browser:
        sys.stderr.write(
            "error: no PDF renderer available.\n"
            "  Install pandoc (with a PDF engine), or Chrome or Edge, then re-run.\n"
        )
        return 2

    print(f"wrote {pdf_path} ({Path(browser).name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
