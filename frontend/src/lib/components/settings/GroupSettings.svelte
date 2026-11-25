<script lang="ts">
  // Groups (openclef#63): a set of people you share chosen pieces with.
  // The creator owns the group and manages its members; anyone else in it
  // can leave. Pieces are shared into a group from the piece's page.
  import { onMount } from 'svelte';
  import { ApiError, api, type Group, type Person } from '$lib/api';
  import { authState } from '$lib/stores/auth.svelte';

  let groups = $state<Group[] | null>(null);
  let people = $state<Person[]>([]);
  let newName = $state('');
  // Per group: the person picked to add, and the name being edited.
  let picks = $state<Record<string, string>>({});
  let renaming = $state<Record<string, string>>({});
  let busy = $state(false);
  let error = $state<string | null>(null);

  const me = $derived(authState.user?.id ?? null);

  onMount(load);

  async function load() {
    try {
      [groups, people] = await Promise.all([
        api.get<Group[]>('/api/v1/groups'),
        api.get<Person[]>('/api/v1/people')
      ]);
    } catch {
      error = "Couldn't load groups.";
    }
  }

  const MESSAGES: Record<string, string> = {
    already_member: "They're already in the group.",
    group_not_found: 'That group no longer exists.',
    user_not_found: 'That person no longer exists.'
  };

  async function run(action: () => Promise<unknown>, failed: string) {
    busy = true;
    error = null;
    try {
      await action();
      groups = await api.get<Group[]>('/api/v1/groups');
    } catch (e) {
      error = (e instanceof ApiError && typeof e.detail === 'string' && MESSAGES[e.detail]) || failed;
    } finally {
      busy = false;
    }
  }

  function addable(group: Group): Person[] {
    return people.filter((person) => !group.members.some((m) => m.id === person.id));
  }

  function create() {
    const name = newName.trim();
    if (!name) return;
    newName = '';
    return run(() => api.post('/api/v1/groups', { name }), 'Creating the group failed.');
  }

  function rename(group: Group) {
    const name = (renaming[group.id] ?? '').trim();
    delete renaming[group.id];
    if (!name || name === group.name) return;
    return run(() => api.patch(`/api/v1/groups/${group.id}`, { name }), 'Renaming failed.');
  }

  function addMember(group: Group) {
    const id = picks[group.id];
    if (!id) return;
    picks[group.id] = '';
    return run(() => api.post(`/api/v1/groups/${group.id}/members`, { user_id: id }), 'Adding failed.');
  }

  function removeMember(group: Group, person: Person) {
    if (!confirm(`Remove ${person.username} from ${group.name}? Music shared with the group disappears for them, and the pieces they shared leave the group.`)) return;
    return run(() => api.delete(`/api/v1/groups/${group.id}/members/${person.id}`), 'Removing failed.');
  }

  function leave(group: Group) {
    if (!me || !confirm(`Leave ${group.name}? You'll stop seeing its music, and pieces you shared with it leave the group.`)) return;
    return run(() => api.delete(`/api/v1/groups/${group.id}/members/${me}`), 'Leaving failed.');
  }

  function remove(group: Group) {
    if (!confirm(`Delete ${group.name}? Its members lose what was shared through it. The music itself stays with its owners.`)) return;
    return run(() => api.delete(`/api/v1/groups/${group.id}`), 'Deleting failed.');
  }
</script>

