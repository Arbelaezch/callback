import { redirect } from 'next/navigation';

// Root redirects to the jobs list — middleware handles auth check.
// If unauthenticated, middleware will redirect to /login from there.
export default function RootPage() {
  redirect('/jobs');
}