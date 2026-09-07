#!/usr/bin/env python3
"""Build index.html (landing page) and cv.tex (detailed CV) from cv.yml.

    python3 build.py            # -> build/index.html, build/cv.tex

cv.yml is the only place wording lives. preamble.tex and the CSS below are
layout. Write plain text in cv.yml — this script handles LaTeX escaping
(%, &, _, #, ~) and HTML escaping, plus a small inline markup:

    **bold**   *italic*   [link text](https://example.com)
"""

import argparse
import html
import shutil
import os
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "build"

# ---------------------------------------------------------------- escaping ---

# Order matters: backslash first, or you double-escape the escapes.
TEX_ESCAPES = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"$\sim$"),
    ("^", r"\textasciicircum{}"),
]


def tex(s):
    """Escape plain text for LaTeX."""
    s = str(s)
    for char, repl in TEX_ESCAPES:
        s = s.replace(char, repl)
    # Typographic dashes, so "2020-2022" and "2022---" survive as written.
    return s


def esc(s):
    """Escape plain text for HTML."""
    return html.escape(str(s), quote=True)


# ----------------------------------------------------------- inline markup ---

INLINE_RE = re.compile(
    r"\[([^\]]+)\]\(([^)\s]+)\)"   # 1,2  [text](url)
    r"|\*\*(.+?)\*\*"              # 3    **bold**
    r"|\*(.+?)\*"                  # 4    *italic*
)


def inline(s, mode):
    """Render **bold**, *italic* and [text](url) for 'tex' or 'html'.

    Everything outside the markup is escaped for the target; URLs are passed
    through verbatim, because escaping an href breaks it.
    """
    s = str(s)
    escape = tex if mode == "tex" else esc
    out, pos = [], 0
    for m in INLINE_RE.finditer(s):
        out.append(escape(s[pos:m.start()]))
        if m.group(1) is not None:
            text, url = escape(m.group(1)), m.group(2)
            out.append(
                f"\\href{{{url}}}{{{text}}}" if mode == "tex"
                else f'<a href="{esc(url)}">{text}</a>'
            )
        elif m.group(3) is not None:
            t = escape(m.group(3))
            out.append(f"\\textbf{{{t}}}" if mode == "tex" else f"<strong>{t}</strong>")
        else:
            t = escape(m.group(4))
            out.append(f"\\textit{{{t}}}" if mode == "tex" else f"<em>{t}</em>")
        pos = m.end()
    out.append(escape(s[pos:]))
    return "".join(out)


def itex(s):
    return inline(s, "tex")


def ihtml(s):
    return inline(s, "html")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


# ------------------------------------------------------------------ loading ---

SECRET_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def resolve_secrets(obj, secrets, missing):
    """Replace ${NAME} with the env var / secrets.local.yml value."""
    if isinstance(obj, dict):
        return {k: resolve_secrets(v, secrets, missing) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_secrets(v, secrets, missing) for v in obj]
    if isinstance(obj, str):
        def sub(m):
            key = m.group(1)
            if key in secrets:
                return secrets[key]
            missing.add(key)
            return m.group(0)
        return SECRET_RE.sub(sub, obj)
    return obj


def load():
    data = yaml.safe_load((ROOT / "cv.yml").read_text(encoding="utf-8"))

    # Values kept out of the public repo. Env first (CI), then a gitignored
    # local file (your machine). Never committed either way.
    secrets = dict(os.environ)
    local = ROOT / "secrets.local.yml"
    if local.exists():
        for k, v in (yaml.safe_load(local.read_text()) or {}).items():
            secrets.setdefault(k, str(v))

    missing = set()
    data = resolve_secrets(data, secrets, missing)
    if missing:
        # Hard fail: a CV that ships with a literal ${RESUME_PHONE} is worse than no
        # CV at all, because you would not notice before sending it.
        sys.exit(
            "Unresolved placeholder(s): "
            + ", ".join(sorted(missing))
            + "\nSet them as env vars, or create secrets.local.yml (gitignored):\n"
            + "\n".join(f"  {k}: your-value" for k in sorted(missing))
        )

    for key in ("profile", "site", "cv"):
        if key not in data:
            sys.exit(f"cv.yml is missing the top-level '{key}:' block.")
    return data