<section class="space-y-5 border-t border-clef-graphite-500 pt-6" aria-labelledby="groups-heading">
  <div>
    <h2 id="groups-heading" class="text-sm font-medium text-clef-ivory">Groups</h2>
    <p class="text-xs text-clef-stone-300/70 mt-1">
      A group is a set of people, like a choir or a band. Share chosen pieces with it from a piece's
      page; members see only those, not the rest of your library.
    </p>
  </div>

  {#if groups}
    {#if groups.length}
      <ul class="space-y-4">
        {#each groups as group (group.id)}
          {@const owner = group.owner.id === me}
          <li class="space-y-2 rounded border border-clef-graphite-500 p-3" data-testid="group">
            <div class="flex flex-wrap items-center justify-between gap-2">
              {#if group.id in renaming}
                <form class="flex items-center gap-2" onsubmit={(e) => { e.preventDefault(); rename(group); }}>
                  <input
                    bind:value={renaming[group.id]}
                    maxlength="100"
                    aria-label="Group name"
                    class="w-48 px-2 py-1 rounded bg-clef-charcoal border border-clef-graphite-500 text-sm focus:border-clef-claret focus:outline-none"
                  />
                  <button type="submit" disabled={busy} class="px-2 py-1 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret">Save</button>
                  <button type="button" onclick={() => delete renaming[group.id]} class="px-2 py-1 text-sm text-clef-stone-300">Cancel</button>
                </form>
              {:else}
                <a href="/?group={group.id}" class="text-sm font-medium hover:text-clef-claret">{group.name}</a>
              {/if}
              <div class="flex items-center gap-1 text-sm">
                {#if owner}
                  {#if !(group.id in renaming)}
                    <button type="button" disabled={busy} onclick={() => (renaming[group.id] = group.name)} class="px-2 py-1 rounded text-clef-stone-300 hover:text-clef-ivory disabled:opacity-50">Rename</button>
                  {/if}
                  <button type="button" disabled={busy} onclick={() => remove(group)} class="px-2 py-1 rounded text-clef-stone-300 hover:text-clef-claret disabled:opacity-50">Delete group</button>
                {:else}
                  <span class="text-xs text-clef-stone-300/70">Run by {group.owner.username}</span>
                  <button type="button" disabled={busy} onclick={() => leave(group)} class="px-2 py-1 rounded text-clef-stone-300 hover:text-clef-claret disabled:opacity-50">Leave</button>
                {/if}
              </div>
            </div>
            <ul class="space-y-1">
              {#each group.members as person (person.id)}
                <li class="flex items-center justify-between gap-3 text-sm">
                  {#if person.id === me}
                    <span>{person.username} <span class="text-clef-stone-300/70">(you)</span></span>
                  {:else}
                    <a href="/?shared_by={person.id}" class="hover:text-clef-claret" title="Music {person.username} shares with you">{person.username}</a>
                  {/if}
                  {#if owner && person.id !== me}
                    <button type="button" disabled={busy} onclick={() => removeMember(group, person)} class="px-2 py-1 rounded text-clef-stone-300 hover:text-clef-claret disabled:opacity-50">Remove</button>
                  {/if}
                </li>
              {/each}
            </ul>
            {#if owner && addable(group).length}
              <div class="flex items-center gap-2 pt-1">
                <select
                  bind:value={picks[group.id]}
                  aria-label="Person to add to {group.name}"
                  class="w-48 px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 text-sm focus:border-clef-claret focus:outline-none"
                >
                  <option value="">Add a person…</option>
                  {#each addable(group) as person (person.id)}
                    <option value={person.id}>{person.username}</option>
                  {/each}
                </select>
                <button type="button" disabled={busy || !picks[group.id]} onclick={() => addMember(group)} class="px-3 py-2 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret disabled:opacity-50">
                  Add
                </button>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="text-sm text-clef-stone-300/70">You're not in any groups.</p>
    {/if}
    <form class="flex items-center gap-2" onsubmit={(e) => { e.preventDefault(); create(); }}>
      <input
        bind:value={newName}
        maxlength="100"
        placeholder="New group name"
        aria-label="New group name"
        class="w-48 px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 text-sm focus:border-clef-claret focus:outline-none"
      />
      <button type="submit" disabled={busy || !newName.trim()} class="px-3 py-2 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret disabled:opacity-50">
        Create group
      </button>
    </form>
  {:else if !error}
    <p class="text-sm text-clef-stone-300/70">Loading…</p>
  {/if}
  {#if error}<p class="text-sm text-clef-claret">{error}</p>{/if}
</section>
