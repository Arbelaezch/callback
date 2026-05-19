import { redirect } from 'next/navigation';

// Root redirects to dashboard — middleware handles auth check.
// If unauthenticated, middleware will redirect to /login from there.
export default function RootPage() {
  redirect('/dashboard');
}