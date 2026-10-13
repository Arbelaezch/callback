const API_URL = process.env.NEXT_PUBLIC_API_URL;

/**
 * Core fetch wrapper. All API calls go through here.
 * Credentials: 'include' ensures cookies are sent with every request.
 *
 * On 401, attempts a token refresh and retries the original request once.
 * Auth mutation routes are excluded from the refresh attempt since a 401
 * there is a genuine auth failure, not an expired token.
 *
 * Concurrent 401s share a single refresh attempt via refreshPromise —
 * prevents a thundering herd of parallel refresh calls on restart.
 *
 * Refresh tokens rotate, so refreshes are also serialized across tabs with
 * the Web Locks API: each tab sends whatever refresh cookie is current when it
 * gets the lock. If a refresh still loses a race, the backend answers 401 with
 * code 'token_rotated' (and keeps the cookies another tab just set); the
 * original request is then retried once.
 *
 * SOCIAL AUTH SCAFFOLD:
 * When adding social providers, pass provider tokens through this
 * same wrapper to /api/auth/social/ — no changes needed here.
 */

const AUTH_NO_REFRESH = [
  '/api/auth/login/',
  '/api/auth/logout/',
  '/api/auth/register/',
  '/api/auth/token/refresh/',
];

const REFRESH_LOCK = 'callback-auth-refresh';

// Wait before retrying after a lost refresh race so the winning tab's
// Set-Cookie has time to land.
const ROTATED_RETRY_DELAY_MS = 250;

let refreshPromise = null;

function postRefresh() {
  return fetch(`${API_URL}/api/auth/token/refresh/`, {
    method: 'POST',
    credentials: 'include',
  });
}

// Resolves to { ok, rotated } (not a Response: a body can only be read once
// and several callers share this promise).
function refreshToken() {
  if (refreshPromise) return refreshPromise;

  const run = () =>
    postRefresh().then(async (res) => {
      if (res.ok) return { ok: true, rotated: false };
      const body = await res.json().catch(() => ({}));
      return { ok: false, rotated: body.code === 'token_rotated' };
    });

  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;

  refreshPromise = (locks ? locks.request(REFRESH_LOCK, run) : run()).finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

/**
 * Read a successful response. `parse` is 'json' (default), 'text', or 'blob'.
 * Blobs come back as { blob, pageCount } so PDF downloads can warn on overflow.
 */
async function readBody(res, parse) {
  if (res.status === 204) return null;
  if (parse === 'text') return res.text();
  if (parse === 'blob') {
    return {
      blob: await res.blob(),
      pageCount: Number(res.headers.get('X-Page-Count')) || null,
    };
  }
  return res.json();
}

async function request(path, options = {}, parse = 'json') {
  const { headers: extraHeaders, ...restOptions } = options;
  const isFormData = restOptions.body instanceof FormData;

  const send = () =>
    fetch(`${API_URL}${path}`, {
      ...restOptions,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...extraHeaders,
      },
      credentials: 'include',
    });

  const res = await send();

  // Token expired — try to refresh once then retry
  if (res.status === 401) {
    if (AUTH_NO_REFRESH.includes(path)) {
      const error = await res.json().catch(() => ({ detail: 'An error occurred.' }));
      throw { status: res.status, ...error };
    }

    const refreshed = await refreshToken();

    if (refreshed.ok || refreshed.rotated) {
      // Retry original request once with the new cookie
      if (refreshed.rotated) {
        await new Promise((resolve) => setTimeout(resolve, ROTATED_RETRY_DELAY_MS));
      }
      const retry = await send();

      if (retry.status === 401 && refreshed.rotated) {
        throw { status: 401, detail: 'Session expired.' };
      }

      if (!retry.ok) {
        const error = await retry.json().catch(() => ({ detail: 'An error occurred.' }));
        throw { status: retry.status, ...error };
      }
      return readBody(retry, parse);
    }

    // Refresh also failed — session is dead
    throw { status: 401, detail: 'Session expired.' };
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'An error occurred.' }));
    throw { status: res.status, ...error };
  }

  return readBody(res, parse);
}

export const apiClient = {
  get: (path) => request(path),
  getText: (path) => request(path, {}, 'text'),
  getBlob: (path) => request(path, {}, 'blob'),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  multipart: (path, formData) =>
    request(path, {
      method: 'POST',
      body: formData,
      // Content-Type omitted — browser sets multipart boundary automatically
    }),
};