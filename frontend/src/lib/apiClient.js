const API_URL = process.env.NEXT_PUBLIC_API_URL;
// console.log('[apiClient] API_URL=', process.env.NEXT_PUBLIC_API_URL);

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
  const isFormData = restOptions.body instanceof FormData;

  const res = await fetch(`${API_URL}${path}`, {
    ...restOptions,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...extraHeaders,
    },
    credentials: 'include',
  });

  // Token expired — try to refresh once then retry
  if (res.status === 401) {
    if (path.startsWith('/api/auth/')) {
      const error = await res.json().catch(() => ({ detail: 'An error occurred.' }));
      throw { status: res.status, ...error };
    }

    const refreshed = await fetch(`${API_URL}/api/auth/token/refresh/`, {
      method: 'POST',
      credentials: 'include',
    });

    if (refreshed.ok) {
      // Retry original request with new cookie
      const retry = await fetch(`${API_URL}${path}`, {
        ...restOptions,
        headers: {
          ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
          ...extraHeaders,
        },
        credentials: 'include',
      });

      if (!retry.ok) {
        const error = await retry.json().catch(() => ({ detail: 'An error occurred.' }));
        throw { status: retry.status, ...error };
      }
      if (retry.status === 204) return null;
      return retry.json();
    }

    // Refresh also failed — session is dead
    throw { status: 401, detail: 'Session expired.' };
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'An error occurred.' }));
    throw { status: res.status, ...error };
  }

  // 204 No Content
  if (res.status === 204) return null;

  return res.json();
}

export const apiClient = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  multipart: (path, formData) =>
    request(path, {
      method: 'POST',
      body: formData,
      // Content-Type omitted — browser sets multipart boundary automatically
    }),
};