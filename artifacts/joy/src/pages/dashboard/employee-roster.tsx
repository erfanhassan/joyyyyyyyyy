
import React, { useState, useEffect } from "react";
import { Link } from "wouter";
import {
  Users,
  MessageSquare,
  PhoneCall,
  Sliders,
  Percent,
  Clock,
  ShieldAlert,
  Plus,
  CheckCircle2,
  Lock,
  Sparkles,
  RefreshCw,
  ArrowRight,
  ArrowLeft,
  Radio,
  SlidersHorizontal,
  Save,
  Check,
  Power
} from "lucide-react";
import { apiUrl } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

interface AgentRecord {
  id: string;
  name: string;
  agent_type: string;
  system_prompt: string;
  tone_settings: { tone_slider?: number; formality?: number; enthusiasm?: number };
  max_discount_pct: number;
  operational_hours: { start?: string; end?: string; timezone?: string };
  is_active: boolean;
  created_at?: string;
}

const TEMPLATES = [
  {
    type: "returns",
    name: "Returns & Exchanges Specialist",
    desc: "Validates photo proof of damages, verifies 7-day return policy, and dispatches courier pickup slips.",
    prompt: "You are the Returns and Exchange Specialist. Guide customers through replacement or store credit according to merchant return policy.",
    defaultDiscount: 0,
    isRoadmap: true,
  },
  {
    type: "abandoned_cart",
    name: "Cart Recovery Concierge",
    desc: "Reaches out via WhatsApp or SMS within 30 minutes with personalized assistance and capped discounts.",
    prompt: "You are the Cart Recovery Concierge. Assist customers who abandoned their checkout with helpful product guidance and limited discount codes.",
    defaultDiscount: 10,
    isRoadmap: true,
  },
  {
    type: "wholesale_inquiries",
    name: "B2B Wholesale Executive",
    desc: "Qualifies high-volume corporate and bulk buyer leads, collects VAT/TIN info, and schedules manager callbacks.",
    prompt: "You are the Wholesale B2B Executive. Collect buyer company information, estimated order volume, and schedule manager calls.",
    defaultDiscount: 15,
    isRoadmap: true,
  },
];

