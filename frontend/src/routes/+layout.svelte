<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import '../app.css';
  import AccountDropdown from '$lib/components/AccountDropdown.svelte';
  import { authState, bootstrap } from '$lib/stores/auth.svelte';

  let { children } = $props();

  // Routes that don't require authentication. Anything else 401-redirects.
  const PUBLIC_ROUTES = new Set(['/login', '/setup']);

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
    if (!authState.user && !PUBLIC_ROUTES.has(path)) {
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
  <header class="flex items-center justify-between px-6 py-3 border-b border-zinc-800">
    <a href="/" class="text-lg font-semibold tracking-tight">OpenClef</a>
    <AccountDropdown />
  </header>

  <main class="flex-1">
    {#if authState.loading}
      <div class="min-h-[60vh] flex items-center justify-center text-zinc-500 text-sm">
        Loading…
      </div>
    {:else}
      {@render children()}
    {/if}
  </main>
</div>
