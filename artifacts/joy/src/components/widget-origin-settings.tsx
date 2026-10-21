import { useEffect, useState } from "react";
import { useTenant } from "@/lib/tenant-context";
import { apiUrl } from "@/lib/api";

export function WidgetOriginSettings() {
  const {tenantId}=useTenant();
  const [domain,setDomain]=useState("");
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!tenantId) return;
    let live=true;
    fetch(apiUrl(`/api/v1/tenant/${tenantId}`)).then(async response=>{
      if(!response.ok) throw new Error("Website configuration could not be loaded.");
      const data=await response.json();
      if(live) setDomain(data.domain||"");
    }).catch(problem=>{if(live) setError(problem.message);});
    return()=>{live=false;};
  },[tenantId]);
  const save=async(event:React.FormEvent)=>{
    event.preventDefault();setError("");setNotice("");
    let origin:string;
    try {
      const parsed=new URL(domain);
      if(parsed.protocol!=="https:"||parsed.username||parsed.password||parsed.port)
        throw new Error();
      origin=parsed.origin;
    }catch{
      setError("Enter the exact HTTPS website origin, for example https://your-store.com.");return;
    }
    setBusy(true);
    try{
      const response=await fetch(apiUrl(`/api/v1/tenant/${tenantId}/widget-origin`),{
        method:"PATCH",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({domain:origin})});
      const data=await response.json();
      if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:
        Array.isArray(data.detail)?data.detail.map((item:{msg?:string})=>item.msg||"Invalid value").join("; "):
        "Website origin could not be saved.");
      setDomain(origin);setNotice("Website origin saved. Install the widget on this exact domain.");
    }catch(problem){setError(problem instanceof Error?problem.message:"Website setup failed.");}
    finally{setBusy(false);}
  };
  return <section className="rounded-xl border bg-card p-5">
    <h2 className="font-semibold">Website widget origin</h2>
    <p className="my-2 text-sm text-muted-foreground">Register the website where customers will use the widget. Other origins are rejected; an embed snippet alone does not enable chat.</p>
    <form onSubmit={save} className="flex flex-wrap items-end gap-3">
      <label className="flex-1 text-sm">Store website origin
        <input type="url" required value={domain} onChange={event=>setDomain(event.target.value)}
          placeholder="https://your-store.com" className="mt-1 w-full rounded border bg-background px-3 py-2"/>
      </label>
      <button disabled={busy||!tenantId} className="rounded bg-foreground px-4 py-2 text-sm text-background">
        {busy?"Saving…":"Save website origin"}
      </button>
    </form>
    {notice&&<p role="status" className="mt-2 text-sm">{notice}</p>}
    {error&&<p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
  </section>;
}
