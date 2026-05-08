/**
 * Tiny fetch wrapper that always sends cookies (so the session cookie
 * propagates) and JSON-encodes bodies. All API calls go through here.
 *
 * Throws ApiError on non-2xx responses; the message is the parsed
 * `detail` field if the server returned JSON, otherwise statusText.
 */
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined
  });
  if (r.status === 204) return undefined as T;
  let payload: unknown;
  try {
    payload = await r.json();
  } catch {
    payload = null;
  }
  if (!r.ok) {
    const detail = (payload as { detail?: unknown })?.detail ?? r.statusText;
    throw new ApiError(r.status, detail);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path)
};

// --- Domain types (subset for Phase 1 auth surface) ---

export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  username: string;
  email: string | null;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface UserSettings {
  user_id: string;
  theme: 'light' | 'dark' | 'system';
  enrichment_default_enabled: boolean;
  enrichment_providers_jsonb: { provider: string; enabled: boolean }[];
  preferences_jsonb: Record<string, unknown>;
}

export interface SetupStatus {
  users_exist: boolean;
}
