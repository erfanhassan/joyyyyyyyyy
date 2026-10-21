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

const FALLBACK_TENANT_ID = "a1e6f58d-b575-420e-b4d6-1fef0064e746";

const TenantContext = createContext<TenantContextValue>({
  tenant: null,
  tenantId: FALLBACK_TENANT_ID,
  isLoading: true,
  error: null,
  refetchTenant: async () => {},
  updateTenant: async () => false,
});

export const TenantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tenant, setTenant] = useState<TenantProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchTenant = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(apiUrl("/api/v1/tenant/me"));
      if (res.ok) {
        const data = await res.json();
        setTenant(data);
        setError(null);
      } else {
        // Fallback to fetching default tenant profile
        const fallbackRes = await fetch(apiUrl(`/api/v1/tenant/${FALLBACK_TENANT_ID}`));
        if (fallbackRes.ok) {
          const fallbackData = await fallbackRes.json();
          setTenant(fallbackData);
        }
      }
    } catch (err: any) {
      console.warn("Failed to resolve dynamic workspace, using local storefront context:", err);
      setError(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTenant();
  }, []);

  const updateTenant = async (updates: Partial<TenantProfile>): Promise<boolean> => {
    const targetId = tenant?.id || FALLBACK_TENANT_ID;
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

  const tenantId = tenant?.id || FALLBACK_TENANT_ID;

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