def enabled(items):
    return [i for i in (items or []) if i.get("enabled", True)]


# --------------------------------------------------------------------- tex ---


def clean_url(url):
    """tel: links keep only + and digits; everything else passes through."""
    url = str(url)
    if url.startswith("tel:"):
        return "tel:" + re.sub(r"[^0-9+]", "", url[4:])
    return url


def tex_contact(contact):
    """The centred line of email / phone / links under the name."""
    parts = []
    for c in enabled(contact):
        label = c.get("label")
        value = itex(c["value"]) if c.get("value") else ""
        body = f"{tex(label)}: {value}" if label else value
        url = c.get("url")
        if url:
            # hrefWithoutArrow keeps the header clean; the black keeps the
            # header line uniform instead of a row of blue.
            parts.append(
                f"\\mbox{{\\hrefWithoutArrow{{{clean_url(url)}}}{{\\color{{black}}{body}}}}}"
            )
        else:
            parts.append(f"\\mbox{{{body}}}")
    sep = "%\n        \\kern 0.25 cm\\textbar\\kern 0.25 cm%\n        "
    return sep.join(parts)


def tex_entry_head(e):
    """Bold lead-in plus optional unbolded remainder, e.g. **Oxford**, Nuffield."""
    bits = []
    if e.get("title"):
        bits.append(f"\\textbf{{{itex(e['title'])}}}")
    if e.get("title_rest"):
        bits.append(itex(e["title_rest"]))
    return "".join(bits)


def tex_lines(lines, indent, blank_first=True):
    """Paragraph-per-line inside an entry (a blank line is a \\par in LaTeX).

    blank_first=False for an entry with no heading above it, where a leading
    \\par would open the entry with an empty line.
    """
    out = []
    for i, line in enumerate(lines):
        if i or blank_first:
            out.append("")
        out.append(f"{indent}{itex(line)}")
    return out


def tex_bullets(items, indent):
    out = [f"{indent}\\begin{{highlights}}"]
    for it in items:
        out.append(f"{indent}    \\item {itex(it)}")
    out.append(f"{indent}\\end{{highlights}}")
    return out


def tex_dated_section(section):
    """Entries with a right-hand date column: education, prizes, talks, teaching."""
    out = []
    entries = enabled(section.get("entries"))
    for i, e in enumerate(entries):
        if i:
            out.append("")
            out.append("        \\vspace{0.4 cm}")
            out.append("")
        date = itex(e.get("date", ""))
        out.append(f"        \\begin{{twocolentry}}{{{date}}}")
        head = tex_entry_head(e)
        if head:
            out.append(f"            {head}")
        body = e.get("lines") or ([e["text"]] if e.get("text") else [])
        if body:
            out.extend(tex_lines(body, "            ", blank_first=bool(head)))
        elif not head:
            # paracol needs something in the left column or the row collapses.
            out.append("            ~")
        out.append("        \\end{twocolentry}")
        if e.get("items"):
            out.append("")
            out.append("        \\vspace{0.2 cm}")
            out.append("")
            out.append("        \\begin{onecolentry}")
            out.extend(tex_bullets(e["items"], "            "))
            out.append("        \\end{onecolentry}")
    return out


def tex_block_section(section):
    """Full-width blocks: 'Fields: ...', 'Working Papers:' + list, languages, etc."""
    out = []
    blocks = enabled(section.get("blocks"))
    for i, b in enumerate(blocks):
        if i:
            out.append("")
            out.append("        \\vspace{0.4 cm}")
            out.append("")
        out.append("        \\begin{onecolentry}")
        lead = f"\\textbf{{{itex(b['label'])}:}} " if b.get("label") else ""
        out.append(f"            {lead}{itex(b['text']) if b.get('text') else ''}".rstrip())
        if b.get("items"):
            out.extend(tex_bullets(b["items"], "            "))
        out.append("        \\end{onecolentry}")
    return out


