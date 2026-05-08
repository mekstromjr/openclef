# Dependency Management — openclef/docs

**Status:** Accepted · **Date:** 2026-05-08 · **Scope:** `docs/` subdirectory only

## Decision

Use **self-hosted Renovate** for automated dependency PRs against the `docs/` subdirectory, with **Astro and Starlight gated behind human review** and lower-risk packages (fontsource, sharp) grouped into a single weekly PR. Renovate config lives at the repo root in [`renovate.json`](../renovate.json), scoped via `matchFileNames: ["docs/**"]`.

The rest of the repo (`backend/`, `frontend/`) is explicitly disabled in Renovate until those areas declare their own bump strategy — keeping this rollout narrow.

## Why Not Manual

A scheduled "run `npm outdated` every N weeks" ticket was the alternative. It's cheaper to set up but has two failure modes:

1. **Forgetting.** A recurring ticket only works if it's actually picked up. The cost of a missed cycle is silent drift — the exact thing version pinning is supposed to make visible.
2. **Doesn't scale past `docs/`.** Once `frontend/` and `backend/` adopt a similar policy, manual cadence becomes a chore. Renovate's marginal cost per added directory is near zero.

## Why Not Full Auto-Merge

There is **no docs CI build yet** (Phase 5 of [ticket 0146](../../meklab/vault/Tickets/Active/0146-openclef-docs-subsite.md)). Without a build step verifying the site still renders, "Renovate says green" only means `npm install` succeeded — which catches peer-dep breaks but not Astro/Starlight regressions.

Until docs CI lands, **all merges are manual**. Once CI exists, the fontsource + sharp group is a candidate for `automerge: true` on minor/patch.

## Why Pin Exact Versions

Reaffirming the meklab-wide principle: pinned versions make upgrades **deliberate**. The combination of pinning + Renovate is complementary, not contradictory:

- Pinning controls **when** an upgrade happens (only when a Renovate PR is merged).
- Renovate controls **whether you remember to look** (a PR shows up every Monday).

The PR is the moment of deliberation. `rangeStrategy: pin` in `renovate.json` enforces this — Renovate will rewrite ranges (`^x.y.z`) back to exact pins if any sneak in.

## Risk Tiers (encoded in `renovate.json`)

| Tier | Packages | Behavior |
|---|---|---|
| Load-bearing | `astro`, `@astrojs/**` | Separate PRs, `needs-human` label, never auto-merged |
| Boring | `@fontsource/**`, `sharp` | Grouped into one weekly PR |
| Major bumps (any package) | — | Always separate, `needs-human` + `major-update` labels |

`@astrojs/starlight` matches `@astrojs/**` and inherits the load-bearing rule. This is intentional — Starlight is pre-1.0, and minor bumps have shipped layout-breaking changes.

## Operational Notes

- **Schedule:** Monday early morning, batched. Avoids midweek context-switches.
- **Concurrency:** 5 open PRs max. Prevents PR backlog if a long absence happens.
- **Lockfile maintenance:** weekly transitive updates, also Mondays.
- **Self-hosted Renovate runner:** not yet deployed. This config will sit dormant until the runner lands — it is forward-looking, not blocking. Tracked separately as a follow-up.

## Revisit When

- Docs CI build lands (ticket 0146 Phase 5) → enable `automerge` on the boring group.
- `frontend/` or `backend/` adopt a strategy → drop the `!docs/**` exclusion rule.
- Astro reaches a version where Starlight is 1.0+ → reconsider whether Starlight still needs `needs-human` gating.

## See Also

- `renovate.json` at the repo root — the runtime config this ADR explains.
- Meklab CLAUDE.md "Pin all image versions" principle — the same logic applied at the container layer.
