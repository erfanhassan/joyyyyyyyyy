/**
 * Universal API & WebSocket endpoint resolution helper.
 * 
 * Works dynamically in:
 * 1. Local development (the dev server rewrites to local FastAPI)
 * 2. Replit cloud hosting (*.replit.app)
 * 3. Custom domain / Hostinger subdomain
 */

export const getApiBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    const customUrl = import.meta.env.VITE_API_URL;
    // If NEXT_PUBLIC_API_URL is set to an external URL (not hardcoded localhost:8000), use it
    if (customUrl && customUrl.trim() !== "" && !customUrl.includes("localhost:8000")) {
      return customUrl.replace(/\/$/, "");
    }
    // Default to empty string in browser: requests will be relative (e.g., /api/v1/...)
    // and handled seamlessly by the dev server rewrites proxy to backend
    return "";
  }
  // Server-side fallback
  return import.meta.env.VITE_INTERNAL_BACKEND_URL || "http://127.0.0.1:8000";
};

export const apiUrl = (endpoint: string): string => {
  const base = getApiBaseUrl();
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
};

export const getWsUrl = (path: string = ""): string => {
  if (typeof window === "undefined") return "";

  if (import.meta.env.VITE_WS_URL) {
    const customWs = import.meta.env.VITE_WS_URL.replace(/\/$/, "");
    return `${customWs}${path.startsWith("/") ? path : `/${path}`}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path.startsWith("/") ? path : `/${path}`}`;
};
