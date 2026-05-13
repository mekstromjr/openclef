import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { mdsvex } from 'mdsvex';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  // .md files are treated as SvelteKit modules so docs pages can live as
  // `src/routes/docs/**/+page.md`. mdsvex compiles them to Svelte
  // components at build time; frontmatter is exposed via the component's
  // metadata for the search index (ticket 0153).
  extensions: ['.svelte', '.md'],
  preprocess: [
    vitePreprocess(),
    mdsvex({
      extensions: ['.md']
    })
  ],
  kit: {
    // Adapter-static with SPA fallback. Acceptance criterion #1 of ticket
    // 0134 requires that deep-linking to /some/spa/route returns the SPA
    // shell rather than a 404. The Python backend serves index.html as
    // its catch-all; this fallback ensures the build emits one.
    adapter: adapter({
      fallback: 'index.html',
      strict: false
    }),
    alias: {
      // Reserved for shadcn-svelte components when the first feature
      // ticket needs them. No components live here yet.
      $components: 'src/lib/components',
      $ui: 'src/lib/components/ui'
    }
  }
};

export default config;
