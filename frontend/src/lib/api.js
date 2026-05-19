const API_URL = process.env.NEXT_PUBLIC_API_URL;

/**
 * Core fetch wrapper. All API calls go through here.
 * Credentials: 'include' ensures cookies are sent with every request.
 *
 * SOCIAL AUTH SCAFFOLD:
 * When adding social providers, pass provider tokens through this
 * same wrapper to /api/auth/social/ — no changes needed here.
 */
async function request(path, options = {}) {
    const { headers: extraHeaders, ...restOptions } = options;
    const res = await fetch(`${API_URL}${path}`, {
      ...restOptions,
      headers: {
        'Content-Type': 'application/json',
        ...extraHeaders,
      },
      credentials: 'include',
    });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'An error occurred.' }));
    throw { status: res.status, ...error };
  }

  // 204 No Content
  if (res.status === 204) return null;

  return res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
};