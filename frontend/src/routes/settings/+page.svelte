<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiError, api, type UserSettings } from '$lib/api';

  let settings = $state<UserSettings | null>(null);
  let saving = $state(false);
  let saved = $state(false);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      settings = await api.get<UserSettings>('/api/v1/users/me/settings');
    } catch (e) {
      error = e instanceof ApiError ? `Failed to load (${e.status}).` : 'Network error.';
    }
  });

  async function save() {
    if (!settings) return;
    saving = true;
    saved = false;
    error = null;
    try {
      settings = await api.patch<UserSettings>('/api/v1/users/me/settings', {
        theme: settings.theme,
        enrichment_default_enabled: settings.enrichment_default_enabled
      });
      saved = true;
    } catch (e) {
      error = e instanceof ApiError ? `Save failed (${e.status}).` : 'Network error.';
    } finally {
      saving = false;
    }
  }
</script>

<div class="max-w-xl mx-auto px-6 py-10 space-y-8">
  <header>
    <h1 class="text-2xl font-semibold">Settings</h1>
    <p class="text-sm text-zinc-500 mt-1">
      Personal preferences. Library content settings live elsewhere.
    </p>
  </header>

  {#if error}
    <div class="text-sm text-red-400">{error}</div>
  {/if}

  {#if settings}
    <section class="space-y-3">
      <h2 class="text-sm font-medium text-zinc-300">Appearance</h2>
      <label class="block text-sm">
        <span class="text-zinc-400">Theme</span>
        <select
          bind:value={settings.theme}
          class="mt-1 w-48 px-3 py-2 rounded bg-zinc-950 border border-zinc-800"
        >
          <option value="system">Follow system</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
        <p class="mt-1 text-xs text-zinc-500">
          Page-level dark mode for sheet music arrives in a later release; this
          preference is stored now.
        </p>
      </label>
    </section>

    <section class="space-y-3">
      <h2 class="text-sm font-medium text-zinc-300">Enrichment</h2>
      <label class="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          bind:checked={settings.enrichment_default_enabled}
          class="mt-0.5"
        />
        <span>
          <span class="text-zinc-200">Enable MusicBrainz enrichment by default</span>
          <span class="block text-xs text-zinc-500">
            New uploads will look up composer + period information automatically.
          </span>
        </span>
      </label>
    </section>

    <button
      type="button"
      onclick={save}
      disabled={saving}
      class="px-4 py-2 rounded bg-zinc-100 text-zinc-950 font-medium disabled:opacity-50"
    >
      {saving ? 'Saving…' : 'Save'}
    </button>
    {#if saved}
      <span class="text-sm text-green-400 ml-3">Saved.</span>
    {/if}
  {:else if !error}
    <div class="text-sm text-zinc-500">Loading…</div>
  {/if}
</div>
