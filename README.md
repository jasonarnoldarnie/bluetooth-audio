# bluetooth-audio
Hardware and firmware for bluetooth audio adaptor

## Repo setup

Hooks live in `.githooks/` (version controlled), so each clone needs one command to enable them:

```bash
git config core.hooksPath .githooks
```

The `pre-commit` hook re-stamps the "Updated" date in [`docs/design-overview.md`](docs/design-overview.md)
and renders [`docs/design-overview.pdf`](docs/design-overview.pdf) into the same commit. It runs only
when that document is staged, never blocks a commit, and needs Python plus Chrome/Edge (or pandoc).

- `git config hooks.designpdf false` — disable without deleting the hook
- `git config hooks.designpdf.snapshot true` — also keep a dated copy under `docs/snapshots/`
