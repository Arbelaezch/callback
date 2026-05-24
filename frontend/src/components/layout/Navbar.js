'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { getMe, logout } from '@/lib/auth';

/**
 * Navbar — shown on all authenticated pages via layout.
 * Shows:
 *   - Unauthenticated: app name + Login button
 *   - Authenticated:   app name + username + Profile link + Logout button
 *
 * Intentionally lightweight — no global auth context yet.
 * Fetches /api/auth/me/ on mount to determine state.
 * Replace with a context/SWR hook when the app grows.
 */
export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.debug('[Navbar] fetching current user');
    getMe()
      .then((data) => {
        console.debug('[Navbar] user=%s', data?.username);
        setUser(data);
      })
      .catch((err) => {
        console.debug('[Navbar] not authenticated err=%o', err);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [pathname]); // re-check on route change so logout/login reflects immediately

  async function handleLogout() {
    console.debug('[Navbar] logging out');
    try {
      await logout();
    } catch (err) {
      console.error('[Navbar] logout error', err);
    }
    setUser(null);
    router.push('/login');
  }

  return (
    <nav className="border-b border-border bg-background px-4 py-3 flex items-center justify-between">
      <Link href="/dashboard" className="font-semibold tracking-tight text-foreground">
        Callback
      </Link>

      <div className="flex items-center gap-3 text-sm">
        {loading ? (
          <span className="text-muted-foreground text-xs">...</span>
        ) : user ? (
          <>
            <span className="text-muted-foreground hidden sm:inline">{user.username}</span>

            {/* PROFILE SCAFFOLD: route to /profile once that page exists */}
            <Link
              href="/profile"
              className="rounded-md px-3 py-1.5 border border-input text-foreground hover:bg-muted transition-colors"
            >
              Profile
            </Link>

            <button
              onClick={handleLogout}
              className="rounded-md px-3 py-1.5 border border-input text-foreground hover:bg-muted transition-colors"
            >
              Logout
            </button>
          </>
        ) : (
          <Link
            href="/login"
            className="rounded-md px-3 py-1.5 bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            Login
          </Link>
        )}
      </div>
    </nav>
  );
}