def tex_references_section(section):
    people = enabled(section.get("people"))
    if not people:
        return []
    cols = "@{\\hspace{0.6 cm}}".join(["l"] * len(people))
    rows = [[f"\\textbf{{{itex(p['name'])}}}" for p in people]]
    for key in ("title", "affiliation"):
        if any(p.get(key) for p in people):
            rows.append([itex(p.get(key, "")) for p in people])
    if any(p.get("email") for p in people):
        rows.append([
            f"\\mbox{{\\hrefWithoutArrow{{mailto:{p['email']}}}"
            f"{{\\color{{black}}{itex(p['email'])}}}}}" if p.get("email") else ""
            for p in people
        ])
    out = ["        \\begin{onecolentry}", f"            \\begin{{tabular}}{{{cols}}}"]
    for r in rows:
        out.append("            " + " & ".join(r) + " \\\\")
    out.append("            \\end{tabular}")
    out.append("        \\end{onecolentry}")
    return out


SECTION_BUILDERS = {
    "dated": tex_dated_section,
    "blocks": tex_block_section,
    "references": tex_references_section,
}


def build_tex(data):
    profile, cv = data["profile"], data["cv"]
    name = profile["name"]

    doc = [
        "% Generated by build.py from cv.yml — do not edit; your changes will be lost.",
        "\\input{preamble}",
        "",
        "\\hypersetup{",
        f"    pdftitle={{{tex(name)}'s CV}},",
        f"    pdfauthor={{{tex(name)}}},",
        "}",
        "",
    ]
    if cv.get("last_updated"):
        doc.append(f"\\newcommand{{\\lastupdatedtext}}{{Last updated in {tex(cv['last_updated'])}}}")
        doc.append("\\placelastupdatedtext")
        doc.append("")

    doc += [
        "\\begin{document}",
        "",
        "    \\begin{header}",
        f"        \\textbf{{\\fontsize{{20 pt}}{{20 pt}}\\selectfont {tex(name)}}}",
        "",
        "        \\vspace{0.3 cm}",
        "",
        "        \\normalsize",
        "        " + tex_contact(cv.get("contact")),
        "    \\end{header}",
        "",
        "    \\vspace{0.4 cm}",
    ]

    for section in enabled(cv.get("sections")):
        kind = section.get("kind", "dated")
        if kind not in SECTION_BUILDERS:
            sys.exit(
                f"Section {section.get('heading')!r} has unknown kind {kind!r}. "
                f"Use one of: {', '.join(SECTION_BUILDERS)}."
            )
        doc.append("")
        doc.append(f"    \\section{{{tex(section['heading'])}}}")
        doc.append("")
        doc.extend(SECTION_BUILDERS[kind](section))
        doc.append("")
        doc.append("    \\vspace{0.2 cm}")

    doc += ["", "\\end{document}"]
    return "\n".join(doc) + "\n"


# -------------------------------------------------------------------- html ---

CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: "Source Sans 3", "Helvetica Neue", Arial, sans-serif;
      font-size: 16px;
      line-height: 1.6;
      color: #333;
      background: #fff;
    }

    a {
      color: #8B0000;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }

    /* Layout */
    .container {
      max-width: 960px;
      margin: 0 auto;
      padding: 3rem 2rem 4rem;
      display: flex;
      gap: 3.5rem;
    }

    /* Sidebar */
    .sidebar {
      flex: 0 0 240px;
    }

    .sidebar img {
      width: 100%;
      display: block;
    }

    .sidebar h1 {
      font-family: "Source Serif 4", Georgia, serif;
      font-size: 1.5rem;
      font-weight: 600;
      color: #111;
      margin-top: 1rem;
      line-height: 1.3;
    }

    .sidebar .affiliation {
      font-size: 0.92rem;
      color: #555;
      margin-top: 0.3rem;
      line-height: 1.45;
    }

    .sidebar .contact {
      margin-top: 1.2rem;
      font-size: 0.88rem;
      line-height: 1.7;
    }

    .sidebar .contact a {
      color: #8B0000;
    }

    /* Main content */
    .main {
      flex: 1;
      min-width: 0;
    }

    .main h2 {
      font-family: "Source Serif 4", Georgia, serif;
      font-size: 1.25rem;
      font-weight: 600;
      color: #111;
      border-bottom: 1px solid #ddd;
      padding-bottom: 0.35rem;
      margin-bottom: 1rem;
    }

    .main h2:not(:first-of-type) {
      margin-top: 2.5rem;
    }

    .intro {
      margin-bottom: 0.5rem;
    }

    .paper {
      margin-bottom: 1.8rem;
    }

    .paper-title {
      font-weight: 600;
      font-size: 1rem;
      color: #111;
    }

    .paper-tag {
      font-size: 0.82rem;
      color: #8B0000;
      font-weight: 600;
    }

    .paper-authors {
      font-size: 0.92rem;
      color: #555;
      margin-top: 0.15rem;
    }

    .paper-links {
      margin-top: 0.3rem;
      font-size: 0.88rem;
    }

    .paper-links a {
      margin-right: 0.8rem;
    }

    .abstract-toggle {
      background: none;
      border: none;
      color: #8B0000;
      font-size: 0.88rem;
      cursor: pointer;
      padding: 0;
      font-family: inherit;
    }

    .abstract-toggle:hover {
      text-decoration: underline;
    }

    .abstract {
      display: none;
      margin-top: 0.5rem;
      font-size: 0.9rem;
      color: #444;
      line-height: 1.6;
      border-left: 2px solid #ddd;
      padding-left: 0.8rem;
    }

    .abstract.open {
      display: block;
    }

    /* Responsive */
    @media (max-width: 700px) {
      .container {
        flex-direction: column;
        padding: 2rem 1.2rem;
        gap: 2rem;
      }
      .sidebar {
        flex: none;
        display: flex;
        flex-wrap: wrap;
        align-items: flex-start;
        gap: 1.2rem;
      }
      .sidebar img {
        width: 150px;
      }
      .sidebar-text {
        flex: 1;
        min-width: 180px;
      }
    }

    @media print {
      .container { display: block; max-width: none; padding: 0; }
      .sidebar img { width: 150px; }
      .abstract { display: block; }
      .abstract-toggle { display: none; }
    }

    a:focus-visible, .abstract-toggle:focus-visible {
      outline: 2px solid #8B0000;
      outline-offset: 2px;
    }
"""


def html_sidebar(profile, site):
    out = ['    <div class="sidebar">']
    photo = site.get("photo")
    if photo:
        out.append(f'      <img src="{esc(photo)}" alt="{esc(profile["name"])}">')
    out.append('      <div class="sidebar-text">')
    out.append(f'        <h1>{esc(profile["name"])}</h1>')
    lines = profile.get("affiliation") or []
    if lines:
        joined = "<br>\n          ".join(ihtml(l) for l in lines)
        out.append(f'        <div class="affiliation">\n          {joined}\n        </div>')
    contact = enabled(site.get("contact"))
    if contact:
        out.append('        <div class="contact">')
        for c in contact:
            label = f'{esc(c["label"])}: ' if c.get("label") else ""
            value = ihtml(c.get("value", ""))
            if c.get("url"):
                value = f'<a href="{esc(c["url"])}">{value}</a>'
            out.append(f"          <div>{label}{value}</div>")
        out.append("        </div>")
    out.append("      </div>")
    out.append("    </div>")
    return out


def on(block):
    """A `paper:` / `abstract:` block counts only if present and enabled."""
    return bool(block) and block.get("enabled", True)


def html_paper(p):
    out = ['      <div class="paper">']
    title = f'<span class="paper-title">{ihtml(p["title"])}</span>'
    if p.get("tag"):
        title += f'<span class="paper-tag">&ensp;({esc(p["tag"])})</span>'
    out.append(f"        {title}")
    if p.get("authors"):
        out.append(f'        <div class="paper-authors">{ihtml(p["authors"])}</div>')

    paper, abstract = p.get("paper"), p.get("abstract")
    # The abstract needs a url to link to or text to expand; enabled alone
    # would render a control that does nothing.
    show_paper = on(paper) and paper.get("url")
    show_abstract = on(abstract) and (abstract.get("url") or abstract.get("text"))

    if show_paper or show_abstract:
        out.append('        <div class="paper-links">')
        if show_paper:
            out.append(
                f'          <a href="{esc(paper["url"])}" target="_blank" '
                'rel="noopener">Paper</a>'
            )
        if show_abstract and abstract.get("url"):
            out.append(
                f'          <a href="{esc(abstract["url"])}" target="_blank" '
                'rel="noopener">Abstract</a>'
            )
        elif show_abstract:
            out.append(
                '          <button class="abstract-toggle" type="button" '
                'aria-expanded="false" onclick="toggleAbstract(this)">Abstract &#9656;</button>'
            )
        out.append("        </div>")

    if show_abstract and not abstract.get("url"):
        out.append(f'        <div class="abstract">{ihtml(abstract["text"].strip())}</div>')
    out.append("      </div>")
    return out


def build_html(data):
    profile, site = data["profile"], data["site"]
    body = []
    for section in enabled(site.get("sections")):
        heading = section["heading"]
        body.append(f'      <h2 id="{slug(heading)}">{esc(heading)}</h2>')
        kind = section.get("kind", "text")
        if kind == "text":
            for para in section.get("paragraphs") or []:
                body.append(f'      <p class="intro">{ihtml(para.strip())}</p>')
        elif kind == "papers":
            for p in enabled(section.get("papers")):
                body.extend(html_paper(p))
        else:
            sys.exit(
                f"Site section {heading!r} has unknown kind {kind!r}. "
                "Use 'text' or 'papers'."
            )
        body.append("")

    desc = site.get("description") or profile["name"]
    sidebar = "\n".join(html_sidebar(profile, site))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(profile["name"])}</title>
  <meta name="description" content="{esc(desc)}">
  <meta property="og:title" content="{esc(profile["name"])}">
  <meta property="og:description" content="{esc(desc)}">
  <meta property="og:type" content="profile">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;1,400&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
  <style>{CSS}  </style>
</head>
<body>
  <div class="container">
    <!-- Sidebar -->
{sidebar}

    <!-- Main -->
    <div class="main">
{chr(10).join(body).rstrip()}
    </div>
  </div>

  <script>
    function toggleAbstract(btn) {{
      var el = btn.parentElement.nextElementSibling;
      var open = el.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
      btn.innerHTML = open ? 'Abstract \\u25BE' : 'Abstract \\u25B8';
    }}
  </script>
</body>
</html>
"""


# -------------------------------------------------------------------- main ---


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    data = load()
    OUT.mkdir(exist_ok=True)
    stem = data["cv"].get("filename", "cv")
    (OUT / f"{stem}.tex").write_text(build_tex(data), encoding="utf-8")
    (OUT / "index.html").write_text(build_html(data), encoding="utf-8")
    # \input{preamble} resolves relative to the .tex, so it has to sit alongside it.
    shutil.copy(ROOT / "preamble.tex", OUT / "preamble.tex")
    # Mirror assets/ so build/index.html previews locally exactly as it deploys.
    if (ROOT / "assets").is_dir():
        shutil.copytree(ROOT / "assets", OUT / "assets", dirs_exist_ok=True)
    print(f"Built build/{stem}.tex and build/index.html")

    # A missing photo or paper is a broken image / 404 on the live site, and you
    # only notice after it is published. Say so now instead.
    photo = data["site"].get("photo")
    wanted = [photo] if photo else []
    for section in enabled(data["site"].get("sections")):
        for paper in enabled(section.get("papers")):
            for block in (paper.get("paper"), paper.get("abstract")):
                if on(block) and block.get("url"):
                    wanted.append(block["url"])
    for ref in wanted:
        if not re.match(r"[a-z]+:|//", ref) and not (ROOT / ref).exists():
            print(f"  warning: {ref} is linked from index.html but does not exist")


if __name__ == "__main__":
    main()
