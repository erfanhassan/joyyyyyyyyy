import { useEffect, useState } from "react";
import { useTenant } from "@/lib/tenant-context";
import { apiUrl } from "@/lib/api";

interface Readiness {
  blockers: string[];
  phone_reason: string;
  public_onboarding_enabled: boolean;
  checkout_reviews: number;
  delivery_reviews: number;
  jobs: {id: string; provider: string; status: string; attempts: number}[];
}

export function OperationalStatus() {
  const {tenantId} = useTenant();
  const [state, setState] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!tenantId) return;
    let live = true;
    const load = async () => {
      try {
        const response = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/operations`));
        if (!response.ok) throw new Error("Operational status could not be loaded.");
        const data = await response.json();
        if (live) {setState(data); setError("");}
      } catch(problem) {if(live) setError(problem instanceof Error ? problem.message : "Status unavailable.");}
    };
    load();
    const timer = setInterval(load, 15000);
    return () => {live=false; clearInterval(timer);};
  }, [tenantId]);
  return <section className="rounded-xl border bg-card p-5" aria-label="Operational readiness">
    <h2 className="font-semibold">Operational readiness</h2>
    {error && <p role="alert" className="my-2 text-sm text-destructive">{error}</p>}
    {state && <>
      <p className="my-2 text-sm">{state.public_onboarding_enabled ? "Merchant onboarding enabled" : "Owner-only release — public onboarding disabled"}</p>
      <ul className="list-inside list-disc text-sm text-muted-foreground">
        {state.blockers.map(item=><li key={item}>{item}</li>)}
        <li>{state.phone_reason}</li>
        <li>Live provider acceptance tests are required before public launch.</li>
      </ul>
      <p className="mt-2 text-sm font-medium">Phone confirmation: unavailable until the voice worker and SIP route pass a real test.</p>
      <p className="mt-3 text-sm">Checkout reviews: {state.checkout_reviews} · Delivery reviews: {state.delivery_reviews}</p>
      {!!state.jobs.length && <details className="mt-3 text-sm"><summary>Queued and failed events ({state.jobs.length})</summary>
        <ul>{state.jobs.map(job=><li key={job.id}>{job.provider}: {job.status} · attempts {job.attempts} · {job.id}</li>)}</ul>
      </details>}
    </>}
  </section>;
}
