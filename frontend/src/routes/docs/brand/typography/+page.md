---
title: Typography
description: OpenClef's type system — Inter, Crimson Pro, JetBrains Mono.
---

# Typography

OpenClef uses two OFL-licensed typefaces so the entire stack is bundleable
in the repo with no licensing friction.

## Sans — Inter

Used for the **"Open"** wordmark, all UI, navigation, headings, and most
body text on screens.

- **Weights in active use:** 400 Regular, 500 Medium, 600 SemiBold, 700 Bold.
- **Wordmark weight:** Inter 600 SemiBold, tracking −2.
- **License:** SIL Open Font License 1.1 — bundle directly.
- **Web fallback stack:**

  ```css
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto,
    sans-serif;
  ```

## Serif — Crimson Pro

Used for the **"Clef"** wordmark, piece titles, composer names, and any
context where the brand should feel like a printed score (epigraphs,
marketing pull-quotes, archival metadata).

- **Weights in active use:** 400 Regular, 600 SemiBold, 600 Italic.
- **Wordmark weight:** Crimson Pro 600 Italic, optical-size tuned for display.
- **License:** SIL Open Font License 1.1 — bundle directly.
- **Web fallback stack:**

  ```css
  font-family: 'Crimson Pro', 'Iowan Old Style', 'Hoefler Text', Georgia,
    serif;
  ```

## Monospace — JetBrains Mono

For code blocks, file paths, and technical metadata.

- **License:** SIL Open Font License 1.1.
- **Fallback:**

  ```css
  font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
  ```

## Type scale

A 1.250 (major-third) modular scale, anchored at 16 px / 1 rem body.

| Token | Use | Size | Weight | Family |
| :--- | :--- | :---: | :---: | :--- |
| `--text-display` | Hero, marketing | 48 px / 3.000 rem | 600 | Crimson Pro |
| `--text-h1` | Page title | 36 px / 2.250 rem | 600 | Crimson Pro |
| `--text-h2` | Section title | 28 px / 1.750 rem | 600 | Inter |
| `--text-h3` | Subsection | 22 px / 1.375 rem | 600 | Inter |
| `--text-body-lg` | Lead paragraph | 18 px / 1.125 rem | 400 | Inter |
| `--text-body` | Default | 16 px / 1.000 rem | 400 | Inter |
| `--text-caption` | Metadata, badges | 13 px / 0.8125 rem | 500 | Inter |
| `--text-mono` | Code, paths | 14 px / 0.875 rem | 400 | JetBrains Mono |

Piece titles and composer names override the body family with Crimson Pro
600 — even at body size — to keep the score-paper feel inside the library
views.
