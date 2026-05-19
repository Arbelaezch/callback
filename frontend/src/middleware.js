import { NextResponse } from 'next/server';

const PUBLIC_PATHS = ['/login', '/register'];

// PASSWORD RESET SCAFFOLD:
// Add '/forgot-password', '/reset-password' to PUBLIC_PATHS

// SOCIAL AUTH SCAFFOLD:
// Add '/auth/callback' to PUBLIC_PATHS for OAuth redirect handling

export function middleware(request) {
  const { pathname } = request.nextUrl;
  const accessToken = request.cookies.get('access_token')?.value;

  const isPublic = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  // Unauthenticated user hitting a protected route → login
  if (!accessToken && !isPublic) {
    const loginUrl = new URL('/login', request.url);
    // Only pass relative paths — prevents open redirect attacks
    if (pathname.startsWith('/')) {
      loginUrl.searchParams.set('next', pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  // Authenticated user hitting auth pages → dashboard
  if (accessToken && isPublic) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static, _next/image (Next.js internals)
     * - favicon.ico
     * - api routes (handled by Django)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};