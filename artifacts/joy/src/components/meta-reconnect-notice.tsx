import { useCallback, useEffect, useState } from "react";
import { AlertCircle, ArrowRight } from "lucide-react";
import { Link } from "wouter";
import { apiUrl } from "@/lib/api";

interface ReconnectNotice {
  id: string;
  provider: "meta" | "whatsapp";
  channel: string;
}

export function MetaReconnectNotice({ tenantId }: { tenantId: string }) {
  const [notices, setNotices] = useState<ReconnectNotice[]>([]);

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    try {
      const response = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/reconnect-notices`));
      if (!response.ok) return;
      const data: { notifications?: ReconnectNotice[] } = await response.json();
      setNotices(Array.isArray(data.notifications) ? data.notifications : []);
    } catch {
      // Keep the last known notice visible during temporary network failures.
    }
  }, [tenantId]);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 30_000);
    const refreshOnFocus = () => void refresh();
    const refreshAfterReconnect = () => void refresh();
    window.addEventListener("focus", refreshOnFocus);
    window.addEventListener("joy:integrations-updated", refreshAfterReconnect);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshOnFocus);
      window.removeEventListener("joy:integrations-updated", refreshAfterReconnect);
    };
  }, [refresh]);

  if (notices.length === 0) return null;

  return (
    <section
      className="mb-6 space-y-3"
      aria-label="Meta connection notifications"
      aria-live="polite"
    >
      {notices.map((notice) => (
        <div
          key={notice.id}
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
            <div>
              <p className="font-semibold">{notice.channel} connection needs to be reconnected</p>
              <p className="mt-1 text-sm text-amber-900">
                Replies are paused until access is restored. Reconnect the account to resume them.
              </p>
            </div>
          </div>
          <Link
            href="/dashboard/integration-hub"
            className="inline-flex shrink-0 items-center gap-2 self-start rounded-lg bg-amber-900 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-950 sm:self-auto"
          >
            Reconnect account
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      ))}
    </section>
  );
}
