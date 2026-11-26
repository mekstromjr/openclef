<script lang="ts">
  // Share a setlist with people or with groups you're in, to view it or
  // also add their own pieces (openclef#64). Shown to the owner only; the
  // server refuses anyone else, admins included.
  //
  // Before a share is made, a dry run lists the pieces its audience won't
  // get (ones someone else owns), so the owner confirms knowingly. With
  // nothing held back it shares straight away.
  import { onMount } from 'svelte';
  import {
    ApiError,
    api,
    type Group,
    type Person,
    type SetlistShare,
    type SetlistShareCheck,
    type SharePermission
  } from '$lib/api';

  let { setlistId, onChanged }: { setlistId: string; onChanged: () => void } = $props();

  let shares = $state<SetlistShare[]>([]);
  let people = $state<Person[]>([]);
  let groups = $state<Group[]>([]);
  // "user:<id>" or "group:<id>"
  let target = $state('');
  let permission = $state<SharePermission>('view');
  let busy = $state(false);
  let error = $state<string | null>(null);

  const base = $derived(`/api/v1/setlists/${setlistId}/shares`);
  const sharedUsers = $derived(new Set(shares.flatMap((s) => (s.user ? [s.user.id] : []))));
  const sharedGroups = $derived(new Set(shares.flatMap((s) => (s.group ? [s.group.id] : []))));

  onMount(async () => {
    try {
      [shares, people, groups] = await Promise.all([
        api.get<SetlistShare[]>(base),
        api.get<Person[]>('/api/v1/people'),
        api.get<Group[]>('/api/v1/groups')
      ]);
    } catch {
      error = "Couldn't load who this setlist is shared with.";
    }
  });

  const MESSAGES: Record<string, string> = {
    already_shared: "It's already shared with them.",
    group_not_found: "You're no longer in that group.",
    user_not_found: 'That person no longer exists.'
  };

  async function run(action: () => Promise<SetlistShare[] | void>, failed: string) {
    busy = true;
    error = null;
    try {
      const updated = await action();
      shares = updated ?? (await api.get<SetlistShare[]>(base));
      onChanged();
    } catch (e) {
      error = (e instanceof ApiError && typeof e.detail === 'string' && MESSAGES[e.detail]) || failed;
    } finally {
      busy = false;
    }
  }

  function heldBackQuestion(check: SetlistShareCheck): string | null {
    const named = check.held_back.map((piece) => `- ${piece.title}`);
    const hidden = check.hidden_count;
    if (!named.length && !hidden) return null;
    const lines = [...named];
    if (hidden) lines.push(`- ${hidden} ${hidden === 1 ? "piece that isn't" : "pieces that aren't"} shared with you`);
    return (
      "These pieces won't be shared, because you don't own them. Whoever you share with sees them as " +
      `"not shared with you":\n\n${lines.join('\n')}\n\nShare anyway?`
    );
  }

  function share(event: SubmitEvent) {
    event.preventDefault();
    if (!target) return;
    const [kind, id] = target.split(':');
    const body = { [kind === 'user' ? 'user_id' : 'group_id']: id, permission };
    return run(async () => {
      const check = await api.post<SetlistShareCheck>(`${base}?dry_run=true`, body);
      const question = heldBackQuestion(check);
      if (question && !confirm(question)) return shares;
      const updated = await api.post<SetlistShare[]>(base, body);
      target = '';
      return updated;
    }, 'Sharing failed.');
  }

  function change(share: SetlistShare, next: SharePermission) {
    return run(() => api.patch<SetlistShare[]>(`${base}/${share.id}`, { permission: next }), 'Saving failed.');
  }

  function stop(share: SetlistShare) {
    const who = share.user?.username ?? share.group?.name ?? '';
    if (!confirm(`Stop sharing with ${who}? They lose the setlist, and pieces they added stop reaching anyone else.`)) return;
    return run(async () => {
      await api.delete(`${base}/${share.id}`);
    }, 'Removing failed.');
  }
</script>

<section class="space-y-3 rounded-lg border border-clef-graphite-500 p-4 text-sm" aria-labelledby="setlist-sharing" data-testid="setlist-sharing">
  <div>
    <h2 id="setlist-sharing" class="font-medium text-clef-ivory">Sharing</h2>
    <p class="mt-1 text-xs text-clef-stone-300/70">
      People you share with see this setlist and the pieces on it that you own. With <em>Can add</em> they can also
      add their own pieces and reorder it.
    </p>
  </div>

  {#if shares.length}
    <ul class="space-y-1">
      {#each shares as entry (entry.id)}
        <li class="flex flex-wrap items-center justify-between gap-2">
          <span>{entry.user ? entry.user.username : `${entry.group?.name} (group)`}</span>
          <span class="flex items-center gap-1">
            <select
              value={entry.permission}
              disabled={busy}
              aria-label="What {entry.user?.username ?? entry.group?.name} can do"
              onchange={(e) => change(entry, e.currentTarget.value as SharePermission)}
              class="rounded border border-clef-graphite-500 bg-clef-graphite-700 px-1 py-0.5 text-xs"
            >
              <option value="view">Can view</option>
              <option value="contribute">Can add</option>
            </select>
            <button type="button" disabled={busy} onclick={() => stop(entry)} class="rounded px-2 py-1 text-clef-stone-300 hover:text-clef-claret disabled:opacity-50">Remove</button>
          </span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="text-xs text-clef-stone-300/70">Only you (and the people you share your library with) can see it.</p>
  {/if}

  <form class="flex flex-wrap items-center gap-2" onsubmit={share}>
    <select bind:value={target} aria-label="Share with" class="w-48 rounded border border-clef-graphite-500 bg-clef-charcoal px-3 py-2">
      <option value="">Share with…</option>
      {#if groups.some((g) => !sharedGroups.has(g.id))}
        <optgroup label="Groups">
          {#each groups.filter((g) => !sharedGroups.has(g.id)) as group (group.id)}
            <option value="group:{group.id}">{group.name}</option>
          {/each}
        </optgroup>
      {/if}
      <optgroup label="People">
        {#each people.filter((p) => !sharedUsers.has(p.id)) as person (person.id)}
          <option value="user:{person.id}">{person.username}</option>
        {/each}
      </optgroup>
    </select>
    <select bind:value={permission} aria-label="Permission" class="rounded border border-clef-graphite-500 bg-clef-charcoal px-2 py-2">
      <option value="view">Can view</option>
      <option value="contribute">Can add</option>
    </select>
    <button type="submit" disabled={busy || !target} class="rounded border border-clef-graphite-500 px-3 py-2 hover:border-clef-claret disabled:opacity-50">Share</button>
  </form>
  {#if error}<p class="text-clef-claret">{error}</p>{/if}
</section>
