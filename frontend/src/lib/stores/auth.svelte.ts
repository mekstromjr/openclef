/**
 * Reactive auth state shared across the SPA.
 *
 * Svelte 5 $state-based store. The single `authState` object is the
 * source of truth; components read from it directly. `bootstrap()`
 * runs once on app load and sets `user` to the result of /auth/me
 * (or null on 401), plus `setupComplete` from /setup/status.
 *
 * Route guards (in +layout.svelte) consume these to decide redirects.
 */
import { ApiError, api, type SetupStatus, type User } from '$lib/api';

export type AuthState = {
  user: User | null;
  setupComplete: boolean | null; // null = not yet checked
  loading: boolean;
};

export const authState = $state<AuthState>({
  user: null,
  setupComplete: null,
  loading: true
});

export async function bootstrap(): Promise<void> {
  authState.loading = true;
  try {
    const status = await api.get<SetupStatus>('/api/v1/setup/status');
    authState.setupComplete = status.users_exist;
  } catch {
    authState.setupComplete = null;
  }

  if (authState.setupComplete) {
    try {
      authState.user = await api.get<User>('/api/v1/auth/me');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        authState.user = null;
      } else {
        throw e;
      }
    }
  } else {
    authState.user = null;
  }
  authState.loading = false;
}

export async function login(username: string, password: string): Promise<void> {
  authState.user = await api.post<User>('/api/v1/auth/login', { username, password });
  authState.setupComplete = true;
}

export async function logout(): Promise<void> {
  await api.post<void>('/api/v1/auth/logout');
  authState.user = null;
}

export async function setup(
  username: string,
  password: string,
  email?: string
): Promise<void> {
  authState.user = await api.post<User>('/api/v1/setup', {
    username,
    password,
    email: email || null
  });
  authState.setupComplete = true;
}
