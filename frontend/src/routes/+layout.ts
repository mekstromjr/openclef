// adapter-static needs a fully prerenderable graph at the root. SPA
// fallback is configured in svelte.config.js — every client route
// resolves through index.html, so we mark the root layout prerender
// here and let SvelteKit emit a single shell.
export const prerender = true;
export const ssr = false;
