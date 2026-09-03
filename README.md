# bluetooth-audio
Hardware and firmware for bluetooth audio adaptor

## Repo setup

Hooks live in `.githooks/` (version controlled), so each clone needs one command to enable them:

```bash
git config core.hooksPath .githooks
```

The `pre-commit` hook re-stamps the "Updated" date in [`docs/design-overview.tex`](docs/design-overview.tex)
and renders [`docs/design-overview.pdf`](docs/design-overview.pdf) into the same commit. It runs only
when that document is staged, never blocks a commit, and needs [Tectonic](https://tectonic-typesetting.github.io/)
(XeTeX) on `PATH` or in `%LOCALAPPDATA%\Programs\Tectonic` (Python is used only for the date stamp).
The diagrams render in the Consolas monospace font (a Windows system font); on other platforms swap it
for another mono font with box-drawing glyphs in the document preamble.

- `git config hooks.designpdf false` — disable without deleting the hook
- `git config hooks.designpdf.snapshot true` — also keep a dated copy under `docs/snapshots/`
