<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiError, api, startSso, type OidcConfig, type UserSettings } from '$lib/api';
  import GroupSettings from '$lib/components/settings/GroupSettings.svelte';
  import SharingSettings from '$lib/components/settings/SharingSettings.svelte';
  import { authState, bootstrap } from '$lib/stores/auth.svelte';

  let sso = $state<OidcConfig | null>(null);
  let ssoError = $state<string | null>(null);

  async function unlinkSso() {
    if (!confirm('Unlink single sign-on? You will sign in with your password only.')) return;
    ssoError = null;
    try {
      await api.delete('/api/v1/auth/oidc/link');
      await bootstrap();
    } catch (e) {
      ssoError = e instanceof ApiError && e.status === 409
        ? 'This account has no password, so single sign-on is its only way in.'
        : 'Unlinking failed.';
    }
  }

  let settings = $state<UserSettings | null>(null);
  let saving = $state(false);
  let saved = $state(false);
  let error = $state<string | null>(null);

  onMount(async () => {
    api.get<OidcConfig>('/api/v1/auth/oidc/config').then((c) => (sso = c), () => (sso = null));
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
    <h1 class="text-2xl font-serif font-semibold">Settings</h1>
    <p class="text-sm text-clef-stone-300/70 mt-1">
      Personal preferences and who you share your library with.
    </p>
  </header>

  {#if error}
    <div class="text-sm text-clef-claret">{error}</div>
  {/if}

  {#if settings}
    <section class="space-y-3">
      <h2 class="text-sm font-medium text-clef-ivory">Appearance</h2>
      <label class="block text-sm">
        <span class="text-clef-stone-300">Theme</span>
        <select
          bind:value={settings.theme}
          class="mt-1 w-48 px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 focus:border-clef-claret focus:outline-none"
        >
          <option value="system">Follow system</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
        <p class="mt-1 text-xs text-clef-stone-300/70">
          Page-level dark mode for sheet music arrives in a later release; this
          preference is stored now.
        </p>
      </label>
    </section>

    <section class="space-y-3">
      <h2 class="text-sm font-medium text-clef-ivory">Enrichment</h2>
      <label class="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          bind:checked={settings.enrichment_default_enabled}
          class="mt-0.5 accent-clef-claret"
        />
        <span>
          <span class="text-clef-ivory"
            >Enable MusicBrainz enrichment by default</span
          >
          <span class="block text-xs text-clef-stone-300/70">
            New uploads will look up composer + period information automatically.
          </span>
        </span>
      </label>
    </section>

    <button
      type="button"
      onclick={save}
      disabled={saving}
      class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50"
    >
      {saving ? 'Saving…' : 'Save'}
    </button>
    {#if saved}
      <span class="text-sm text-clef-gold ml-3">Saved.</span>
    {/if}
  {:else if !error}
    <div class="text-sm text-clef-stone-300/70">Loading…</div>
  {/if}

  <SharingSettings />
  <GroupSettings />

  {#if sso?.enabled && authState.user}
    <section class="space-y-3 border-t border-clef-graphite-500 pt-6">
      <h2 class="text-sm font-medium text-clef-ivory">Single sign-on</h2>
      {#if authState.user.sso_linked}
        <p class="text-sm text-clef-stone-300">
          Linked to {sso.provider_name}. You can sign in with it instead of your password.
        </p>
        {#if authState.user.has_password}
          <button type="button" onclick={unlinkSso} class="px-3 py-1.5 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret">
            Unlink
          </button>
        {/if}
      {:else}
        <p class="text-sm text-clef-stone-300">
          Link your {sso.provider_name} account to sign in without a separate OpenClef password.
        </p>
        <button type="button" onclick={() => startSso('/settings', true)} class="px-3 py-1.5 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret">
          Link {sso.provider_name}
        </button>
      {/if}
      {#if ssoError}<p class="text-sm text-clef-claret">{ssoError}</p>{/if}
    </section>
  {/if}
</div>
