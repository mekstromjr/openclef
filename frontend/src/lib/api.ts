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
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
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
  sso_linked: boolean;
  has_password: boolean;
}

export interface OidcConfig {
  enabled: boolean;
  provider_name: string;
}

/** Plain-language text for the `sso_error` codes the OIDC callback returns. */
export function ssoErrorMessage(code: string): string {
  switch (code) {
    case 'access_denied':
      return 'Sign-in was cancelled, or your account is not allowed to use OpenClef.';
    case 'session_expired':
      return 'The sign-in took too long. Please try again.';
    case 'link_requires_login':
      return 'Sign in with your OpenClef password first, then link single sign-on from Settings.';
    case 'sso_already_linked':
      return 'That single sign-on account is already linked to another OpenClef user.';
    case 'provider_unreachable':
      return 'The sign-in service could not be reached. Try again, or use your password.';
    default:
      return 'Single sign-on failed. Try again, or use your password.';
  }
}

/** Full-page navigation to start the SSO redirect dance. */
export function startSso(next = '/', link = false) {
  const query = new URLSearchParams({ next });
  if (link) query.set('link', '1');
  window.location.assign(`/api/v1/auth/oidc/login?${query}`);
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

export const PERIODS = [
  'Medieval', 'Renaissance', 'Baroque', 'Classical', 'Early Romantic',
  'Romantic', 'Late Romantic', 'Modern', 'Contemporary', 'Various'
] as const;

export interface Part {
  id: string;
  arrangement_id: string;
  part_type: PartType;
  label: string;
  instrument: string | null;
  page_count: number;
  file_size_bytes: number;
  thumbnail_storage_key: string | null;
  uploaded_by: string;
  created_at: string;
}

export interface ArrangementDetail {
  id: string;
  title: string;
  subtitle: string | null;
  composer: string[];
  arranger: string[];
  instrumentation: string[];
  key_signature: string | null;
  period: string | null;
  difficulty: number | null;
  notes: string | null;
  description: string | null;
  owner_id: string;
  created_at: string;
  parts: Part[];
  tags: string[];
  /** Setlists this piece is on; a piece on a setlist can't be deleted. */
  setlists: SetlistRef[];
}

export type ArrangementPatch = Partial<
  Pick<
    ArrangementDetail,
    'title' | 'subtitle' | 'composer' | 'arranger' | 'instrumentation' | 'key_signature' | 'period' | 'difficulty' | 'notes'
  >
>;

export interface UploadMetadata {
  title?: string;
  composer?: string[];
  arranger?: string[];
  instrumentation?: string[];
  key_signature?: string;
  difficulty?: number;
}

/**
 * POST a multipart form with upload progress. XMLHttpRequest rather than
 * fetch, because fetch can't report upload progress.
 */
function postMultipart<T>(url: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error body */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload as T);
      else reject(new ApiError(xhr.status, (payload as { detail?: unknown })?.detail ?? xhr.statusText));
    };
    xhr.onerror = () => reject(new ApiError(0, 'network_error'));
    xhr.send(form);
  });
}

/** Upload one PDF as a new arrangement. */
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
  return postMultipart('/api/v1/arrangements/upload', form, options.onProgress);
}

/** Add another part (e.g. the cello part) to an arrangement. */
export function uploadPart(
  arrangementId: string,
  file: File,
  options: { partType?: PartType; label?: string; instrument?: string; onProgress?: (fraction: number) => void }
): Promise<Part> {
  const form = new FormData();
  form.append('file', file);
  if (options.partType) form.append('part_type', options.partType);
  if (options.label?.trim()) form.append('label', options.label.trim());
  if (options.instrument?.trim()) form.append('instrument', options.instrument.trim());
  return postMultipart(`/api/v1/arrangements/${arrangementId}/parts`, form, options.onProgress);
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

// --- Setlists ---

export interface SetlistRef {
  id: string;
  name: string;
}

export interface SetlistEntry {
  position: number;
  /**
   * False when this viewer can't see the piece; the API then withholds
   * everything but the position. Pages drop these with `withoutHidden`.
   */
  available: boolean;
  arrangement_id: string;
  title: string;
  subtitle: string | null;
  composer: string[];
  /** The part chosen for this entry; null opens the piece's cover part. */
  part_id: string | null;
  /** The part that will actually open (null only if the piece has no parts). */
  effective_part_id: string | null;
  part_label: string | null;
  page_count: number | null;
  thumbnail_ready: boolean;
}

export interface SetlistSummary {
  id: string;
  name: string;
  owner_id: string;
  owner_username: string;
  item_count: number;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
}

export interface SetlistDetail extends SetlistSummary {
  items: SetlistEntry[];
}

export interface SetlistItemWrite {
  arrangement_id: string;
  part_id: string | null;
}

export const SETLIST_MAX_ITEMS = 200;

/** The setlist with entries this viewer can't see removed, and how many there were. */
export function withoutHidden(setlist: SetlistDetail): { setlist: SetlistDetail; hidden: number } {
  const items = setlist.items.filter((item) => item.available);
  return { setlist: { ...setlist, items }, hidden: setlist.items.length - items.length };
}

export function setlistErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.detail === 'setlist_has_hidden_items')
      return "This setlist has pieces that aren't shared with you, so its order can't be saved yet.";
    if (error.status === 409) return 'This setlist changed somewhere else. Reload to see the latest version.';
    if (error.status === 403) return 'Only the owner of this setlist (or an admin) can change it.';
    if (error.detail === 'setlist_full') return `A setlist holds at most ${SETLIST_MAX_ITEMS} pieces.`;
    if (error.detail === 'arrangement_not_found') return "One of these pieces no longer exists or isn't shared with you. Reload and try again.";
    if (error.status === 404) return "This setlist doesn't exist or isn't shared with you.";
  }
  return 'Saving failed. Try again.';
}
