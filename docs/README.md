# OpenClef Docs

Documentation subsite for OpenClef, built with [Astro Starlight](https://starlight.astro.build).

The eventual public URL is `openclef.meklab.net` (then `openclef.org`).

## Requirements

- Node **22.12+** (pinned via `.nvmrc` to `22`).
- npm 10+.

If you use [nvm](https://github.com/nvm-sh/nvm):

```sh
nvm use     # reads .nvmrc
```

## Local development

```sh
npm install
npm run dev       # starts dev server at http://localhost:4321
npm run build     # static build to ./dist
npm run preview   # preview the production build
```

## Project layout

```
docs/
├── astro.config.mjs           # Site config + sidebar IA
├── src/
│   ├── styles/brand.css       # Brand color + font tokens
│   ├── assets/branding/       # Brand asset files (concept refs for now)
│   └── content/docs/
│       ├── index.mdx          # Landing
│       ├── brand/             # Brand style guide (canonical)
│       ├── guides/            # User-facing guides
│       └── reference/         # API + config reference
└── public/                    # Static files served as-is
```

## Editing in Obsidian

For editing convenience, the `src/content/docs/` directory is symlinked into
the MekVault at `Efforts/Hobbies/Meklab/openclef/docs/`. Edits in either
place persist — they are the same files.

## Brand source of truth

The `brand/` section is the canonical OpenClef brand style guide. Update it
here, not in copies elsewhere.
