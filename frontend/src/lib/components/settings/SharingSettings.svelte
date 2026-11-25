<script lang="ts">
  // Partners (openclef#62): share your whole library with someone, one way.
  // They see your music; you see none of theirs unless they share back.
  import { onMount } from 'svelte';
  import { ApiError, api, type IncomingPartner, type Partners, type Person } from '$lib/api';

  let partners = $state<Partners | null>(null);
  let people = $state<Person[]>([]);
  let choice = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  const available = $derived(
    people.filter((person) => !partners?.outgoing.some((p) => p.id === person.id))
  );

  onMount(load);

  async function load() {
    try {
      [partners, people] = await Promise.all([
        api.get<Partners>('/api/v1/partners'),
        api.get<Person[]>('/api/v1/people')
      ]);
    } catch {
      error = "Couldn't load sharing.";
    }
  }

  async function run(action: () => Promise<unknown>, failed: string) {
    busy = true;
    error = null;
    try {
      await action();
      partners = await api.get<Partners>('/api/v1/partners');
    } catch (e) {
      error = e instanceof ApiError && e.detail === 'already_partners'
        ? 'You already share your library with them.'
        : failed;
    } finally {
      busy = false;
    }
  }

  function share() {
    const id = choice;
    if (!id) return;
    choice = '';
    return run(() => api.post('/api/v1/partners', { user_id: id }), 'Sharing failed.');
  }

  function stopSharing(person: Person) {
    if (!confirm(`Stop sharing your library with ${person.username}? Your music will disappear from their library and setlists.`)) return;
    return run(() => api.delete(`/api/v1/partners/${person.id}`), 'Stopping failed.');
  }

  function setShown(partner: IncomingPartner, shown: boolean) {
    return run(
      () => api.patch(`/api/v1/partners/incoming/${partner.id}`, { show_in_library: shown }),
      'Saving failed.'
    );
  }
</script>

<section class="space-y-5 border-t border-clef-graphite-500 pt-6" aria-labelledby="sharing-heading">
  <div>
    <h2 id="sharing-heading" class="text-sm font-medium text-clef-ivory">Sharing</h2>
    <p class="text-xs text-clef-stone-300/70 mt-1">
      Sharing your library lets someone see and edit all your music. It's one way: you
      don't see theirs unless they share with you, and they can't pass yours on.
    </p>
  </div>

  {#if partners}
    <div class="space-y-2">
      <h3 class="text-sm text-clef-stone-300">I share my library with</h3>
      {#if partners.outgoing.length}
        <ul class="space-y-1">
          {#each partners.outgoing as person (person.id)}
            <li class="flex items-center justify-between gap-3 text-sm">
              <span>{person.username}</span>
              <button type="button" disabled={busy} onclick={() => stopSharing(person)} class="px-2 py-1 rounded text-clef-stone-300 hover:text-clef-claret disabled:opacity-50">
                Stop sharing
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-sm text-clef-stone-300/70">Nobody yet. Your music is private.</p>
      {/if}
      {#if available.length}
        <div class="flex items-center gap-2 pt-1">
          <select
            bind:value={choice}
            aria-label="Person to share your library with"
            class="w-48 px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 text-sm focus:border-clef-claret focus:outline-none"
          >
            <option value="">Choose a person…</option>
            {#each available as person (person.id)}
              <option value={person.id}>{person.username}</option>
            {/each}
          </select>
          <button type="button" disabled={busy || !choice} onclick={share} class="px-3 py-2 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret disabled:opacity-50">
            Share
          </button>
        </div>
      {/if}
    </div>

    <div class="space-y-2">
      <h3 class="text-sm text-clef-stone-300">Shared with me</h3>
      {#if partners.incoming.length}
        <ul class="space-y-2">
          {#each partners.incoming as partner (partner.id)}
            <li class="flex flex-wrap items-center justify-between gap-3 text-sm">
              <a href="/?shared_by={partner.id}" class="hover:text-clef-claret">{partner.username}'s music</a>
              <label class="flex items-center gap-2 text-clef-stone-300">
                <input
                  type="checkbox"
                  checked={partner.show_in_library}
                  disabled={busy}
                  onchange={(e) => setShown(partner, e.currentTarget.checked)}
                  class="accent-clef-claret"
                />
                Show in my library
              </label>
            </li>
          {/each}
        </ul>
        <p class="text-xs text-clef-stone-300/70">
          Turning "Show in my library" off only hides their music from your main library. It stays
          on their page and in your setlists.
        </p>
      {:else}
        <p class="text-sm text-clef-stone-300/70">Nobody shares their library with you yet.</p>
      {/if}
    </div>
  {:else if !error}
    <p class="text-sm text-clef-stone-300/70">Loading…</p>
  {/if}
  {#if error}<p class="text-sm text-clef-claret">{error}</p>{/if}
</section>
