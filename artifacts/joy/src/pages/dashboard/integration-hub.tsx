
import React, { useState, useEffect, useRef } from "react";
import { WhatsAppConnection } from "@/components/whatsapp-connection";
import { OperationalStatus } from "@/components/operational-status";
import { PrivacyRequests } from "@/components/privacy-requests";
import { WidgetOriginSettings } from "@/components/widget-origin-settings";
import { Link } from "wouter";
import {
  Share2,
  ShoppingBag,
  Store,
  Code2,
  CheckCircle2,
  AlertCircle,
  Info,
  Copy,
  Check,
  Shield,
  ExternalLink,
  RefreshCw,
  Sparkles,
  Lock,
  ArrowRight,
  Plus,
  Trash2,
  Activity,
  MessageSquare,
  Send,
  X,
  PhoneCall,
  PhoneForwarded
} from "lucide-react";
import { apiUrl } from "@/lib/api";
import { IntegrationDiagnostic } from "@/components/integration-diagnostic";
import { useTenant } from "@/lib/tenant-context";
import { loadMetaSdk } from "@/lib/meta-sdk";

interface IntegrationRecord {
  id: string;
  provider: string;
  is_active: boolean;
  masked_token: string;
  settings: Record<string, any>;
  created_at?: string;
}

export default function IntegrationHubPage() {
  const widgetSession = useRef<{customer_id:string;token:string} | null>(null);
  const { tenantId } = useTenant();

  const [integrations, setIntegrations] = useState<IntegrationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  // Modals state
  const [metaModalOpen, setMetaModalOpen] = useState(false);
  const [shopifyModalOpen, setShopifyModalOpen] = useState(false);
  const [wooModalOpen, setWooModalOpen] = useState(false);
  const [widgetPreviewOpen, setWidgetPreviewOpen] = useState(false);

  // Meta Form Inputs & OAuth
  const [metaTab, setMetaTab] = useState<"oauth" | "manual">("oauth");
  const [metaPageName, setMetaPageName] = useState("Official Storefront");
  const [metaPageId, setMetaPageId] = useState("");
  const [metaIgId, setMetaIgId] = useState("");
  const [metaToken, setMetaToken] = useState("");
  const [userAccessTokenInput, setUserAccessTokenInput] = useState("");
  const [metaDiscoveredPages, setMetaDiscoveredPages] = useState<Array<{
    page_id: string;
    page_name: string;
    page_access_token: string;
    instagram_business_account_id?: string;
    instagram_username?: string;
    has_instagram: boolean;
  }>>([]);
  const [isDiscoveringPages, setIsDiscoveringPages] = useState(false);
  const [metaAppId, setMetaAppId] = useState("");
  const [metaLoginConfigId, setMetaLoginConfigId] = useState("");
  const [whatsappSignupConfigId, setWhatsappSignupConfigId] = useState("");

  // Shopify Form Inputs
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken] = useState("");
  const [shopifySecret, setShopifySecret] = useState("");

  // WooCommerce Form Inputs
  const [wooUrl, setWooUrl] = useState("");
  const [wooKey, setWooKey] = useState("");
  const [wooSecret, setWooSecret] = useState("");

  // Diagnostics and feedback
  const [diagnostics, setDiagnostics] = useState<Record<string, any>>({});
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Telephony Test Call State
  const [telephonyModalOpen, setTelephonyModalOpen] = useState(false);
  const [testCallPhone, setTestCallPhone] = useState("+8801712345678");
  const [testCallName, setTestCallName] = useState("Tahmid Rahman");
  const [testCallAddress, setTestCallAddress] = useState("House 42, Road 11, Banani, Dhaka");
  const [testCallItem, setTestCallItem] = useState("Silk Jamdani Panjabi (Size L)");
  const [testCallTotal, setTestCallTotal] = useState("3850");
  const [testCallResult, setTestCallResult] = useState<any>(null);
  const [isCalling, setIsCalling] = useState(false);

  // Interactive Live Widget Chat Test state
  const [widgetMessages, setWidgetMessages] = useState<Array<{ sender: "user" | "agent"; text: string }>>([
    { sender: "agent", text: "Hello! Welcome to our store. How can I help you find the right item today?" },
  ]);
  const [widgetInput, setWidgetInput] = useState("");
  const [isWidgetThinking, setIsWidgetThinking] = useState(false);
  const [currentOrigin, setCurrentOrigin] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentOrigin(window.location.origin);
    }
  }, []);

  const embedCode = `<script src="${currentOrigin || "https://joy.yourdomain.com"}/api/v1/widget/widget.js" data-tenant-id="${tenantId}" defer></script>`;

  // Fetch real integrations from PostgreSQL on load
  const loadIntegrations = async () => {
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`));
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not load saved integrations.");
      if (Array.isArray(data.integrations)) {
        setIntegrations(data.integrations);
      }
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Could not load integrations. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIntegrations();
    fetch(apiUrl("/api/auth/me"), { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const data = await response.json();
        setMetaAppId(typeof data.meta_app_id === "string" ? data.meta_app_id : "");
        setMetaLoginConfigId(typeof data.meta_login_config_id === "string" ? data.meta_login_config_id : "");
        setWhatsappSignupConfigId(
          typeof data.whatsapp_embedded_signup_config_id === "string"
            ? data.whatsapp_embedded_signup_config_id
            : ""
        );
      })
      .catch(() => {
        setMetaAppId("");
        setMetaLoginConfigId("");
        setWhatsappSignupConfigId("");
      });
  }, [tenantId]);

  const copyEmbedCode = () => {
    navigator.clipboard.writeText(embedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Helper to find integration by provider
  const getIntegration = (provider: string) => integrations.find((i) => i.provider === provider && i.is_active);

  // Facebook Login for Business uses the Meta Dashboard configuration rather than a raw scope list.
  const handleLaunchMetaLogin = async () => {
    if (!metaAppId || !metaLoginConfigId) {
      setActionStatus("Meta sign-in needs META_APP_ID and META_LOGIN_CONFIG_ID configured on the server.");
      return;
    }
    setActionStatus(null);
    setIsDiscoveringPages(true);
    try {
      const sdk = await loadMetaSdk(metaAppId);
      sdk.login((response) => {
        const accessToken = response.authResponse?.accessToken;
        if (!accessToken) {
          setIsDiscoveringPages(false);
          setActionStatus("Meta login was cancelled or did not return a user access token.");
          return;
        }
        void handleExchangeUserToken(accessToken);
      }, { config_id: metaLoginConfigId });
    } catch (error) {
      setIsDiscoveringPages(false);
      setActionStatus(error instanceof Error ? error.message : "Could not start Meta login.");
    }
  };

  const exchangeMetaCredential = async (credential: { code?: string; access_token?: string }) => {
    setIsDiscoveringPages(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations/meta/oauth-exchange`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credential),
      });
      const data = await res.json();
      if (res.ok && data.pages) {
        setMetaDiscoveredPages(data.pages);
        if (data.pages.length === 0) {
          setActionStatus("No Facebook Pages were returned. Check the selected Meta assets and use a User access token configuration for Page discovery.");
        }
      } else {
        setActionStatus(data.detail || "Failed to discover Facebook Pages.");
      }
    } catch (err: any) {
      setActionStatus("Error contacting JOY Meta authorization: " + err.message);
    } finally {
      setIsDiscoveringPages(false);
    }
  };
  const handleExchangeUserToken = (token: string) => exchangeMetaCredential({ access_token: token });

  // Select a discovered Facebook Page to connect & encrypt
  const handleSelectPage = async (page: any) => {
    setIsSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations/meta/select-page`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: page.page_id,
          page_name: page.page_name,
          page_access_token: page.page_access_token,
          instagram_account_id: page.instagram_business_account_id,
          instagram_username: page.instagram_username,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setActionStatus(`Facebook Page '${page.page_name}' connected & encrypted with AES-256!`);
        setMetaModalOpen(false);
        setMetaDiscoveredPages([]);
        loadIntegrations();
      } else {
        alert(data.detail || "Failed to connect selected page.");
      }
    } catch (err: any) {
      alert("Error saving selected page: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Sandbox simulation of Facebook Login for local development
  const handleSimulateOAuth = async () => {
    setIsDiscoveringPages(true);
    setTimeout(() => {
      setMetaDiscoveredPages([
        {
          page_id: "102938475620192",
          page_name: "Joy Luxury Boutique",
          page_access_token: "EAAG_simulated_token_" + Math.random().toString(36).substring(2, 10),
          instagram_business_account_id: "17841400012345678",
          instagram_username: "joy_luxury_official",
          has_instagram: true,
        },
        {
          page_id: "998877665544332",
          page_name: "Joy Customer Support",
          page_access_token: "EAAG_simulated_token_" + Math.random().toString(36).substring(2, 10),
          instagram_business_account_id: undefined,
          instagram_username: undefined,
          has_instagram: false,
        },
      ]);
      setIsDiscoveringPages(false);
    }, 600);
  };

  // Connect Meta Handler (Manual)
  const handleConnectMeta = async () => {
    if (!metaToken.trim()) {
      alert("Please enter your real Meta Page Access Token and Page ID.");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "meta",
          access_token: metaToken,
          settings: {
            page_name: metaPageName,
            page_id: metaPageId,
            instagram_account_id: metaIgId,
            permissions_granted: ["instagram_manage_messages", "pages_messaging", "pages_read_engagement"],
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Meta connection failed.");
      if (res.ok) {
        setActionStatus(data.message);
        setMetaModalOpen(false);
        setMetaToken("");
        loadIntegrations();
      }
    } catch (err: any) {
      alert("Connection error: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Connect Shopify Handler
  const handleConnectShopify = async () => {
    if (!shopifyToken.trim()) {
      alert("Please enter your Shopify Admin API Access Token.");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "shopify",
          access_token: shopifyToken,
          settings: {
            shop_domain: shopifyDomain,
            webhook_secret: shopifySecret,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Shopify credentials could not be saved.");
      if (res.ok) {
        setActionStatus(data.message);
        setShopifyModalOpen(false);
        setShopifyToken("");
        loadIntegrations();
      }
    } catch (err: any) {
      alert("Connection error: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Connect WooCommerce Handler
  const handleConnectWoo = async () => {
    if (!wooKey.trim() || !wooSecret.trim()) {
      alert("Please enter both Consumer Key and Consumer Secret.");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "woocommerce",
          access_token: wooSecret,
          settings: {
            store_url: wooUrl,
            consumer_key: wooKey,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "WooCommerce credentials could not be saved.");
      if (res.ok) {
        setActionStatus(data.message);
        setWooModalOpen(false);
        setWooKey("");
        setWooSecret("");
        loadIntegrations();
      }
    } catch (err: any) {
      alert("Connection error: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Disconnect Handler
  const handleDisconnect = async (provider: string) => {
    if (!confirm(`Are you sure you want to disconnect ${provider.toUpperCase()}?`)) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations/${provider}`), {
        method: "DELETE",
      });
      if (res.ok) {
        setActionStatus(`Disconnected ${provider.toUpperCase()} successfully.`);
        loadIntegrations();
      } else throw new Error((await res.json()).detail || "Disconnect failed.");
    } catch (err: any) {
      alert("Disconnect error: " + err.message);
    }
  };

  // Test Connection Diagnostics
  const handleTestConnection = async (provider: string) => {
    try {
      setDiagnostics((prev) => ({ ...prev, [provider]: "Testing connection..." }));
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations/${provider}/test`), {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Provider verification failed.");
      setDiagnostics((prev) => ({ ...prev, [provider]: data }));
    } catch (err: any) {
      setDiagnostics((prev) => ({ ...prev, [provider]: { status: "error", message: err.message } }));
    }
  };

  // Trigger Outbound Phone Call via Amber IT PABX & LiveKit WebRTC
  const handleTriggerTestCall = async () => {
    setIsCalling(true);
    setTestCallResult(null);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/telephony/test-call`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_phone: testCallPhone,
          customer_name: testCallName,
          shipping_address: testCallAddress,
          order_items: testCallItem,
          order_total: parseFloat(testCallTotal) || 3850.00,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.status !== "success" || data.dispatch?.status !== "initiated") {
        throw new Error(data.detail || data.message || "The provider did not confirm call dispatch.");
      }
      setTestCallResult(data);
      setActionStatus("The calling provider confirmed dispatch.");
    } catch (err: any) {
      alert("Call dispatch error: " + err.message);
    } finally {
      setIsCalling(false);
    }
  };

  // Live Interactive Widget Chat Send
  const handleSendWidgetChat = async () => {
    if (!widgetInput.trim() || isWidgetThinking) return;
    const userText = widgetInput.trim();
    setWidgetMessages((prev) => [...prev, { sender: "user", text: userText }]);
    setWidgetInput("");
    setIsWidgetThinking(true);

    try {
      let session = widgetSession.current;
      if (!session) {
      const sessionResponse = await fetch(apiUrl("/api/v1/widget/session"), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({tenant_id: tenantId})
      });
      const created = await sessionResponse.json();
      if (!sessionResponse.ok) throw new Error(created.detail || "Widget session failed.");
      widgetSession.current = created;
      session = created;
      }
      if (!session) throw new Error("Widget session unavailable.");
      const res = await fetch(apiUrl("/api/v1/widget/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          session_id: `preview_widget_${Date.now()}`,
          customer_id: session.customer_id,
          visitor_token: session.token,
          request_id: crypto.randomUUID(),
          message: userText,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Widget request failed.");
      setWidgetMessages((prev) => [
        ...prev,
        {
          sender: "agent",
          text: data.reply || "The specialist is paused or unavailable. Please contact the store.",
        },
      ]);
    } catch (e: any) {
      setWidgetMessages((prev) => [
        ...prev,
        { sender: "agent", text: "Connection error: Could not contact Employee #1 API." },
      ]);
    } finally {
      setIsWidgetThinking(false);
    }
  };

  const metaInt = getIntegration("meta");
  const shopifyInt = getIntegration("shopify");
  const wooInt = getIntegration("woocommerce");

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 text-xs font-semibold mb-2">
          <span>Step 1 of 4</span>
          <span>&bull;</span>
          <span>Live Sales &amp; Messaging Connections</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Store Connections (Integration Hub)
        </h1>
        <p className="text-sm text-muted mt-1">
          Connect your social messaging channels and storefront APIs. Tokens are encrypted with AES-256 and stored in your dedicated database partition.
        </p>
      </div>

      {/* Global Status Notification */}
      {actionStatus && (
        <div role="status" className="p-3.5 bg-surface border border-border rounded-xl text-xs text-foreground flex items-center justify-between animate-in slide-in-from-top-1">
          <div className="flex items-center gap-2">
            <Info className="w-4 h-4 text-muted flex-shrink-0" />
            <span className="font-semibold">{actionStatus}</span>
          </div>
          <button onClick={() => setActionStatus(null)} className="text-brand-700 hover:text-brand-900 text-xs font-bold">
            ✕
          </button>
        </div>
      )}

      {/* Integration Channels Grid */}
      <WidgetOriginSettings />
          <WhatsAppConnection
            metaAppId={metaAppId}
            signupConfigId={whatsappSignupConfigId}
          />
      <OperationalStatus />
      <PrivacyRequests />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* ========================================== */}
        {/* 1. Meta / Instagram & Facebook             */}
        {/* ========================================== */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm hover:border-foreground/30 transition-all flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
                <Share2 className="w-5 h-5 text-foreground" />
              </div>
              {metaInt ? (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                  Page authorized
                </span>
              ) : (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-surface text-muted border border-border">
                  Not Connected
                </span>
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold text-foreground">Meta Business Suite</h3>
              <p className="text-xs text-muted mt-1">
                Authorize your Facebook Page and connected Instagram professional account.
              </p>
            </div>

            {metaInt ? (
              <div className="space-y-2 bg-surface p-3.5 rounded-lg border border-border text-xs">
                <div className="flex items-center justify-between text-muted">
                  <span>Page:</span>
                  <span className="font-semibold text-foreground">{metaInt.settings.page_name || "Official Page"}</span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Token:</span>
                  <span className="font-mono text-foreground">{metaInt.masked_token}</span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Encryption:</span>
                  <span className="font-semibold text-brand-700 flex items-center gap-1">
                    <Lock className="w-3 h-3 text-brand-600" /> AES-256 Vault
                  </span>
                </div>

                <IntegrationDiagnostic result={diagnostics["meta"]} />
              </div>
            ) : (
              <div className="p-3 bg-surface rounded-lg border border-border text-xs text-muted">
                Connect your Meta Page to verify API access and authorize webhook subscriptions.
              </div>
            )}
            <p className="text-[11px] leading-relaxed text-amber-800">
              Supported inbound messages are routed to the Social Sales agent when the webhook fields,
              permissions, and agent are enabled. Live delivery and replies still require an end-to-end
              test with a real Meta Page.
            </p>
          </div>

          <div className="pt-4 border-t border-border mt-4 flex items-center gap-2">
            {metaInt ? (
              <>
                <button
                  onClick={() => handleTestConnection("meta")}
                  className="flex-1 py-2 px-3 bg-surface hover:bg-surface-hover border border-border text-foreground rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <Activity className="w-3.5 h-3.5 text-brand-600" />
                  <span>Test Connection</span>
                </button>
                <button
                  onClick={() => handleDisconnect("meta")}
                  className="p-2 text-muted hover:text-alert border border-border hover:border-alert/40 rounded-lg transition-colors"
                  title="Disconnect Meta"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </>
            ) : (
              <button
                onClick={() => setMetaModalOpen(true)}
                className="w-full py-2 px-4 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm flex items-center justify-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Connect Meta Suite</span>
              </button>
            )}
          </div>
        </div>

        {/* ========================================== */}
        {/* 2. Shopify Storefront                      */}
        {/* ========================================== */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm hover:border-foreground/30 transition-all flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
                <ShoppingBag className="w-5 h-5 text-foreground" />
              </div>
              {shopifyInt ? (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                  Credentials saved
                </span>
              ) : (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-surface text-muted border border-border">
                  Not Connected
                </span>
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold text-foreground">Shopify Storefront</h3>
              <p className="text-xs text-muted mt-1">
                Sync product catalogs and dispatch automated outbound phone confirmation calls (Employee #2).
              </p>
            </div>

            {shopifyInt ? (
              <div className="space-y-2 bg-surface p-3.5 rounded-lg border border-border text-xs">
                <div className="flex items-center justify-between text-muted">
                  <span>Store Domain:</span>
                  <span className="font-semibold text-foreground">{shopifyInt.settings.shop_domain || "myshopify.com"}</span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Webhook URL:</span>
                  <span className="font-mono text-[11px] text-foreground truncate max-w-[150px]">
                    /api/v1/webhooks/shopify
                  </span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Security:</span>
                  <span className="font-semibold text-brand-700 flex items-center gap-1">
                    <Lock className="w-3 h-3 text-brand-600" /> HMAC-SHA256
                  </span>
                </div>

                <IntegrationDiagnostic result={diagnostics["shopify"]} />
              </div>
            ) : (
              <div className="p-3 bg-surface rounded-lg border border-border text-xs text-muted">
                Connect Shopify to trigger outbound phone confirmation calls whenever a customer orders.
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-border mt-4 flex items-center gap-2">
            {shopifyInt ? (
              <>
                <button
                  onClick={() => handleTestConnection("shopify")}
                  className="flex-1 py-2 px-3 bg-surface hover:bg-surface-hover border border-border text-foreground rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <Activity className="w-3.5 h-3.5 text-brand-600" />
                  <span>Verify Webhook</span>
                </button>
                <button
                  onClick={() => handleDisconnect("shopify")}
                  className="p-2 text-muted hover:text-alert border border-border hover:border-alert/40 rounded-lg transition-colors"
                  title="Disconnect Shopify"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </>
            ) : (
              <button
                onClick={() => setShopifyModalOpen(true)}
                className="w-full py-2 px-4 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm flex items-center justify-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Connect Shopify Store</span>
              </button>
            )}
          </div>
        </div>

        {/* ========================================== */}
        {/* 3. WooCommerce Store                       */}
        {/* ========================================== */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm hover:border-foreground/30 transition-all flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
                <Store className="w-5 h-5 text-foreground" />
              </div>
              {wooInt ? (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                  Credentials saved
                </span>
              ) : (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-surface text-muted border border-border">
                  Not Connected
                </span>
              )}
            </div>

            <div>
              <h3 className="text-base font-semibold text-foreground">WooCommerce Store</h3>
              <p className="text-xs text-muted mt-1">
                Synchronize self-hosted WordPress/WooCommerce product catalogs and automated phone order confirmation.
              </p>
            </div>

            {wooInt ? (
              <div className="space-y-2 bg-surface p-3.5 rounded-lg border border-border text-xs">
                <div className="flex items-center justify-between text-muted">
                  <span>Store URL:</span>
                  <span className="font-semibold text-foreground truncate max-w-[150px]">{wooInt.settings.store_url}</span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Webhook Topic:</span>
                  <span className="font-mono text-foreground">woocommerce_new_order</span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Credentials:</span>
                  <span className="font-semibold text-brand-700 flex items-center gap-1">
                    <Lock className="w-3 h-3 text-brand-600" /> AES-256
                  </span>
                </div>

                <IntegrationDiagnostic result={diagnostics["woocommerce"]} />
              </div>
            ) : (
              <div className="p-3 bg-surface rounded-lg border border-border text-xs text-muted">
                Connect your WordPress/WooCommerce site via REST API Keys for automated inventory and phone confirmation.
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-border mt-4 flex items-center gap-2">
            {wooInt ? (
              <>
                <button
                  onClick={() => handleTestConnection("woocommerce")}
                  className="flex-1 py-2 px-3 bg-surface hover:bg-surface-hover border border-border text-foreground rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <Activity className="w-3.5 h-3.5 text-brand-600" />
                  <span>Test API Ping</span>
                </button>
                <button
                  onClick={() => handleDisconnect("woocommerce")}
                  className="p-2 text-muted hover:text-alert border border-border hover:border-alert/40 rounded-lg transition-colors"
                  title="Disconnect WooCommerce"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </>
            ) : (
              <button
                onClick={() => setWooModalOpen(true)}
                className="w-full py-2 px-4 bg-foreground hover:bg-foreground/90 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm flex items-center justify-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Connect WooCommerce Store</span>
              </button>
            )}
          </div>
        </div>

        {/* ========================================== */}
        {/* 4. Amber IT Telephony & LiveKit Voice Hub  */}
        {/* ========================================== */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm hover:border-foreground/30 transition-all flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
                <PhoneCall className="w-5 h-5 text-foreground" />
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                Setup required
              </span>
            </div>

            <div>
              <h3 className="text-base font-semibold text-foreground">Amber IT &amp; LiveKit Voice</h3>
              <p className="text-xs text-muted mt-1">
                Bangladeshi PABX SIP telephony &amp; LiveKit WebRTC streaming for Employee #2 (Voice Confirmation).
              </p>
            </div>

            <div className="space-y-2 bg-surface p-3.5 rounded-lg border border-border text-xs">
              <p className="text-muted leading-relaxed">
                Calls are disabled until a compatible AmberIT SIP trunk, LiveKit SIP dialing,
                and a running voice-agent worker are connected and tested.
                A reachable LiveKit room does not verify outbound calling.
              </p>
              <IntegrationDiagnostic result={diagnostics["telephony"]} />
            </div>
          </div>

          <div className="pt-4 border-t border-border mt-4 flex items-center gap-2">
            <button
              onClick={() => handleTestConnection("telephony")}
              className="flex-1 py-2 px-3 bg-surface hover:bg-surface-hover border border-border text-foreground rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
            >
              <Activity className="w-3.5 h-3.5 text-brand-600" />
              <span>Check configuration</span>
            </button>
            <button
              onClick={() => setTelephonyModalOpen(true)}
              className="py-2 px-3 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm flex items-center justify-center gap-1.5"
            >
              <PhoneForwarded className="w-3.5 h-3.5" />
              <span>Setup details</span>
            </button>
          </div>
        </div>
      </div>

      {/* ========================================== */}
      {/* Universal Web Chat Embed Widget            */}
      {/* ========================================== */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
              <Code2 className="w-5 h-5 text-foreground" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-foreground">Universal Web Chat Embed Widget</h3>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                  Embed code available
                </span>
              </div>
              <p className="text-xs text-muted mt-0.5">
                Paste this single script tag right before <code className="text-foreground font-mono">&lt;/body&gt;</code> on any custom website, Wix, Webflow, or WordPress site.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setWidgetPreviewOpen(true)}
              className="px-3.5 py-1.5 rounded-lg bg-brand-50 hover:bg-brand-100 text-brand-800 border border-brand-200 text-xs font-semibold transition-colors flex items-center gap-1.5"
            >
              <MessageSquare className="w-3.5 h-3.5 text-brand-600" />
              <span>Test Live Web Widget</span>
            </button>
            <button
              onClick={copyEmbedCode}
              className="px-3.5 py-1.5 rounded-lg bg-foreground text-white hover:bg-foreground/90 text-xs font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-brand-400" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Snippet</span>
                </>
              )}
            </button>
          </div>
        </div>

        <div className="relative">
          <pre className="p-4 rounded-lg bg-surface border border-border text-xs font-mono text-foreground overflow-x-auto selection:bg-brand-100">
            {embedCode}
          </pre>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-muted">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
            <span>Zero external dependencies (&lt;12KB)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
            <span>Pure white minimal design (zero blue/purple)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
            <span>Real-time catalog lookup &amp; discount codes</span>
          </div>
        </div>
      </div>

      {/* Workflow Navigation Footer */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-600" />
            <h3 className="text-sm font-bold text-foreground">Step 1 Complete: Sales Channels Connected</h3>
          </div>
          <p className="text-xs text-muted mt-0.5">
            Next, upload your product catalog or crawl your website so Employee #1 &amp; #2 know your stock, prices, and return policies.
          </p>
        </div>
        <Link
          href="/dashboard/knowledge-brain"
          className="px-5 py-2.5 rounded-lg bg-brand-600 text-white font-semibold text-xs hover:bg-brand-700 transition-colors shadow-sm flex items-center gap-1.5"
        >
          <span>Proceed to Step 2: Train Digital Brain</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* ========================================== */}
      {/* MODAL 1: Connect Meta Suite                */}
      {/* ========================================== */}
      {metaModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-foreground">Connect Meta Business Suite</h3>
                  {metaAppId && (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                      App: {metaAppId}
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted mt-0.5">
                  Link your Facebook Page and Instagram Professional Account. Credentials are encrypted with AES-256 before storing.
                </p>
              </div>
              <button onClick={() => setMetaModalOpen(false)} className="text-muted hover:text-foreground p-1">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Tab Switcher */}
            <div className="flex items-center bg-surface p-1 rounded-lg border border-border text-xs">
              <button
                type="button"
                onClick={() => setMetaTab("oauth")}
                className={`flex-1 py-1.5 px-3 rounded-md font-semibold transition-all ${
                  metaTab === "oauth" ? "bg-white text-foreground shadow-sm" : "text-muted hover:text-foreground"
                }`}
              >
                  Facebook Login for Business
              </button>
              <button
                type="button"
                onClick={() => setMetaTab("manual")}
                className={`flex-1 py-1.5 px-3 rounded-md font-semibold transition-all ${
                  metaTab === "manual" ? "bg-white text-foreground shadow-sm" : "text-muted hover:text-foreground"
                }`}
              >
                Manual Token &amp; IDs
              </button>
            </div>

            {metaTab === "oauth" ? (
              <div className="space-y-4">
                <div className="p-4 bg-gradient-to-br from-blue-50/50 to-indigo-50/50 rounded-xl border border-blue-100 text-center space-y-3">
                  <div className="w-10 h-10 rounded-full bg-[#1877F2] text-white flex items-center justify-center mx-auto shadow-sm">
                    <Share2 className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-foreground">Meta Business Login</h4>
                    <p className="text-[11px] text-muted max-w-sm mx-auto mt-0.5">
                      Authorize the Pages and connected Instagram accounts selected in JOY’s Meta Business Login user-token configuration.
                    </p>
                  </div>

                  <div className="flex flex-col gap-2 pt-1">
                    <button
                      type="button"
                      onClick={handleLaunchMetaLogin}
                      disabled={isDiscoveringPages || !metaAppId || !metaLoginConfigId}
                      className="w-full py-2.5 px-4 bg-[#1877F2] hover:bg-[#166fe5] disabled:cursor-not-allowed disabled:opacity-50 text-white font-semibold rounded-lg text-xs transition-colors shadow-sm flex items-center justify-center gap-2"
                    >
                      <Share2 className="w-4 h-4" />
                      <span>{isDiscoveringPages ? "Waiting for Meta authorization..." : "Continue with Facebook"}</span>
                    </button>
                    {(!metaAppId || !metaLoginConfigId) && (
                      <p className="text-[11px] text-muted">
                        Meta sign-in needs the server’s Meta app ID and Business Login configuration ID. Set
                        META_APP_ID and META_LOGIN_CONFIG_ID after creating a User access token configuration in Meta.
                      </p>
                    )}

                    {import.meta.env.DEV && <button
                      type="button"
                      onClick={handleSimulateOAuth}
                      disabled={isDiscoveringPages}
                      className="text-[11px] font-semibold text-brand-700 hover:text-brand-900 py-1"
                    >
                      ⚡ Quick Test with Simulated OAuth Sandbox
                    </button>}
                  </div>
                </div>

                {/* Direct User Token Discovery Option */}
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold text-muted">Or paste User Access Token to discover pages:</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={userAccessTokenInput}
                      onChange={(e) => setUserAccessTokenInput(e.target.value)}
                      placeholder="Paste User Token (EAAG...)"
                      className="flex-1 px-3 py-1.5 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => handleExchangeUserToken(userAccessTokenInput)}
                      disabled={!userAccessTokenInput || isDiscoveringPages}
                      className="px-3 py-1.5 bg-surface hover:bg-surface-hover border border-border text-foreground font-semibold text-xs rounded-lg transition-colors"
                    >
                      Discover
                    </button>
                  </div>
                </div>

                {/* Discovered Pages List */}
                {metaDiscoveredPages.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-border">
                    <label className="text-xs font-bold text-foreground">Select Facebook Page to Connect:</label>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {metaDiscoveredPages.map((page) => (
                        <div
                          key={page.page_id}
                          className="p-3 bg-surface hover:bg-surface-hover/80 rounded-xl border border-border flex items-center justify-between transition-colors"
                        >
                          <div>
                            <div className="font-bold text-xs text-foreground">{page.page_name}</div>
                            <div className="text-[11px] text-muted flex items-center gap-2 mt-0.5">
                              <span>Page ID: {page.page_id}</span>
                              {page.has_instagram && (
                                <span className="px-1.5 py-0.5 rounded bg-pink-50 text-pink-700 border border-pink-200 text-[10px] font-medium">
                                  IG: @{page.instagram_username || page.instagram_business_account_id}
                                </span>
                              )}
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleSelectPage(page)}
                            disabled={isSubmitting}
                            className="px-3 py-1.5 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors"
                          >
                            {isSubmitting ? "Connecting..." : "Connect Page"}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3.5">
                <div>
                  <label className="text-xs font-semibold text-foreground">Facebook Page Name</label>
                  <input
                    type="text"
                    value={metaPageName}
                    onChange={(e) => setMetaPageName(e.target.value)}
                    placeholder="e.g. Joy Luxury Boutique"
                    className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-foreground">Facebook Page ID</label>
                    <input
                      type="text"
                      value={metaPageId}
                      onChange={(e) => setMetaPageId(e.target.value)}
                      placeholder="e.g. 102938475620"
                      className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-foreground">Instagram Account ID</label>
                    <input
                      type="text"
                      value={metaIgId}
                      onChange={(e) => setMetaIgId(e.target.value)}
                      placeholder="e.g. 178414000123"
                      className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-foreground">Page Access Token (User / System Token)</label>
                    {import.meta.env.DEV && <button
                      type="button"
                      onClick={() => setMetaToken("EAAGtest_sandbox_token_" + Math.random().toString(36).substring(2, 12))}
                      className="text-[11px] font-semibold text-brand-700 hover:text-brand-900"
                    >
                      + Prefill Verified Sandbox Token
                    </button>}
                  </div>
                  <textarea
                    value={metaToken}
                    onChange={(e) => setMetaToken(e.target.value)}
                    rows={3}
                    placeholder="Paste your EAAG... permanent Page Access Token here"
                    className="w-full mt-1 p-2.5 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                  />
                </div>
              </div>
            )}

            <div className="p-3 bg-surface rounded-xl border border-border text-[11px] text-muted space-y-1">
              <div className="font-semibold text-foreground flex items-center gap-1">
                <Shield className="w-3.5 h-3.5 text-brand-600" /> Envelope Encryption Guarantee
              </div>
              <p>
                Tokens are never stored in plaintext. They are encrypted using Fernet AES-256 authenticated encryption before being saved to PostgreSQL.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
              <button
                onClick={() => setMetaModalOpen(false)}
                className="px-3.5 py-1.5 text-xs text-muted hover:text-foreground font-medium"
              >
                Cancel
              </button>
              {metaTab === "manual" && (
                <button
                  onClick={handleConnectMeta}
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors shadow-sm"
                >
                  {isSubmitting ? "Encrypting & Saving..." : "Encrypt & Save Connection"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================== */}
      {/* MODAL 2: Connect Shopify Storefront        */}
      {/* ========================================== */}
      {shopifyModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Connect Shopify Storefront</h3>
                <p className="text-xs text-muted mt-0.5">
                  Link your Shopify store to receive real-time <code className="text-foreground">orders/create</code> webhooks.
                </p>
              </div>
              <button onClick={() => setShopifyModalOpen(false)} className="text-muted hover:text-foreground p-1">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="text-xs font-semibold text-foreground">Shopify Domain</label>
                <input
                  type="text"
                  value={shopifyDomain}
                  onChange={(e) => setShopifyDomain(e.target.value)}
                  placeholder="e.g. my-store.myshopify.com"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-foreground">Admin API Access Token</label>
                  {import.meta.env.DEV && <button
                    type="button"
                    onClick={() => {
                      setShopifyToken("shpat_test_token_" + Math.random().toString(36).substring(2, 12));
                      setShopifySecret("shpss_secret_" + Math.random().toString(36).substring(2, 10));
                    }}
                    className="text-[11px] font-semibold text-brand-700 hover:text-brand-900"
                  >
                    + Prefill Verified Sandbox Credentials
                  </button>}
                </div>
                <input
                  type="password"
                  value={shopifyToken}
                  onChange={(e) => setShopifyToken(e.target.value)}
                  placeholder="shpat_••••••••••••••••••••••••"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Webhook HMAC Signing Secret</label>
                <input
                  type="password"
                  value={shopifySecret}
                  onChange={(e) => setShopifySecret(e.target.value)}
                  placeholder="Found under Shopify Admin > Notifications > Webhooks"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div className="p-3 bg-surface rounded-xl border border-border text-[11px] text-muted space-y-1">
                <div className="font-semibold text-foreground">Webhook Ingestion Endpoint</div>
                <p className="font-mono text-foreground select-all bg-white p-1.5 rounded border border-border">
                  {currentOrigin || "https://joy.yourdomain.com"}/api/v1/webhooks/shopify/{tenantId}
                </p>
                <p>FastAPI validates incoming payloads against your HMAC secret and deduplicates events in Redis.</p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
              <button
                onClick={() => setShopifyModalOpen(false)}
                className="px-3.5 py-1.5 text-xs text-muted hover:text-foreground font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleConnectShopify}
                disabled={isSubmitting}
                className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors shadow-sm"
              >
                {isSubmitting ? "Saving..." : "Verify & Save Shopify"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================== */}
      {/* MODAL 3: Connect WooCommerce Store         */}
      {/* ========================================== */}
      {wooModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Connect WooCommerce Store</h3>
                <p className="text-xs text-muted mt-0.5">
                  Connect self-hosted WordPress/WooCommerce using standard REST API keys.
                </p>
              </div>
              <button onClick={() => setWooModalOpen(false)} className="text-muted hover:text-foreground p-1">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="text-xs font-semibold text-foreground">Store Website URL</label>
                <input
                  type="text"
                  value={wooUrl}
                  onChange={(e) => setWooUrl(e.target.value)}
                  placeholder="https://yourstore.com"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-foreground">Consumer Key (Read/Write)</label>
                  {import.meta.env.DEV && <button
                    type="button"
                    onClick={() => {
                      setWooKey("ck_test_" + Math.random().toString(36).substring(2, 12));
                      setWooSecret("cs_test_" + Math.random().toString(36).substring(2, 12));
                    }}
                    className="text-[11px] font-semibold text-brand-700 hover:text-brand-900"
                  >
                    + Prefill Verified Sandbox Keys
                  </button>}
                </div>
                <input
                  type="text"
                  value={wooKey}
                  onChange={(e) => setWooKey(e.target.value)}
                  placeholder="ck_••••••••••••••••••••••••"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Consumer Secret</label>
                <input
                  type="password"
                  value={wooSecret}
                  onChange={(e) => setWooSecret(e.target.value)}
                  placeholder="cs_••••••••••••••••••••••••"
                  className="w-full mt-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
              <button
                onClick={() => setWooModalOpen(false)}
                className="px-3.5 py-1.5 text-xs text-muted hover:text-foreground font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleConnectWoo}
                disabled={isSubmitting}
                className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors shadow-sm"
              >
                {isSubmitting ? "Connecting..." : "Save WooCommerce Credentials"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================== */}
      {/* MODAL 4: Interactive Live Web Widget Chat  */}
      {/* ========================================== */}
      {widgetPreviewOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-end p-4 sm:p-6">
          <div className="bg-white border border-border rounded-2xl w-full max-w-sm h-[560px] shadow-2xl flex flex-col justify-between overflow-hidden animate-in slide-in-from-right-4 duration-200">
            {/* Widget Top Bar */}
            <div className="p-4 bg-foreground text-white flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-white font-bold text-xs">
                  JOY
                </div>
                <div>
                  <h4 className="text-xs font-bold">Store Sales Assistant</h4>
                  <p className="text-[10px] text-zinc-300 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" /> Employee #1 Online
                  </p>
                </div>
              </div>
              <button
                onClick={() => setWidgetPreviewOpen(false)}
                className="text-zinc-300 hover:text-white p-1 text-sm"
              >
                ✕
              </button>
            </div>

            {/* Widget Message Stream */}
            <div className="p-4 flex-1 overflow-y-auto space-y-3 bg-surface">
              {widgetMessages.map((m, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`max-w-[85%] p-3 rounded-2xl text-xs leading-relaxed ${
                      m.sender === "user"
                        ? "bg-foreground text-white rounded-br-sm"
                        : "bg-white text-foreground border border-border rounded-bl-sm shadow-sm"
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))}
              {isWidgetThinking && (
                <div className="flex items-center gap-1.5 text-xs text-muted bg-white p-2.5 rounded-xl border border-border w-fit">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce" />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce [animation-delay:0.2s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-bounce [animation-delay:0.4s]" />
                  <span className="text-[10px] ml-1">Searching store catalog...</span>
                </div>
              )}
            </div>

            {/* Widget Quick Suggestions */}
            <div className="px-3 py-1.5 bg-white border-t border-border flex items-center gap-1.5 overflow-x-auto text-[10px]">
              <button
                onClick={() => {
                  setWidgetInput("Do you have Mulberry silk Panjabi in stock?");
                }}
                className="px-2.5 py-1 rounded-full bg-surface hover:bg-surface-hover text-muted hover:text-foreground border border-border whitespace-nowrap"
              >
                Silk Panjabi inquiry
              </button>
              <button
                onClick={() => {
                  setWidgetInput("What is your Dhaka delivery and return policy?");
                }}
                className="px-2.5 py-1 rounded-full bg-surface hover:bg-surface-hover text-muted hover:text-foreground border border-border whitespace-nowrap"
              >
                Delivery policy
              </button>
            </div>

            {/* Widget Input */}
            <div className="p-3 bg-white border-t border-border flex items-center gap-2">
              <input
                type="text"
                value={widgetInput}
                onChange={(e) => setWidgetInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendWidgetChat()}
                placeholder="Ask about products, sizes, prices..."
                className="flex-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
              />
              <button
                onClick={handleSendWidgetChat}
                disabled={!widgetInput.trim() || isWidgetThinking}
                className="p-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-40 text-white rounded-lg transition-colors shadow-sm"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================== */}
      {/* Telephony Outbound Call Test Modal         */}
      {/* ========================================== */}
      {telephonyModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-lg w-full border border-border shadow-2xl overflow-hidden animate-in zoom-in-95">
            <div className="p-6 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center">
                  <PhoneCall className="w-5 h-5 text-brand-600" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Outbound Voice Confirmation Test</h3>
                  <p className="text-xs text-muted">Amber IT PABX Bangladesh &bull; LiveKit Cloud WebRTC</p>
                </div>
              </div>
              <button
                onClick={() => setTelephonyModalOpen(false)}
                className="w-8 h-8 rounded-lg hover:bg-surface text-muted hover:text-foreground flex items-center justify-center text-sm"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto text-xs">
              <div role="status" className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 leading-relaxed">
                Calling is not enabled. Confirm AmberIT trunk compatibility, connect it to
                LiveKit SIP, and deploy a voice-agent worker before testing.
                This form cannot currently dispatch a call.
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-foreground mb-1">
                    Customer Phone Number
                  </label>
                  <input
                    type="text"
                    value={testCallPhone}
                    onChange={(e) => setTestCallPhone(e.target.value)}
                    placeholder="+8801712345678"
                    className="w-full px-3 py-2 text-xs bg-surface border border-border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-foreground"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">
                      Customer Name
                    </label>
                    <input
                      type="text"
                      value={testCallName}
                      onChange={(e) => setTestCallName(e.target.value)}
                      className="w-full px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">
                      Order Total (BDT)
                    </label>
                    <input
                      type="number"
                      value={testCallTotal}
                      onChange={(e) => setTestCallTotal(e.target.value)}
                      className="w-full px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-foreground mb-1">
                    Order Items
                  </label>
                  <input
                    type="text"
                    value={testCallItem}
                    onChange={(e) => setTestCallItem(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-foreground mb-1">
                    Delivery Address
                  </label>
                  <input
                    type="text"
                    value={testCallAddress}
                    onChange={(e) => setTestCallAddress(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                  />
                </div>
              </div>

              {testCallResult && (
                <div className="p-4 bg-brand-50 border border-brand-200 rounded-xl space-y-2 animate-in fade-in">
                  <div className="flex items-center gap-2 text-brand-900 font-bold">
                    <CheckCircle2 className="w-4 h-4 text-brand-600" />
                    <span>Call Successfully Dispatched!</span>
                  </div>
                  <div className="text-[11px] space-y-1 text-brand-800">
                    <div><strong>Call ID:</strong> <span className="font-mono">{testCallResult.dispatch?.call_id}</span></div>
                    <div><strong>LiveKit Room:</strong> <span className="font-mono">{testCallResult.dispatch?.room_name}</span></div>
                    <div><strong>Caller ID:</strong> <span className="font-mono">{testCallResult.dispatch?.sip_caller_id}</span></div>
                    <div><strong>Order ID:</strong> <span className="font-mono">{testCallResult.order_id}</span></div>
                    <div><strong>Status:</strong> Dispatched to LiveKit WebRTC Streaming Engine</div>
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 bg-surface border-t border-border flex items-center justify-end gap-3">
              <button
                onClick={() => setTelephonyModalOpen(false)}
                className="py-2 px-4 rounded-lg border border-border text-xs font-medium hover:bg-surface-hover transition-colors"
              >
                Close
              </button>
              <button
                onClick={handleTriggerTestCall}
                disabled
                className="py-2 px-4 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-xs font-semibold transition-colors shadow-sm flex items-center gap-1.5"
              >
                <PhoneForwarded className="w-3.5 h-3.5" />
                <span>Calling unavailable — setup required</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
