<script lang="ts">
  import { goto } from '$app/navigation';
  import { ApiError } from '$lib/api';
  import { setup } from '$lib/stores/auth.svelte';

  let username = $state('');
  let password = $state('');
  let confirm = $state('');
  let email = $state('');
  let error = $state<string | null>(null);
  let submitting = $state(false);

  function validate(): string | null {
    if (username.length < 1) return 'Username is required.';
    if (password.length < 8) return 'Password must be at least 8 characters.';
    if (password !== confirm) return "Passwords don't match.";
    return null;
  }

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    error = validate();
    if (error) return;

    submitting = true;
    try {
      await setup(username, password, email || undefined);
      await goto('/');
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 409) {
          error = 'Setup is already complete. Reload to sign in.';
        } else {
          error = `Setup failed (${e.status}).`;
        }
      } else {
        error = 'Network error. Try again.';
      }
    } finally {
      submitting = false;
    }
  }
</script>

<div class="min-h-[80vh] flex items-center justify-center px-6">
  <form
    onsubmit={handleSubmit}
    class="w-full max-w-md space-y-6 bg-zinc-900/50 border border-zinc-800 rounded-lg p-8"
  >
    <div class="text-center space-y-1">
      <h1 class="text-2xl font-semibold">Welcome to OpenClef</h1>
      <p class="text-sm text-zinc-500">
        Create the administrator account to get started. You can add other users
        later from the Settings page.
      </p>
    </div>

    <div class="space-y-3">
      <label class="block text-sm">
        <span class="text-zinc-400">Username</span>
        <input
          type="text"
          bind:value={username}
          required
          autocomplete="username"
          autofocus
          class="mt-1 w-full px-3 py-2 rounded bg-zinc-950 border border-zinc-800 focus:border-zinc-600 focus:outline-none"
        />
      </label>

      <label class="block text-sm">
        <span class="text-zinc-400">Email (optional)</span>
        <input
          type="email"
          bind:value={email}
          autocomplete="email"
          class="mt-1 w-full px-3 py-2 rounded bg-zinc-950 border border-zinc-800 focus:border-zinc-600 focus:outline-none"
        />
      </label>

      <label class="block text-sm">
        <span class="text-zinc-400">Password (≥ 8 characters)</span>
        <input
          type="password"
          bind:value={password}
          required
          autocomplete="new-password"
          minlength="8"
          class="mt-1 w-full px-3 py-2 rounded bg-zinc-950 border border-zinc-800 focus:border-zinc-600 focus:outline-none"
        />
      </label>

      <label class="block text-sm">
        <span class="text-zinc-400">Confirm password</span>
        <input
          type="password"
          bind:value={confirm}
          required
          autocomplete="new-password"
          minlength="8"
          class="mt-1 w-full px-3 py-2 rounded bg-zinc-950 border border-zinc-800 focus:border-zinc-600 focus:outline-none"
        />
      </label>
    </div>

    {#if error}
      <div class="text-sm text-red-400">{error}</div>
    {/if}

    <button
      type="submit"
      disabled={submitting}
      class="w-full py-2 rounded bg-zinc-100 text-zinc-950 font-medium disabled:opacity-50"
    >
      {submitting ? 'Creating…' : 'Create administrator'}
    </button>
  </form>
</div>
