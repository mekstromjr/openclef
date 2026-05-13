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

## Two workflows

### Daily editing — `npm run dev`

Hot module reload, instant feedback. The right tool for writing content and
tweaking styles.

```sh
npm install
npm run dev       # http://localhost:4321
```

Other useful scripts:

```sh
npm run build     # static build to ./dist
npm run preview   # preview the static build via Astro (no container)
npm run check     # astro check — type errors, broken links
```

### Production-fidelity preview — Docker

Builds the same nginx image that prod will eventually run. Use this to
verify the built artifact behaves correctly before shipping.

```sh
# From the openclef repo root:
docker compose --profile preview up docs        # http://localhost:8080

# Or stand-alone:
docker build -t openclef-docs .
docker run --rm -p 8080:80 openclef-docs
```

The `preview` profile means `docker compose up` (no profile) keeps doing
what it did before — docs stays out of the default dev path.

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