export default function EmployeeRosterPage() {
  const { tenantId } = useTenant();

  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [hireModalOpen, setHireModalOpen] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Hire Form Inputs
  const [newEmployeeName, setNewEmployeeName] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("returns");
  const [newEmployeeDiscount, setNewEmployeeDiscount] = useState(0);

  // Fetch real agent configs from PostgreSQL
  const loadAgents = async () => {
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/agents`));
      const data = await res.json();
      if (data.agents) {
        setAgents(data.agents);
      }
    } catch (err) {
      console.warn("Could not load agents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, [tenantId]);

  // Handle local state slider update
  const handleUpdateAgentLocal = (id: string, field: string, value: any) => {
    setAgents((prev) =>
      prev.map((a) => {
        if (a.id !== id) return a;
        if (field === "tone_slider") {
          return {
            ...a,
            tone_settings: { ...a.tone_settings, tone_slider: value },
          };
        }
        if (field === "max_discount_pct") {
          return { ...a, max_discount_pct: value };
        }
        if (field === "is_active") {
          return { ...a, is_active: value };
        }
        if (field === "time_start" || field === "time_end") {
          return {
            ...a,
            operational_hours: {
              ...a.operational_hours,
              [field === "time_start" ? "start" : "end"]: value,
            },
          };
        }
        return a;
      })
    );
  };

  // Persist agent guardrails to PostgreSQL
  const handleSaveGuardrails = async (agent: AgentRecord) => {
    setIsSaving(true);
    setSaveStatus(null);
    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/agents/${agent.id}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: agent.name,
          tone_settings: agent.tone_settings,
          max_discount_pct: agent.max_discount_pct,
          operational_hours: agent.operational_hours,
          is_active: agent.is_active,
        }),
      });
      if (res.ok) {
        setSaveStatus(`Saved guardrails for ${agent.name} to PostgreSQL database!`);
        setTimeout(() => setSaveStatus(null), 3500);
      }
    } catch (err: any) {
      alert("Error saving guardrails: " + err.message);
    } finally {
      setIsSaving(false);
    }
  };

  // Hire new employee and persist to PostgreSQL
  const handleHireEmployee = async () => {
    if (!newEmployeeName.trim()) {
      alert("Please enter a name for the new employee.");
      return;
    }
    const tmpl = TEMPLATES.find((t) => t.type === selectedTemplate) || TEMPLATES[0];

    try {
      const res = await fetch(apiUrl(`/api/v1/tenant/${tenantId}/agents`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newEmployeeName.trim(),
          agent_type: tmpl.type,
          system_prompt: tmpl.prompt,
          max_discount_pct: newEmployeeDiscount,
          tone_settings: { tone_slider: 60, formality: 0.6, enthusiasm: 0.7 },
          operational_hours: { start: "08:00", end: "21:00", timezone: "Asia/Dhaka" },
          is_active: true,
        }),
      });
      if (res.ok) {
        setHireModalOpen(false);
        setNewEmployeeName("");
        setSaveStatus(`Successfully hired and onboarded ${newEmployeeName}!`);
        loadAgents();
      }
    } catch (err: any) {
      alert("Error onboarding employee: " + err.message);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 text-xs font-semibold mb-2">
            <span>Step 3 of 4</span>
            <span>&bull;</span>
            <span>Digital Staff Guardrails &amp; Controls</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Digital Employee Roster &amp; Guardrails
          </h1>
          <p className="text-sm text-muted mt-1">
            Configure Tone of Voice sliders, maximum discount limits (5%&ndash;25%), and daytime calling hours. All settings are enforced by DeepSeek reasoning nodes.
          </p>
        </div>

        <button
          onClick={() => setHireModalOpen(true)}
          className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors flex items-center gap-1.5 shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>Hire New Digital Employee</span>
        </button>
      </div>

      {/* Save Notification */}
      {saveStatus && (
        <div className="p-3.5 bg-brand-50 border border-brand-100 rounded-xl text-xs text-brand-900 flex items-center justify-between animate-in slide-in-from-top-1">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-brand-600 flex-shrink-0" />
            <span className="font-semibold">{saveStatus}</span>
          </div>
          <button onClick={() => setSaveStatus(null)} className="text-brand-700 hover:text-brand-900 text-xs font-bold">
            ✕
          </button>
        </div>
      )}

      {/* Employee Cards List */}
      <div className="space-y-6">
        {agents.map((emp) => {
          const isSocial = emp.agent_type === "social_sales";
          const isVoice = emp.agent_type === "voice_confirmation";
          const currentTone = emp.tone_settings?.tone_slider ?? 65;

          return (
            <div
              key={emp.id}
              className="bg-white border border-border rounded-xl p-6 shadow-sm hover:border-foreground/30 transition-all space-y-6"
            >
              {/* Top Bar: Title & Toggle */}
              <div className="flex items-start justify-between flex-wrap gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-surface border border-border flex items-center justify-center">
                    {isSocial ? (
                      <MessageSquare className="w-5 h-5 text-brand-600" />
                    ) : isVoice ? (
                      <PhoneCall className="w-5 h-5 text-foreground" />
                    ) : (
                      <Users className="w-5 h-5 text-brand-700" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-foreground">{emp.name}</h3>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                        {emp.agent_type}
                      </span>
                    </div>
                    <p className="text-xs text-muted mt-0.5">
                      {isSocial
                        ? "Instagram DMs, Public Comments, and Web Widget live lead conversion"
                        : isVoice
                        ? "Outbound phone calls verifying order items, addresses & fraud check"
                        : "Specialized customer operation assistant"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleUpdateAgentLocal(emp.id, "is_active", !emp.is_active)}
                    className={`px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                      emp.is_active
                        ? "bg-brand-50 text-brand-700 border border-brand-100"
                        : "bg-surface text-muted border border-border"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${emp.is_active ? "bg-brand-600 animate-pulse" : "bg-muted"}`} />
                    <span>{emp.is_active ? "Active On Duty" : "Paused"}</span>
                  </button>

                  <button
                    onClick={() => handleSaveGuardrails(emp)}
                    disabled={isSaving}
                    className="px-3.5 py-1.5 bg-foreground hover:bg-foreground/90 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1 shadow-sm"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>Save Guardrails</span>
                  </button>
                </div>
              </div>

              {/* Guardrails Controls Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
                {/* Tone Slider */}
                <div className="p-4 rounded-xl bg-surface border border-border space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <SlidersHorizontal className="w-3.5 h-3.5 text-brand-600" />
                      Tone &amp; Personality
                    </span>
                    <span className="font-bold text-brand-700 font-mono">{currentTone}%</span>
                  </div>

                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={currentTone}
                    onChange={(e) => handleUpdateAgentLocal(emp.id, "tone_slider", parseInt(e.target.value))}
                    className="w-full accent-brand-600 cursor-pointer"
                  />

                  <div className="flex justify-between text-[10px] text-muted font-medium">
                    <span>Formal &amp; Direct</span>
                    <span>Polite</span>
                    <span>Warm &amp; Enthusiastic</span>
                  </div>
                </div>

                {/* Discount Cap Slider */}
                <div className="p-4 rounded-xl bg-surface border border-border space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <Percent className="w-3.5 h-3.5 text-brand-600" />
                      Hard Discount Cap
                    </span>
                    <span className="font-bold text-brand-700 font-mono">{emp.max_discount_pct}% Max</span>
                  </div>

                  <input
                    type="range"
                    min={0}
                    max={30}
                    step={5}
                    value={emp.max_discount_pct}
                    onChange={(e) => handleUpdateAgentLocal(emp.id, "max_discount_pct", parseInt(e.target.value))}
                    className="w-full accent-brand-600 cursor-pointer"
                  />

                  <div className="flex justify-between text-[10px] text-muted font-medium">
                    <span>0% (No discount)</span>
                    <span>10% (Standard)</span>
                    <span>30% (Clearance)</span>
                  </div>
                </div>

                {/* Daytime Calling Hours / Operating Window */}
                <div className="p-4 rounded-xl bg-surface border border-border space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-brand-600" />
                      Calling Hours (Local Time)
                    </span>
                    <span className="text-[10px] font-semibold text-brand-700">8 AM &ndash; 9 PM</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className="text-[10px] text-muted">Start Time</span>
                      <input
                        type="time"
                        value={emp.operational_hours?.start || "08:00"}
                        onChange={(e) => handleUpdateAgentLocal(emp.id, "time_start", e.target.value)}
                        className="w-full mt-1 p-1.5 text-xs bg-white border border-border rounded-lg"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-muted">End Time</span>
                      <input
                        type="time"
                        value={emp.operational_hours?.end || "21:00"}
                        onChange={(e) => handleUpdateAgentLocal(emp.id, "time_end", e.target.value)}
                        className="w-full mt-1 p-1.5 text-xs bg-white border border-border rounded-lg"
                      />
                    </div>
                  </div>

                  <p className="text-[10px] text-muted leading-tight">
                    Nighttime calling protection strictly blocks calls between 9 PM and 8 AM to prevent customer disturbances.
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Workflow Navigation Footer */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex items-center justify-between flex-wrap gap-4">
        <Link
          href="/dashboard/knowledge-brain"
          className="px-4 py-2.5 rounded-lg bg-surface border border-border text-foreground font-semibold text-xs hover:bg-white transition-colors shadow-sm flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Step 2: Employee Training</span>
        </Link>

        <div className="text-left sm:text-right">
          <div className="flex items-center sm:justify-end gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-600" />
            <h3 className="text-sm font-bold text-foreground">Step 3 Complete: Staff Guardrails Active</h3>
          </div>
          <p className="text-xs text-muted mt-0.5">
            Next, watch live social conversations and monitor sentiment in the Operator Desk.
          </p>
        </div>

        <Link
          href="/dashboard/operator-workbench"
          className="px-5 py-2.5 rounded-lg bg-brand-600 text-white font-semibold text-xs hover:bg-brand-700 transition-colors shadow-sm flex items-center gap-1.5"
        >
          <span>Proceed to Step 4: Open Operator Desk</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Hire New Employee Modal */}
      {hireModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Hire New Digital Employee</h3>
                <p className="text-xs text-muted mt-0.5">
                  Select a pre-built specialization role to onboard to your digital workforce.
                </p>
              </div>
              <button onClick={() => setHireModalOpen(false)} className="text-muted hover:text-foreground text-sm font-semibold">
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-foreground">Employee Name</label>
                <input
                  type="text"
                  value={newEmployeeName}
                  onChange={(e) => setNewEmployeeName(e.target.value)}
                  placeholder="e.g. Maya (Returns Specialist), Alex (VIP Sales)"
                  className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Choose Specialization Role</label>
                <div className="space-y-2 mt-2">
                  {TEMPLATES.map((tmpl) => (
                    <div
                      key={tmpl.type}
                      onClick={() => {
                        setSelectedTemplate(tmpl.type);
                        setNewEmployeeDiscount(tmpl.defaultDiscount);
                      }}
                      className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                        selectedTemplate === tmpl.type
                          ? "border-foreground bg-surface shadow-sm"
                          : "border-border hover:border-foreground/30 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between font-semibold text-foreground">
                        <div className="flex items-center gap-2">
                          <span>{tmpl.name}</span>
                          {tmpl.isRoadmap && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                              Roadmap
                            </span>
                          )}
                        </div>
                        {selectedTemplate === tmpl.type && <CheckCircle2 className="w-4 h-4 text-brand-600" />}
                      </div>
                      <p className="text-[11px] text-muted mt-1">{tmpl.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
              <button
                onClick={() => setHireModalOpen(false)}
                className="px-3.5 py-1.5 text-xs text-muted hover:text-foreground font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleHireEmployee}
                className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors shadow-sm"
              >
                Onboard to Database
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
