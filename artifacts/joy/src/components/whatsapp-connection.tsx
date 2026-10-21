import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

export function WhatsAppConnection() {
  const { tenantId, refetchTenant } = useTenant();
  const [waba, setWaba] = useState("");
  const [phone, setPhone] = useState("");
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const reload = async () => {
    const response = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/integrations`));
    if (!response.ok) throw new Error("Could not load WhatsApp connection.");
    const data = await response.json();
    const record = data.integrations.find((item: {provider: string}) => item.provider === "whatsapp");
    setConnected(Boolean(record?.is_active));
    if (record) {
      setWaba(record.settings.waba_id || "");
      setPhone(record.settings.phone_number_id || "");
    }
  };
  useEffect(() => { if (tenantId) reload().catch(error => setNotice(error.message)); }, [tenantId]);
  return <section className="rounded-xl border bg-card p-5">
    <h2 className="font-semibold">WhatsApp Business</h2>
    <p className="my-2 text-sm text-muted-foreground">
      Connect an official Cloud API number. Customer-initiated text replies are supported within Meta’s 24-hour window.
      Outbound campaigns and template messages are not enabled. App permissions and business approval are required.
    </p>
    <p className="mb-3 text-sm">{connected ? "Connected — number ownership and webhook subscription verified" : "Not connected"}</p>
    {notice && <p role="status" className="mb-3 text-sm">{notice}</p>}
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
        setNotice("Connected. Configure the Meta webhook callback for WhatsApp messages in your provider account.");
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
        <input required type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}
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
