import { Link } from "wouter";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-surface text-foreground flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-bold">404 Page Not Found</h1>
        <p className="mt-2 text-sm text-muted">This page does not exist.</p>
        <Link href="/" className="inline-block mt-4 text-sm font-semibold text-brand-700 hover:underline">
          Back to JOY
        </Link>
      </div>
    </div>
  );
}
