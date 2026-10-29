<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import '../app.css';
  import AccountDropdown from '$lib/components/AccountDropdown.svelte';
  import OpenClefWordmark from '$lib/components/OpenClefWordmark.svelte';
  import { authState, bootstrap } from '$lib/stores/auth.svelte';

  let { children } = $props();

  // Routes that don't require authentication. Anything else 401-redirects.
  // Docs are public so a user can read help and the brand guide without
  // signing in (ticket 0153).
  const PUBLIC_PREFIXES = ['/login', '/setup', '/docs'];

  function isPublic(path: string): boolean {
    return PUBLIC_PREFIXES.some((p) => path === p || path.startsWith(p + '/'));
  }

  onMount(async () => {
    await bootstrap();
    enforceGuard();
  });

  // Re-evaluate the guard whenever the route changes (after navigation
  // from a public to a protected route, or vice versa).
  $effect(() => {
    void page.url;
    if (!authState.loading) enforceGuard();
  });

  function enforceGuard() {
    const path = page.url.pathname;
    if (authState.setupComplete === false) {
      if (path !== '/setup') goto('/setup');
      return;
    }
    if (!authState.user && !isPublic(path)) {
      goto('/login');
      return;
    }
    // Authed user shouldn't see /login or /setup
    if (authState.user && (path === '/login' || path === '/setup')) {
      goto('/');
    }
  }
</script>

<div class="min-h-screen flex flex-col">
  <header
    class="h-14 flex items-center justify-between px-6 border-b border-clef-graphite-500"
  >
    <a href="/" class="text-lg" aria-label="OpenClef home">
      <OpenClefWordmark />
    </a>
    <AccountDropdown />
  </header>

  <main class="flex-1">
    {#if authState.loading}
      <div
        class="min-h-[60vh] flex items-center justify-center text-clef-stone-300/70 text-sm"
      >
        Loading…
      </div>
    {:else}
      {@render children()}
    {/if}
  </main>
</div>
