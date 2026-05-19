import { api } from './api';

/**
 * Auth helpers. The rest of the app doesn't care how auth works —
 * it just calls login(), logout(), and getMe().
 *
 * SOCIAL AUTH SCAFFOLD:
 * Add login({ provider: 'google', token }) branch here.
 * The cookie-setting happens server-side either way — no
 * changes needed in middleware or protected pages.
 */

export async function register({ username, email, password }) {
  return api.post('/api/auth/register/', { username, email, password });
}

export async function login({ username, password }) {
  return api.post('/api/auth/login/', { username, password });

  // SOCIAL AUTH SCAFFOLD:
  // if (provider) {
  //   return api.post('/api/auth/social/', { provider, token });
  // }
}

export async function logout() {
  return api.post('/api/auth/logout/', {});
}

export async function getMe() {
  return api.get('/api/auth/me/');
}

// PASSWORD RESET SCAFFOLD:
// export async function requestPasswordReset(email) {
//   return api.post('/api/auth/password/reset/', { email });
// }
// export async function confirmPasswordReset({ token, password }) {
//   return api.post('/api/auth/password/reset/confirm/', { token, password });
// }

// EMAIL VERIFICATION SCAFFOLD:
// export async function verifyEmail(token) {
//   return api.post('/api/auth/email/verify/confirm/', { token });
// }