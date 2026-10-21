import React, { createContext, useContext, useEffect, useState } from "react";
import { apiUrl } from "./api";

export interface TenantProfile {
  id: string;
  name: string;
  currency: string;
  timezone: string;
  domain?: string | null;
  settings?: Record<string, any>;
  role?: string;
  active_integrations_count?: number;
  configured_providers?: string[];
}

interface TenantContextValue {
  tenant: TenantProfile | null;
  tenantId: string;
  isLoading: boolean;
  error: Error | null;
  refetchTenant: () => Promise<void>;
  updateTenant: (updates: Partial<TenantProfile>) => Promise<boolean>;
}

const TenantContext = createContext<TenantContextValue>({
  tenant: null,
  tenantId: "",
  isLoading: true,
  error: null,
  refetchTenant: async () => {},
  updateTenant: async () => false,
});

export const TenantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tenant, setTenant] = useState<TenantProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [needsWorkspace, setNeedsWorkspace] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchTenant = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(apiUrl("/api/v1/tenant/me"));
      if (res.ok) {
        const data = await res.json();
        setTenant(data);
        setError(null);
        setNeedsWorkspace(false);
      } else {
        setTenant(null);
        setNeedsWorkspace(res.status === 404);
        const problem = await res.json();
        throw new Error(problem.detail || "Could not load your workspace.");
      }
    } catch (err: any) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTenant();
  }, []);

  const updateTenant = async (updates: Partial<TenantProfile>): Promise<boolean> => {
    if (!tenant?.id) return false;
    const targetId = tenant.id;
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${targetId}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: updates.name || tenant?.name || "My Storefront",
          currency: updates.currency || tenant?.currency || "BDT",
          timezone: updates.timezone || tenant?.timezone || "Asia/Dhaka",
          domain: updates.domain !== undefined ? updates.domain : tenant?.domain,
        }),
      });
      if (res.ok) {
        await fetchTenant();
        return true;
      }
      return false;
    } catch (err) {
      console.error("Failed to update tenant profile:", err);
      return false;
    }
  };

  const tenantId = tenant?.id || "";

  if (isLoading) return <div className="p-8 text-sm text-muted-foreground" role="status">Loading your workspace…</div>;
  if (!tenant) return (
    <section className="m-8 max-w-lg rounded-xl border bg-card p-6">
      <h1 className="text-xl font-semibold">{needsWorkspace ? "Create your business workspace" : "Workspace unavailable"}</h1>
      {error && <p role="alert" className="my-4 text-sm text-destructive">{error.message}</p>}
      {needsWorkspace ? <form onSubmit={async (event) => {
        event.preventDefault();
        setIsCreating(true);
        try {
          const response = await fetch(apiUrl("/api/v1/tenant/onboard"), {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name: workspaceName.trim(), currency: "BDT", timezone: "Asia/Dhaka"})
          });
          if (!response.ok) throw new Error((await response.json()).detail || "Could not create workspace.");
          await fetchTenant();
        } catch (problem) {
          setError(problem instanceof Error ? problem : new Error("Could not create workspace."));
        } finally { setIsCreating(false); }
      }}>
        <label className="block text-sm font-medium" htmlFor="workspace-name">Business name</label>
        <input id="workspace-name" className="my-3 w-full rounded-md border bg-background p-2"
          value={workspaceName} onChange={event => setWorkspaceName(event.target.value)} required maxLength={150} />
        <button className="rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          disabled={isCreating || !workspaceName.trim()}>{isCreating ? "Creating…" : "Create workspace"}</button>
      </form> : <button className="rounded-md border px-4 py-2" onClick={fetchTenant}>Retry</button>}
    </section>
  );

  return (
    <TenantContext.Provider
      value={{
        tenant,
        tenantId,
        isLoading,
        error,
        refetchTenant: fetchTenant,
        updateTenant,
      }}
    >
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = () => useContext(TenantContext);
