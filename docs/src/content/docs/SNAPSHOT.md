---
title: Snapshot notice
description: The canonical OpenClef docs now live inside the app at openclef/frontend/src/routes/docs/.
sidebar:
  hidden: true
---

# Snapshot notice

> **As of 2026-05-12 (ticket 0153), this content is a snapshot.**

The canonical OpenClef documentation now lives **inside the running app**,
at `openclef/frontend/src/routes/docs/`. The Obsidian vault symlink has
been re-pointed at the in-app version. Edits here will not be picked up
by the running OpenClef instance.

This standalone Astro Starlight site is preserved as groundwork for the
eventual public-facing OpenClef site. When that becomes a priority, we'll
decide between:

1. **Shared content directory** — both Starlight and the SvelteKit
   frontend read from a single source.
2. **Starlight pulls from the frontend** — Astro reads markdown files
   from the SvelteKit route tree at build time.
3. **Dual maintenance with tooling** — a sync script keeps both in step.

Until then: edit content in
`openclef/frontend/src/routes/docs/**/+page.md`. This site's `brand/`,
`guides/`, and `reference/` pages will drift; the Starlight build will
keep working, but it's a snapshot of the 2026-05-08 state.
