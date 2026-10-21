import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

export function PrivacyRequests() {
  const [rows,setRows]=useState<{code:string;status:string}[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const path="/api/v1/webhooks/meta-privacy/requests";
  const load=async()=> {
    const response=await fetch(apiUrl(path));
    if(response.ok) setRows(await response.json());
  };
  useEffect(()=>{load().catch(()=>{});},[]);
  const complete=async(code:string)=> {
    if(!window.confirm("Permanently delete only the Meta data covered by this signed request? This cannot be undone. In-flight processing must finish first.")) return;
    setBusy(true);setError("");
    try{
      const response=await fetch(apiUrl(`${path}/${code}/complete`),{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({confirm:"DELETE_REQUESTED_DATA"})});
      const data=await response.json();
      if(!response.ok) throw new Error(data.detail||"Deletion could not be completed.");
      await load();
    }catch(problem){setError(problem instanceof Error?problem.message:"Deletion unavailable.");}
    finally{setBusy(false);}
  };
  if(!rows.length&&!error) return null;
  return <section className="rounded-xl border p-5">
    <h2 className="font-semibold">Signed Meta privacy requests</h2>
    <p className="my-2 text-sm">The app owner must review these requests. Credentials are already revoked; deletion is never marked complete while processing is active.</p>
    {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}
    <ul className="text-sm">{rows.map(row=><li className="my-2" key={row.code}>
      {row.code} · {row.status}{" "}
      {row.status.startsWith("delete_")&&<button disabled={busy} onClick={()=>complete(row.code)}
        className="rounded border px-2 py-1 text-destructive">Complete verified deletion</button>}
    </li>)}</ul>
  </section>;
}
