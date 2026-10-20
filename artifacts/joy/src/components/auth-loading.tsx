import { useEffect, useState } from 'react';

/** Keep authentication failures visible instead of leaving an empty screen. */
export function AuthLoading({ label = 'Loading secure sign-in…' }: { label?: string }) {
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setTimedOut(true), 15000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <section className="mx-auto w-full max-w-md rounded-2xl border border-border bg-white p-8 text-center shadow-sm">
      <h1 className="text-xl font-bold text-foreground">
        {timedOut ? 'Secure sign-in could not load' : label}
      </h1>
      <p role={timedOut ? 'alert' : 'status'} className="mt-3 text-sm leading-6 text-muted">
        {timedOut
          ? 'The sign-in service did not respond. Please retry. Your dashboard remains protected.'
          : 'Connecting to the authentication service. This should only take a moment.'}
      </p>
      {timedOut && (
        <div className="mt-6 flex justify-center gap-4">
          <button
            type="button"
            className="rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-white"
            onClick={() => window.location.reload()}
          >
            Retry
          </button>
          <a className="px-4 py-2 text-sm font-semibold text-brand-700" href={import.meta.env.BASE_URL}>
            Back to JOY
          </a>
        </div>
      )}
    </section>
  );
}
