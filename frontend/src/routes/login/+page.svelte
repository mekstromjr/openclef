<script lang="ts">
  import { goto } from '$app/navigation';
  import { ApiError } from '$lib/api';
  import { login } from '$lib/stores/auth.svelte';

  let username = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let submitting = $state(false);

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    submitting = true;
    try {
      await login(username, password);
      await goto('/');
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 429) {
          const detail = e.detail as { retry_after_seconds?: number };
          error = `Too many attempts. Try again in ${detail.retry_after_seconds ?? 60}s.`;
        } else if (e.status === 401) {
          error = 'Invalid username or password.';
        } else {
          error = `Sign-in failed (${e.status}).`;
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
    class="w-full max-w-sm space-y-5 bg-clef-graphite-700/60 border border-clef-graphite-500 rounded-lg p-8"
  >
    <div class="text-center space-y-1">
      <h1 class="text-2xl font-serif font-semibold">Sign in</h1>
      <p class="text-sm text-clef-stone-300/70">to your OpenClef library</p>
    </div>

    <div class="space-y-3">
      <label class="block text-sm">
        <span class="text-clef-stone-300">Username</span>
        <input
          type="text"
          bind:value={username}
          required
          autocomplete="username"
          autofocus
          class="mt-1 w-full px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 focus:border-clef-claret focus:outline-none"
        />
      </label>

      <label class="block text-sm">
        <span class="text-clef-stone-300">Password</span>
        <input
          type="password"
          bind:value={password}
          required
          autocomplete="current-password"
          class="mt-1 w-full px-3 py-2 rounded bg-clef-charcoal border border-clef-graphite-500 focus:border-clef-claret focus:outline-none"
        />
      </label>
    </div>

    {#if error}
      <div class="text-sm text-clef-claret">{error}</div>
    {/if}

    <button
      type="submit"
      disabled={submitting}
      class="w-full py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50"
    >
      {submitting ? 'Signing in…' : 'Sign in'}
    </button>
  </form>
</div>
