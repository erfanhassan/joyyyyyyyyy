import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";
import { loadMetaSdk } from "@/lib/meta-sdk";

interface WhatsAppConnectionProps {
  metaAppId: string;
  signupConfigId: string;
}

interface SignupAssets {
  waba_id?: string;
  phone_number_id?: string;
}

export function WhatsAppConnection({ metaAppId, signupConfigId }: WhatsAppConnectionProps) {
  const { tenantId, refetchTenant } = useTenant();
  const [waba, setWaba] = useState("");
  const [phone, setPhone] = useState("");
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [needsReconnect, setNeedsReconnect] = useState(false);
  const [attentionChannel, setAttentionChannel] = useState("WhatsApp");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [signupAvailable, setSignupAvailable] = useState(false);

  useEffect(() => {
    setSignupAvailable(Boolean(metaAppId && signupConfigId));
  }, [metaAppId, signupConfigId]);

  const reload = async () => {
    const response = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`));
    if (!response.ok) throw new Error("Could not load WhatsApp connection.");
    const data = await response.json();
    const record = data.integrations.find((item: {provider: string}) => item.provider === "whatsapp");
    setConnected(Boolean(record?.is_active));
    setNeedsReconnect(record?.settings?.connection_status === "needs_reconnect");
    setAttentionChannel(record?.settings?.attention_channel || "WhatsApp");
    if (record) {
      setWaba(record.settings.waba_id || "");
      setPhone(record.settings.phone_number_id || "");
    }
  };
  useEffect(() => { if (tenantId) reload().catch(error => setNotice(error.message)); }, [tenantId]);

  const connectWithEmbeddedSignup = async () => {
    if (!metaAppId || !signupConfigId) {
      setNotice("WhatsApp one-click setup needs META_APP_ID and WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID configured on the server.");
      return;
    }

    setBusy(true);
    setNotice("Opening Meta’s WhatsApp setup…");
    let code: string | undefined;
    let assets: SignupAssets | undefined;
    let submitted = false;
    let timeoutId: number | undefined;

    const cleanup = () => {
      window.removeEventListener("message", handleMessage);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };

    const completeIfReady = async () => {
      if (submitted || !code || !assets?.waba_id || !assets.phone_number_id) return;
      submitted = true;
      cleanup();
      try {
        setNotice("Verifying the WhatsApp business account…");
        const response = await fetch(
          apiUrl(`/api/v1/tenant/${tenantId}/integrations/whatsapp/embedded-signup`),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              code,
              waba_id: assets.waba_id,
              phone_number_id: assets.phone_number_id,
            }),
          }
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "WhatsApp account verification failed.");
        setWaba(assets.waba_id);
        setPhone(assets.phone_number_id);
        await reload();
        await refetchTenant();
        window.dispatchEvent(new Event("joy:integrations-updated"));
        setNotice(data.message || "WhatsApp was connected. Live webhook delivery still needs testing.");
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "WhatsApp signup could not be verified.");
      } finally {
        setBusy(false);
      }
    };

    function handleMessage(event: MessageEvent) {
      let hostname = "";
      try {
        hostname = new URL(event.origin).hostname;
      } catch {
        return;
      }
      if (hostname !== "facebook.com" && !hostname.endsWith(".facebook.com")) return;

      let data: any;
      try {
        data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
      } catch {
        return;
      }
      if (data?.type !== "WA_EMBEDDED_SIGNUP") return;

      if (data.event === "CANCEL" || data.event === "ERROR") {
        cleanup();
        setBusy(false);
        setNotice(data.data?.error_message || "WhatsApp setup was cancelled before completion.");
        return;
      }
      if (!String(data.event || "").startsWith("FINISH")) return;
      assets = {
        waba_id: data.data?.waba_id,
        phone_number_id: data.data?.phone_number_id,
      };
      if (!assets.waba_id || !assets.phone_number_id) {
        cleanup();
        setBusy(false);
        setNotice("Meta finished setup without returning a WABA and phone number. Complete phone setup and try again.");
        return;
      }
      void completeIfReady();
    }

    try {
      const sdk = await loadMetaSdk(metaAppId);
      window.addEventListener("message", handleMessage);
      timeoutId = window.setTimeout(() => {
        cleanup();
        setBusy(false);
        setNotice("WhatsApp setup timed out. You can try again or use manual setup.");
      }, 5 * 60 * 1000);
      sdk.login((response) => {
        const returnedCode = response.authResponse?.code;
        if (!returnedCode) {
          cleanup();
          setBusy(false);
          setNotice("Meta login was cancelled or did not return an authorization code.");
          return;
        }
        code = returnedCode;
        void completeIfReady();
      }, {
        config_id: signupConfigId,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {} },
      });
    } catch (error) {
      cleanup();
      setBusy(false);
      setNotice(error instanceof Error ? error.message : "Could not start WhatsApp signup.");
    }
  };

  return <section className="rounded-xl border bg-card p-5">
    <h2 className="font-semibold">WhatsApp Business</h2>
    <p className="my-2 text-sm text-muted-foreground">
      Connect an official Cloud API number. Meta Embedded Signup can securely authorize and return the business account and phone number.
      JOY supports customer-initiated replies within Meta’s 24-hour window and approved templates from the Workbench when customer opt-in is recorded.
      Bulk campaigns are not enabled.
    </p>
    <p className="mb-3 text-sm">{needsReconnect
      ? "Reconnect required — WhatsApp replies are paused"
      : connected
        ? "Connected — account ownership and WABA subscription verified; live delivery still needs testing"
        : "Not connected"}</p>
    {needsReconnect && <div role="alert" className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="font-semibold">{attentionChannel} needs reconnection</p>
      <p className="mt-1">Replies are paused until WhatsApp is reauthorized. Existing delivery records are preserved.</p>
      <button type="button" onClick={() => {
        if (signupAvailable) {
          void connectWithEmbeddedSignup();
        } else {
          setNotice("One-click signup is unavailable. Enter refreshed credentials in Manual setup below.");
          document.getElementById("whatsapp-manual-token")?.focus();
        }
      }} disabled={busy}
        className="mt-2 rounded-md border border-amber-500 px-3 py-1.5 font-semibold disabled:opacity-50">
        Reconnect WhatsApp
      </button>
    </div>}
    {notice && <p role="status" className="mb-3 text-sm">{notice}</p>}
    <div className="mb-4 rounded-lg border p-3">
      <button
        type="button"
        disabled={busy || !signupAvailable}
        onClick={connectWithEmbeddedSignup}
        className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
      >
        {busy ? "Connecting…" : needsReconnect ? "Reconnect with Meta (recommended)" : "Connect with Meta (recommended)"}
      </button>
      {!signupAvailable && (
        <p className="mt-2 text-xs text-muted-foreground">
          One-click signup is unavailable until the server has META_APP_ID and WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID.
          The manual connection below remains available.
        </p>
      )}
    </div>
    <h3 className="mb-2 text-sm font-medium">Manual setup</h3>
    <form className="grid gap-3 md:grid-cols-3" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setNotice("");
      try {
        const response = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`), {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({provider:"whatsapp", access_token:token,
            settings:{waba_id:waba.trim(),phone_number_id:phone.trim()}})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "WhatsApp verification failed.");
        setToken(""); await reload(); await refetchTenant();
        setNotice(data.message || "Connected. Inbound messages require JOY’s Meta webhook callback to be enabled.");
      } catch(error) { setNotice(error instanceof Error ? error.message : "Connection failed."); }
      finally { setBusy(false); }
    }}>
      <label className="text-sm">Business Account ID
        <input required inputMode="numeric" pattern="[0-9]+" value={waba} onChange={e=>setWaba(e.target.value)}
          className="mt-1 w-full rounded-md border bg-background p-2" />
      </label>
      <label className="text-sm">Phone Number ID
        <input required inputMode="numeric" pattern="[0-9]+" value={phone} onChange={e=>setPhone(e.target.value)}
          className="mt-1 w-full rounded-md border bg-background p-2" />
      </label>
      <label className="text-sm">System-user access token
        <input id="whatsapp-manual-token" required type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}
          className="mt-1 w-full rounded-md border bg-background p-2" />
      </label>
      <button disabled={busy} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
        {busy ? "Verifying…" : connected ? "Reconnect" : "Verify and connect"}
      </button>
      {connected && <button type="button" disabled={busy} className="rounded-md border px-4 py-2 text-sm" onClick={async()=>{
        setBusy(true);
        try {
          const response=await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations/whatsapp`),{method:"DELETE"});
          const data=await response.json();
          if(!response.ok) throw new Error(data.detail || "Disconnect failed.");
          await reload(); await refetchTenant(); setNotice("Disconnected.");
        } catch(error) {setNotice(error instanceof Error ? error.message : "Disconnect failed.");}
        finally {setBusy(false);}
      }}>Disconnect</button>}
    </form>
  </section>;
}
