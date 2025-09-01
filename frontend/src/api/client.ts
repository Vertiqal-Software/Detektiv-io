// frontend/src/api/client.ts
// Detecktiv.io – API Client (fetch-based with auth, refresh, and safety)
// - Zero external deps; works with your Vite proxy (/api) or VITE_API_URL
// - Defensive JSON parsing, timeouts, consistent error shapes
// - Token storage (access/refresh) with helpers

// =========================
// Environment / Base URL
// =========================
const DEFAULT_BASE = (typeof window !== 'undefined' && window.location?.origin) || '';
// Prefer /api (Vite proxy) in dev. Fallback to VITE_API_URL if provided.
const API_BASE_URL: string =
  (import.meta as any)?.env?.VITE_API_URL // e.g. http://localhost:8000
    ? (import.meta as any).env.VITE_API_URL
    : '/api';

// Normalize to avoid double slashes when joining
const trimSlash = (s: string) => s.replace(/\/+$/, '');
const baseUrl = trimSlash(API_BASE_URL);

// =========================
// Token Storage Helpers
// =========================
type TokenBundle = {
  access_token: string;
  refresh_token?: string;
  token_type?: string; // usually 'bearer'
  expires_in?: number; // seconds
  // optional: when the token will expire (epoch ms)
  expires_at?: number;
};

const STORAGE_KEY = 'detecktiv.auth';

function loadTokens(): TokenBundle | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TokenBundle) : null;
  } catch {
    return null;
  }
}

function saveTokens(tokens: TokenBundle | null) {
  try {
    if (!tokens) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    // Compute expires_at if expires_in
    const copy: TokenBundle = { ...tokens };
    if (typeof tokens.expires_in === 'number' && !tokens.expires_at) {
      copy.expires_at = Date.now() + tokens.expires_in * 1000;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(copy));
  } catch {
    // Ignore storage errors
  }
}

export function getAccessToken(): string | null {
  return loadTokens()?.access_token ?? null;
}

export function getRefreshToken(): string | undefined {
  return loadTokens()?.refresh_token;
}

export function setTokens(tokens: TokenBundle) {
  saveTokens(tokens);
}

export function clearTokens() {
  saveTokens(null);
}

// =========================
// Fetch Helpers
// =========================

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';
export type Json = Record<string, unknown> | Array<unknown> | null;

export type HttpError = {
  status: number;
  url: string;
  message: string;
  details?: any;
};

function isJsonResponse(resp: Response) {
  const ct = resp.headers.get('content-type') || '';
  return ct.includes('application/json');
}

async function safeParseJson(resp: Response): Promise<any> {
  try {
    return await resp.json();
  } catch {
    return null;
  }
}

function withTimeout<T>(p: Promise<T>, ms: number, desc = 'request'): Promise<T> {
  return new Promise((resolve, reject) => {
    const id = setTimeout(() => reject(new Error(`Timeout after ${ms}ms: ${desc}`)), ms);
    p.then(
      (v) => {
        clearTimeout(id);
        resolve(v);
      },
      (e) => {
        clearTimeout(id);
        reject(e);
      }
    );
  });
}

type RequestOptions = {
  method?: HttpMethod;
  body?: any;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  timeoutMs?: number; // default 15000
  // internal
  _isRetry?: boolean; // used to prevent refresh loops
};

function qs(params?: RequestOptions['query']): string {
  if (!params) return '';
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

async function coreFetch(path: string, opts: RequestOptions = {}) {
  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs ?? 15000;

  const url = `${baseUrl}${path}${qs(opts.query)}`;
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
    ...(opts.headers || {}),
  };

  // Attach Authorization if we have a token
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const fetchPromise = fetch(url, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: controller.signal,
    credentials: 'include', // allows cookie-based flows if used for refresh
  });

  try {
    const resp = await withTimeout(fetchPromise, timeoutMs, `${opts.method ?? 'GET'} ${path}`);

    if (resp.status === 204) return null; // No Content
    const data = isJsonResponse(resp) ? await safeParseJson(resp) : await resp.text();

    if (!resp.ok) {
      // If 401 and we have a refresh token, try once to refresh then retry
      if (resp.status === 401 && !opts._isRetry && getRefreshToken()) {
        const refreshed = await tryRefreshToken();
        if (refreshed) {
          return coreFetch(path, { ...opts, _isRetry: true });
        } else {
          clearTokens();
        }
      }

      const err: HttpError = {
        status: resp.status,
        url,
        message:
          (data && (data.message || data.detail || data.error)) ||
          `HTTP ${resp.status} for ${url}`,
        details: data,
      };
      throw err;
    }

    return data;
  } finally {
    controller.abort(); // defensive; ensures signal cleanup after resolution
  }
}

let refreshingPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (refreshingPromise) return refreshingPromise;

  refreshingPromise = (async () => {
    const refresh = getRefreshToken();
    if (!refresh) return false;

    try {
      // Common FastAPI pattern: POST /v1/auth/refresh
      const data = await coreFetch('/v1/auth/refresh', {
        method: 'POST',
        body: { refresh_token: refresh },
        // prevent infinite loop if refresh also 401s
        _isRetry: true,
      });

      if (data && data.access_token) {
        setTokens({
          access_token: data.access_token,
          refresh_token: data.refresh_token || refresh,
          token_type: data.token_type || 'bearer',
          expires_in: data.expires_in,
        });
        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      refreshingPromise = null;
    }
  })();

  return refreshingPromise;
}

// Public HTTP interface
export const http = {
  get: <T = any>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    coreFetch(path, { ...opts, method: 'GET' }) as Promise<T>,
  post: <T = any>(path: string, body?: Json, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    coreFetch(path, { ...opts, method: 'POST', body }) as Promise<T>,
  patch: <T = any>(path: string, body?: Json, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    coreFetch(path, { ...opts, method: 'PATCH', body }) as Promise<T>,
  delete: <T = any>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    coreFetch(path, { ...opts, method: 'DELETE' }) as Promise<T>,
};

// =========================
// API: Auth
// =========================

export type LoginRequest = {
  email: string;
  password: string;
};

export type LoginResponse = {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
  user?: {
    id: number;
    name?: string;
    email?: string;
    is_admin?: boolean;
  };
};

export const AuthApi = {
  async login(payload: LoginRequest): Promise<LoginResponse> {
    // Basic input validation to avoid common mistakes
    if (!payload?.email || !payload?.password) {
      throw new Error('Email and password are required.');
    }

    const res = await http.post<LoginResponse>('/v1/auth/login', payload);
    if (res?.access_token) setTokens(res);
    return res;
  },

  async me() {
    return http.get('/v1/users/me');
  },

  logout() {
    clearTokens();
  },
};

// =========================
// API: Users (used by Users pages)
// =========================

export type User = {
  id: number;
  email: string;
  name?: string;
  is_active?: boolean;
  is_admin?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type UserCreate = {
  email: string;
  name?: string;
  password?: string;
  is_admin?: boolean;
};

export type UserUpdate = {
  email?: string;
  name?: string;
  password?: string;
  is_admin?: boolean;
  is_active?: boolean;
};

export const UsersApi = {
  async list(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    is_active?: boolean;
  }): Promise<{ items: User[]; total: number; page: number; page_size: number }> {
    return http.get('/v1/users', { query: params });
  },

  async get(id: number): Promise<User> {
    if (!Number.isFinite(id)) throw new Error('Valid user id required');
    return http.get(`/v1/users/${id}`);
  },

  async create(data: UserCreate): Promise<User> {
    if (!data?.email) throw new Error('email is required');
    return http.post('/v1/users', data);
  },

  async update(id: number, data: UserUpdate): Promise<User> {
    if (!Number.isFinite(id)) throw new Error('Valid user id required');
    return http.patch(`/v1/users/${id}`, data);
  },

  // Many APIs “deactivate” via DELETE; others may use PATCH {is_active:false}.
  // We implement DELETE first (matches typical admin UX).
  async deactivate(id: number): Promise<{ success: boolean }> {
    if (!Number.isFinite(id)) throw new Error('Valid user id required');
    const res = await http.delete(`/v1/users/${id}`);
    return res ?? { success: true };
  },
};

// =========================
// Optional: Companies API (scaffold for later)
// =========================

export const CompaniesApi = {
  list(params?: { page?: number; page_size?: number; q?: string }) {
    return http.get('/v1/companies', { query: params });
  },
  get(id: number) {
    return http.get(`/v1/companies/${id}`);
  },
  create(data: Record<string, any>) {
    return http.post('/v1/companies', data);
  },
  update(id: number, data: Record<string, any>) {
    return http.patch(`/v1/companies/${id}`, data);
  },
  remove(id: number) {
    return http.delete(`/v1/companies/${id}`);
  },
};

// =========================
// Minimal runtime logging
// =========================
if (import.meta.env?.MODE !== 'production') {
  // eslint-disable-next-line no-console
  console.log('[detecktiv] API base:', baseUrl || DEFAULT_BASE);
}
