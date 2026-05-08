---
title: Color
description: OpenClef's color palette — tokens, semantics, accessibility, and Tier 2 dark mode.
---

The palette is high-contrast, accessible, and engineered for **Tier 2 Dark
Mode** inversion. Every token has a CSS variable name; the frontend should
consume these, not hex literals.

## Core tokens

| Name | Token | Hex | RGB | Role |
| :--- | :--- | :--- | :--- | :--- |
| **Charcoal** | `--clef-charcoal` | `#111111` | 17, 17, 17 | Dark-mode background; light-mode text. |
| **Ivory** | `--clef-ivory` | `#F6F4EF` | 246, 244, 239 | Light-mode background; dark-mode text; "paper" surface. |
| **Midnight** | `--clef-midnight` | `#0D1B2A` | 13, 27, 42 | Secondary accent, deep shadows, focus rings on Ivory. |
| **Claret** | `--clef-claret` | `#B8233A` | 184, 35, 58 | "Clef" wordmark, critical highlights, marking-pencil accents. |
| **Gold** | `--clef-gold` | `#D4AF37` | 212, 175, 55 | High-confidence match badges, performance-mode indicators. |

## Neutrals

| Name | Token | Hex | Role |
| :--- | :--- | :--- | :--- |
| **Stone 100** | `--clef-stone-100` | `#ECE9E1` | Card hover, subtle dividers on Ivory. |
| **Stone 300** | `--clef-stone-300` | `#C8C2B4` | Borders, disabled text on Ivory. |
| **Stone 600** | `--clef-stone-600` | `#6B6558` | Secondary body text on Ivory. |
| **Graphite 700** | `--clef-graphite-700` | `#2A2A2A` | Card surface in dark mode. |
| **Graphite 500** | `--clef-graphite-500` | `#4A4A4A` | Borders, dividers in dark mode. |

## Semantic tokens

| Token | Maps to | Use |
| :--- | :--- | :--- |
| `--color-bg` | Ivory / Charcoal (mode-dependent) | Page background. |
| `--color-surface` | Ivory / Graphite 700 | Cards, score paper. |
| `--color-text` | Charcoal / Ivory | Primary copy. |
| `--color-text-muted` | Stone 600 / Stone 300 | Captions, metadata. |
| `--color-accent` | Claret | Primary CTAs, brand highlights. |
| `--color-success` | Gold | Confidence badges, "matched." |
| `--color-focus` | Midnight / Gold | Keyboard focus rings. |

## Tier 2 dark mode

OpenClef's dark mode is a true semantic inversion, not just a recolor.

| Light token | inverts to | Dark token |
| :--- | :---: | :--- |
| `--color-bg` = Ivory | → | Charcoal |
| `--color-surface` = Ivory | → | Graphite 700 |
| `--color-text` = Charcoal | → | Ivory |
| `--color-accent` = Claret | → | Claret (unchanged) |
| `--color-success` = Gold | → | Gold (unchanged) |

Claret and Gold are preserved across modes — they're the brand's voice in any
room.

## Accessibility

All foreground/background pairings should clear **WCAG 2.2 AA (4.5:1 for body,
3:1 for large)**.

| Pairing | Ratio | Status |
| :--- | :---: | :--- |
| Charcoal on Ivory | 16.4 : 1 | AAA. |
| Ivory on Charcoal | 16.4 : 1 | AAA. |
| Claret on Ivory | 6.5 : 1 | AA body, AAA large. |
| Claret on Charcoal | 2.5 : 1 | **Fails AA** — never use Claret as text on Charcoal. Reserve for ≥ 18 px or non-text marks (badges, icons). |
| Gold on Charcoal | 8.9 : 1 | AAA. |
| Gold on Ivory | 1.8 : 1 | **Fails** — never use Gold as text on Ivory. Use as fill behind dark text only. |
