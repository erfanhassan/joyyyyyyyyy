
import React, { useState, useEffect } from "react";
import { Link } from "wouter";
import { useLocation } from "wouter";
import {
  Layers,
  Brain,
  Users,
  Inbox,
  ShieldCheck,
  ChevronRight,
  ExternalLink,
  ArrowRight,
  CheckCircle2,
  Settings,
  Store,
  Check,
  Save,
  X
} from "lucide-react";
import { apiUrl } from "@/lib/api";

const STEPS = [
  {
    step: 1,
    name: "Connect Stores",
    short: "1. Integrations",
    href: "/dashboard/integration-hub",
    icon: Layers,
    desc: "Meta, Shopify & Web Embed",
    instruction: "Connect your sales channels so JOY can listen to customer comments, DMs, and orders.",
  },
  {
    step: 2,
    name: "Train Brain",
    short: "2. Training",
    href: "/dashboard/knowledge-brain",
    icon: Brain,
    desc: "Catalogs & Storefront Crawler",
    instruction: "Upload product catalogs or crawl your website so employees know what items are in stock.",
  },
  {
    step: 3,
    name: "Staff Guardrails",
    short: "3. Guardrails",
    href: "/dashboard/employee-roster",
    icon: Users,
    desc: "Tone, Discounts & Hours",
    instruction: "Set discount caps (e.g. 10%), tone of voice, and daytime calling hours for your digital employees.",
  },
  {
    step: 4,
    name: "Live Operations",
    short: "4. Live Desk",
    href: "/dashboard/operator-workbench",
    icon: Inbox,
    desc: "Unified Inbox & Takeover",
    instruction: "Watch live customer conversations, sentiment risk alerts, and step in anytime with 1-click human takeover.",
  },
];

