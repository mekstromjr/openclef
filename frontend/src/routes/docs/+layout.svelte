<script lang="ts">
  import { page } from '$app/state';
  import DocsSearch from '$lib/components/DocsSearch.svelte';
  import { docsNav } from '$lib/docs/nav';

  let { children } = $props();

  function isActive(href: string): boolean {
    return page.url.pathname === href;
  }
</script>

<div class="max-w-6xl mx-auto px-6 py-10 flex gap-10">
  <aside class="w-56 shrink-0 space-y-6">
    <DocsSearch />

    <nav class="space-y-5 text-sm">
      {#each docsNav as section (section.label)}
        <div>
          <div
            class="text-xs font-semibold uppercase tracking-wider text-clef-stone-300/70 mb-2"
          >
            {section.label}
          </div>
          <ul class="space-y-1">
            {#each section.links as link (link.href)}
              <li>
                <a
                  href={link.href}
                  class="block px-2 py-1 rounded {isActive(link.href)
                    ? 'bg-clef-graphite-700 text-clef-ivory'
                    : 'text-clef-stone-300 hover:text-clef-ivory hover:bg-clef-graphite-700/60'}"
                >
                  {link.label}
                </a>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </nav>
  </aside>

  <article
    class="flex-1 min-w-0 prose-docs space-y-4 text-clef-ivory"
  >
    {@render children()}
  </article>
</div>

<style>
  /*
   * Type styling for rendered markdown. mdsvex emits standard HTML
   * (h1-h6, p, ul, table, code) — we scope brand styles via a
   * `.prose-docs` ancestor class on the article. Headings carry the
   * serif voice (Crimson Pro); body/UI stays sans (Inter); code stays
   * mono (JetBrains Mono).
   */
  .prose-docs :global(h1) {
    font-family: var(--font-serif);
    font-weight: 600;
    font-size: 2.25rem;
    line-height: 1.2;
    margin: 0 0 1rem;
  }
  .prose-docs :global(h2) {
    font-family: var(--font-serif);
    font-weight: 600;
    font-size: 1.5rem;
    margin: 2rem 0 0.75rem;
  }
  .prose-docs :global(h3) {
    font-family: var(--font-serif);
    font-weight: 600;
    font-size: 1.2rem;
    margin: 1.5rem 0 0.5rem;
  }
  .prose-docs :global(p),
  .prose-docs :global(ul),
  .prose-docs :global(ol) {
    margin: 0.75rem 0;
    line-height: 1.65;
  }
  .prose-docs :global(ul),
  .prose-docs :global(ol) {
    padding-left: 1.5rem;
  }
  .prose-docs :global(ul) {
    list-style: disc;
  }
  .prose-docs :global(ol) {
    list-style: decimal;
  }
  .prose-docs :global(a) {
    color: var(--color-clef-claret);
    text-decoration: underline;
    text-underline-offset: 2px;
  }
  .prose-docs :global(code) {
    font-family: var(--font-mono);
    font-size: 0.875em;
    background: var(--color-clef-graphite-700);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }
  .prose-docs :global(pre) {
    background: var(--color-clef-graphite-700);
    border: 1px solid var(--color-clef-graphite-500);
    border-radius: 0.5rem;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
  }
  .prose-docs :global(pre code) {
    background: transparent;
    padding: 0;
  }
  .prose-docs :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.9rem;
  }
  .prose-docs :global(th),
  .prose-docs :global(td) {
    border: 1px solid var(--color-clef-graphite-500);
    padding: 0.5rem 0.75rem;
    text-align: left;
    vertical-align: top;
  }
  .prose-docs :global(th) {
    background: var(--color-clef-graphite-700);
    font-weight: 600;
  }
  .prose-docs :global(blockquote) {
    border-left: 3px solid var(--color-clef-claret);
    padding-left: 1rem;
    color: var(--color-clef-stone-300);
    margin: 1rem 0;
  }
  .prose-docs :global(hr) {
    border: 0;
    border-top: 1px solid var(--color-clef-graphite-500);
    margin: 2rem 0;
  }
</style>
