import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
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
      '$components': 'src/lib/components',
      '$ui': 'src/lib/components/ui'
    }
  }
};

export default config;
