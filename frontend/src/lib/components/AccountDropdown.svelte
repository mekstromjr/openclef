<script lang="ts">
  import { goto } from '$app/navigation';
  import { authState, logout } from '$lib/stores/auth.svelte';

  let open = $state(false);

  async function doLogout() {
    open = false;
    await logout();
    await goto('/login');
  }

  function close() {
    open = false;
  }
</script>

<svelte:window onclick={close} />

{#if authState.user}
  <div class="relative">
    <button
      type="button"
      class="px-3 py-1.5 rounded text-sm font-medium text-zinc-200 hover:bg-zinc-800 transition"
      onclick={(e) => {
        e.stopPropagation();
        open = !open;
      }}
    >
      {authState.user.username}
      {#if authState.user.role === 'admin'}
        <span class="ml-1 text-xs text-zinc-500">· admin</span>
      {/if}
    </button>

    {#if open}
      <div
        class="absolute right-0 mt-1 w-44 rounded-md bg-zinc-900 border border-zinc-800 shadow-lg z-50"
        onclick={(e) => e.stopPropagation()}
        role="menu"
        tabindex="-1"
      >
        <a
          href="/settings"
          onclick={close}
          class="block px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
        >Settings</a>
        <button
          type="button"
          onclick={doLogout}
          class="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
        >Log out</button>
      </div>
    {/if}
  </div>
{/if}
