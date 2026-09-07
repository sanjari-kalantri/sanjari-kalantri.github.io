# sanjarikalantri.github.io

Personal website and CV. Both are generated from **one file: `cv.yml`**.

| You edit | It becomes |
| --- | --- |
| `cv.yml` → `site:` | `index.html`, the landing page |
| `cv.yml` → `cv:`   | `cv.pdf`, the detailed CV (LaTeX) |
| `cv.yml` → `profile:` | the name and affiliation used by both |

Everything else is layout you can leave alone: `preamble.tex` (LaTeX styling),
the CSS inside `build.py`, and the GitHub Actions workflow.

## Setting it up — once, in this order

1. **Create the repo** on GitHub named exactly `sanjarikalantri.github.io`,
   then `git remote add origin git@github.com:sanjarikalantri/sanjarikalantri.github.io.git`.
2. **Turn on Pages:** repo → Settings → Pages → **Source: GitHub Actions**.
3. **Add the phone number:** repo → Settings → Secrets and variables → Actions
   → New repository secret → name `RESUME_PHONE`, value the number.
   Skip this and the first build fails on purpose — see below.
4. **Add the photo:** put your picture at `assets/pic.jpg`, commit it.
5. `git push -u origin main`. The site is live at
   `https://sanjarikalantri.github.io` a minute or two later.

Steps 2 and 3 have to happen before the first push, or the Actions run goes
red. If it does, fix the setting and re-run it from the Actions tab — nothing
is broken.

## Editing

Open `cv.yml`, change the wording, commit, push. GitHub Actions rebuilds the
page and the PDF and publishes them, usually within a couple of minutes.

Write plain text — special characters (`%`, `&`, `_`, `#`, `~`) are escaped for
you. Three bits of formatting work anywhere in the file:

```
**bold**        *italic*        [link text](https://example.com)
```

Any entry can be parked with `enabled: false` instead of deleting it.

## Files (photo, papers)

Anything you want to link goes in `assets/`:

- `assets/pic.jpg` — the photo in the sidebar
- `assets/jmp.pdf`, and so on — papers linked from the Research section

The paths in `cv.yml` are relative to the repo root, so a paper dropped at
`assets/jmp.pdf` is linked as `url: assets/jmp.pdf`. The CV itself is always at
`cv.pdf`, since it is built rather than committed.

## Papers on the landing page

Every entry under Research and Work in Progress takes the same two blocks:

```yaml
- title: Information Provision with Intertemporal Externalities
  tag: Job Market Paper          # optional, shown in red after the title
  authors: with A and B          # optional, omit if sole-authored
  paper:
    enabled: true                # false hides the "Paper" link
    url: assets/jmp.pdf
  abstract:
    enabled: true                # false hides the abstract entirely
    url:                         # blank -> expand `text` on the page
    text: >-
      I analyse a dynamic model of persuasion in which...
```

`paper` is a link to the PDF. `abstract` is normally an accordion: the reader
clicks "Abstract" and `text` expands in place. Filling in `abstract: url:`
instead turns it into a plain link to that file and `text` is ignored — use
that only if you host the abstract separately.

Set `enabled: false` on `paper` while a draft is unfinished; the abstract can
stay up on its own. A block with `enabled: true` but nothing to show (no url,
no text) is skipped rather than rendering a dead control.

## The phone number

`cv.yml` is public, so the phone number is not written in it. Instead it says
`${RESUME_PHONE}`, and the real value comes from a GitHub secret:

> repo → Settings → Secrets and variables → Actions → New repository secret
> → name `RESUME_PHONE`, value the number.

The build fails loudly if the secret is missing, rather than shipping a PDF
with a literal `${RESUME_PHONE}` in it. To drop the phone number altogether, put
`enabled: false` on that entry under `cv: contact:`.

## Building locally (optional)

Not required — pushing is enough. But if you want to preview before you push:

```sh
pip install pyyaml
echo 'RESUME_PHONE: "(+44) 0000 000 000"' > secrets.local.yml   # gitignored
python3 build.py                # -> build/index.html, build/cv.tex
cd build && pdflatex cv.tex     # -> build/cv.pdf
```

Open `build/index.html` in a browser — `assets/` is mirrored into `build/`, so
the photo and papers load there exactly as they will on the live site.

You need a reasonably complete TeX Live for the PDF (`fontawesome5`, `paracol`,
`eso-pic`); CI already has it.

## If a build fails

repo → **Actions** tab → click the red run → read the failing step.

- `Unresolved placeholder(s): RESUME_PHONE` — the secret is not set; see step 3.
- A LaTeX error names the line in `build/cv.tex`. Almost always a stray
  character in `cv.yml`; the surrounding text will tell you which entry.
- `cv.yml` itself failing to parse — usually an indentation slip, or a value
  starting with `[`, `{`, `*`, `&` or containing `: ` that needs quoting.

The live site keeps serving the last good build until a run succeeds, so a
failure never takes the page down.
