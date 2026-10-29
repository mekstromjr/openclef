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

// --- Library ---

// All 30 key signatures, circle-of-fifths order (matches the backend enum).
// Enharmonic keys are distinct on purpose: the spelling is what's printed.
export const MAJOR_KEYS = [
  'C major', 'G major', 'D major', 'A major', 'E major', 'B major', 'F# major', 'C# major',
  'Cb major', 'Gb major', 'Db major', 'Ab major', 'Eb major', 'Bb major', 'F major'
] as const;
export const MINOR_KEYS = [
  'A minor', 'E minor', 'B minor', 'F# minor', 'C# minor', 'G# minor', 'D# minor', 'A# minor',
  'Ab minor', 'Eb minor', 'Bb minor', 'F minor', 'C minor', 'G minor', 'D minor'
] as const;
export const OTHER_KEYS = ['Atonal', 'Modal', 'None', 'Multiple'] as const;
export const KEY_SIGNATURES = [...MAJOR_KEYS, ...MINOR_KEYS, ...OTHER_KEYS];

/** "Gb major" -> "G♭ major" for display; stored values keep ASCII. */
export function formatKey(key: string): string {
  return key.replace(/^([A-G])b/, '$1♭').replace(/^([A-G])#/, '$1♯');
}

export const PART_TYPES = [
  'Full Score', 'Conductor Score', 'Piano Reduction', 'Vocal Score', 'Other'
] as const;

export type PartType = (typeof PART_TYPES)[number];

export interface ArrangementSummary {
  id: string;
  title: string;
  subtitle: string | null;
  composer: string[];
  arranger: string[];
  instrumentation: string[];
  key_signature: string | null;
  period: string | null;
  difficulty: number | null;
  created_at: string;
  part_count: number;
  cover_part_id: string | null;
  cover_thumbnail_ready: boolean;
}

export interface FacetCount {
  value: string;
  count: number;
}

export type FacetName = 'instrument' | 'composer' | 'key' | 'period' | 'difficulty' | 'tag';

export interface ArrangementList {
  items: ArrangementSummary[];
  total: number;
  page: number;
  page_size: number;
  facets: Record<FacetName, FacetCount[]>;
}

export interface UploadMetadata {
  title?: string;
  composer?: string[];
  arranger?: string[];
  instrumentation?: string[];
  key_signature?: string;
  difficulty?: number;
}

/**
 * Upload one PDF as a new arrangement. Uses XMLHttpRequest rather than
 * fetch because fetch can't report upload progress.
 */
export function uploadArrangement(
  file: File,
  options: { metadata?: UploadMetadata; partType?: PartType; onProgress?: (fraction: number) => void }
): Promise<{ arrangement: { id: string; title: string } }> {
  const form = new FormData();
  form.append('file', file);
  if (options.metadata && Object.keys(options.metadata).length > 0) {
    form.append('metadata', JSON.stringify(options.metadata));
  }
  if (options.partType) form.append('part_type', options.partType);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/arrangements/upload');
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error body */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as { arrangement: { id: string; title: string } });
      } else {
        reject(new ApiError(xhr.status, (payload as { detail?: unknown })?.detail ?? xhr.statusText));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, 'network_error'));
    xhr.send(form);
  });
}

/** Human-readable message for an upload failure. */
export function uploadErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Upload failed.';
  switch (error.status) {
    case 0:
      return 'Network error. Check your connection and try again.';
    case 401:
      return 'Your session expired. Sign in again.';
    case 413:
      return 'This PDF is larger than the upload limit.';
    case 415:
      return error.detail === 'not_a_pdf'
        ? 'This file is not a PDF.'
        : 'This PDF could not be read. It may be damaged.';
    default:
      return `Upload failed (${error.status}).`;
  }
}
