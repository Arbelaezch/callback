'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';

/**
 * Navbar — shown on all authenticated pages via layout.
 * Shows:
 *   - Unauthenticated: app name + Login button
 *   - Authenticated:   app name + username + Profile link + Logout button
 *
 * Reads auth state from AuthContext via useAuth().
 * Redirects to /login after logout.
 */
export default function Navbar() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  async function handleLogout() {
    console.debug('[Navbar] logging out');
    try {
      await logout();
    } catch (err) {
      console.error('[Navbar] logout error', err);
    }
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