import { useTenant } from "@/lib/tenant-context";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [pathname] = useLocation();
  const currentStep = STEPS.find((s) => s.href === pathname) || STEPS[0];

  const { tenant, tenantId, updateTenant } = useTenant();
  const [storeName, setStoreName] = useState<string>("My Storefront");
  const [currency, setCurrency] = useState<string>("BDT");
  const [timezone, setTimezone] = useState<string>("Asia/Dhaka");
  const [storeDomain, setStoreDomain] = useState<string>("joy.sonictch.com");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (tenant) {
      if (tenant.name) setStoreName(tenant.name);
      if (tenant.currency) setCurrency(tenant.currency);
      if (tenant.timezone) setTimezone(tenant.timezone);
      if (tenant.domain) setStoreDomain(tenant.domain);
    }
  }, [tenant]);

  const handleSaveStoreSettings = async () => {
    setIsSaving(true);
    try {
      const success = await updateTenant({
        name: storeName,
        currency: currency,
        timezone: timezone,
        domain: storeDomain,
      });
      if (success) {
        setSaveSuccess(true);
        setTimeout(() => {
          setSaveSuccess(false);
          setSettingsOpen(false);
        }, 1200);
      }
    } catch (err) {
      console.warn("Failed to update store settings:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface text-foreground font-sans antialiased selection:bg-brand-100 selection:text-brand-900">
      {/* Top Header */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-3 group">
              <span className="text-2xl font-black tracking-tight text-foreground group-hover:text-brand-600 transition-colors">
                JOY
              </span>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                Live Merchant Workspace
              </span>
            </Link>

            {/* Stepper Navigation */}
            <nav className="hidden lg:flex items-center gap-1.5 bg-surface p-1 rounded-xl border border-border">
              {STEPS.map((s) => {
                const Icon = s.icon;
                const isActive = pathname === s.href;
                const isPassed = currentStep.step > s.step;

                return (
                  <Link
                    key={s.href}
                    href={s.href}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      isActive
                        ? "bg-foreground text-white shadow-sm"
                        : isPassed
                        ? "text-brand-700 bg-brand-50/60 hover:bg-brand-50"
                        : "text-muted hover:text-foreground hover:bg-white"
                    }`}
                  >
                    {isPassed ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
                    ) : (
                      <Icon className="w-3.5 h-3.5" />
                    )}
                    <span>{s.short}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {/* Dynamic Store Profile Pill */}
            <button
              onClick={() => setSettingsOpen(true)}
              className="flex items-center gap-2 text-xs font-semibold text-foreground bg-white hover:bg-surface px-3 py-1.5 rounded-full border border-border shadow-sm transition-all group"
              title="Click to customize store settings"
            >
              <Store className="w-3.5 h-3.5 text-brand-600" />
              <span>{storeName}</span>
              <Settings className="w-3 h-3 text-muted group-hover:text-foreground transition-colors" />
            </button>

            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:flex text-xs font-medium text-muted hover:text-foreground items-center gap-1 px-2.5 py-1.5 rounded-md hover:bg-surface transition-colors"
            >
              <span>API Specs</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>

        {/* Guided Step Sub-Banner */}
        <div className="border-t border-border/80 bg-white/70 px-6 py-2">
          <div className="max-w-7xl mx-auto flex items-center justify-between text-xs flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-bold px-2 py-0.5 rounded bg-brand-50 text-brand-700 border border-brand-100 uppercase tracking-wider text-[10px]">
                Step {currentStep.step} of 4
              </span>
              <span className="font-semibold text-foreground">{currentStep.name}:</span>
              <span className="text-muted hidden md:inline">{currentStep.instruction}</span>
            </div>

            {currentStep.step < 4 && (
              <Link
                href={STEPS[currentStep.step].href}
                className="font-semibold text-brand-700 hover:text-brand-800 flex items-center gap-1 text-[11px] group"
              >
                <span>Next: {STEPS[currentStep.step].name}</span>
                <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            )}
          </div>
        </div>

        {/* Mobile Stepper Navigation */}
        <div className="lg:hidden flex items-center gap-1 px-4 py-2 border-t border-border overflow-x-auto bg-surface">
          {STEPS.map((s) => {
            const Icon = s.icon;
            const isActive = pathname === s.href;
            return (
              <Link
                key={s.href}
                href={s.href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap ${
                  isActive
                    ? "bg-foreground text-white"
                    : "text-muted hover:text-foreground"
                }`}
              >
                <Icon className="w-3 h-3" />
                <span>{s.short}</span>
              </Link>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {children}
      </main>

      {/* Visible Dashboard Footer */}
      <footer className="border-t border-border bg-white/80 py-6 mt-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted">
          <div className="flex items-center gap-3">
            <span className="font-bold text-foreground">JOY</span>
            <span>&bull;</span>
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-brand-600" />
              <span>Multi-Tenant Vault Active</span>
            </span>
            <span>&bull;</span>
            <span>&copy; {new Date().getFullYear()} JOY Inc.</span>
          </div>
          <div className="flex items-center gap-5">
            <Link
              href="/privacy"
              className="text-foreground hover:text-brand-600 font-medium transition-colors underline underline-offset-4 decoration-border hover:decoration-brand-600"
            >
              Privacy Policy
            </Link>
            <Link
              href="/terms"
              className="text-foreground hover:text-brand-600 font-medium transition-colors underline underline-offset-4 decoration-border hover:decoration-brand-600"
            >
              Terms of Service
            </Link>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors flex items-center gap-1"
            >
              <span>API Specs</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </footer>

      {/* Store Settings Modal */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-border rounded-2xl max-w-md w-full p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Storefront &amp; Business Profile</h3>
                <p className="text-xs text-muted mt-0.5">
                  Customize your business details. JOY stores these in your dedicated PostgreSQL tenant partition.
                </p>
              </div>
              <button
                onClick={() => setSettingsOpen(false)}
                className="text-muted hover:text-foreground p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-foreground">Business / Storefront Name</label>
                <input
                  type="text"
                  value={storeName}
                  onChange={(e) => setStoreName(e.target.value)}
                  placeholder="e.g. Dhaka Silk Store, Gulshan Fashion Hub, Tech Zone"
                  className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Storefront Domain / Website</label>
                <input
                  type="text"
                  value={storeDomain}
                  onChange={(e) => setStoreDomain(e.target.value)}
                  placeholder="e.g. www.myboutique.com"
                  className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Store Currency</label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                  >
                    <option value="BDT">BDT (৳ Taka)</option>
                    <option value="USD">USD ($ Dollar)</option>
                    <option value="EUR">EUR (€ Euro)</option>
                    <option value="GBP">GBP (£ Pound)</option>
                    <option value="AED">AED (Dirham)</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-foreground">Operational Timezone</label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
                  >
                    <option value="Asia/Dhaka">Dhaka (GMT+6)</option>
                    <option value="Asia/Dubai">Dubai (GMT+4)</option>
                    <option value="Europe/London">London (GMT+0)</option>
                    <option value="America/New_York">New York (EST)</option>
                    <option value="Asia/Singapore">Singapore (GMT+8)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-border pt-4">
              <span className="text-[11px] text-muted">Tenant ID: {tenantId.substring(0, 8)}...</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSettingsOpen(false)}
                  className="px-3 py-1.5 text-xs text-muted hover:text-foreground font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveStoreSettings}
                  disabled={isSaving}
                  className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors shadow-sm flex items-center gap-1.5"
                >
                  {saveSuccess ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-brand-400" />
                      <span>Saved!</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      <span>{isSaving ? "Saving..." : "Save Store Profile"}</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
