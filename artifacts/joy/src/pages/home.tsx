
import React, { useEffect, useState } from "react";
import { Link } from "wouter";
import { 
  Users, 
  MessageSquare, 
  PhoneCall, 
  Bot, 
  CheckCircle2, 
  ArrowRight, 
  ShieldCheck, 
  Zap, 
  Layers, 
  Radio,
  ExternalLink,
  Brain,
  Inbox,
  Sparkles
} from "lucide-react";
import { apiUrl } from "@/lib/api";

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<string>("checking...");
  const [backendVersion, setBackendVersion] = useState<string>("");

  useEffect(() => {
    fetch(apiUrl("/health"))
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "ok") {
          setBackendStatus("Connected (Healthy)");
          setBackendVersion(data.version || "1.0.0");
        } else {
          setBackendStatus("Degraded");
        }
      })
      .catch(() => {
        setBackendStatus("Connecting...");
      });
  }, []);

  return (
    <div className="min-h-screen bg-surface text-foreground font-sans antialiased selection:bg-brand-100 selection:text-brand-900">
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl font-black tracking-tight text-foreground">JOY</span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
              Digital Workforce
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden lg:flex items-center gap-2 text-xs font-medium text-muted bg-surface px-3 py-1.5 rounded-full border border-border">
              <span className={`w-2 h-2 rounded-full ${backendStatus.includes("Healthy") ? "bg-brand-600" : "bg-warning"}`} />
              API: <span className="text-foreground font-semibold">{backendStatus}</span>
            </div>

            <Link
              href="/dashboard/operator-workbench"
              className="text-xs font-semibold px-3 py-1.5 text-muted hover:text-foreground transition-colors"
            >
              Operator Desk
            </Link>

            <Link
              href="/sign-in"
              className="text-xs font-semibold px-3 py-1.5 text-muted hover:text-foreground transition-colors"
            >
              Sign in
            </Link>

            <Link
              href="/dashboard/integration-hub"
              className="text-xs font-semibold px-4 py-2 rounded-lg bg-foreground text-white hover:bg-foreground/90 transition-colors shadow-sm flex items-center gap-1.5"
            >
              <span>Launch Dashboard</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Hero Section */}
        <div className="max-w-3xl mb-12">
          <div className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase px-3 py-1 rounded-full bg-surface-hover text-muted mb-4 border border-border">
            <Zap className="w-3.5 h-3.5 text-brand-600" />
            Autonomous Digital Staff for Retail &amp; E-Commerce
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-foreground leading-[1.15] mb-4">
            Manage social sales with a verified AI assistant.
          </h1>
          <p className="text-lg text-muted leading-relaxed mb-6">
            Connect your store and social channels, set operating hours, and keep a human in control. Phone confirmation is not yet available and requires a verified voice worker and SIP route.
          </p>

          {/* Quick Flow Actions */}
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/dashboard/integration-hub"
              className="px-5 py-3 rounded-xl bg-brand-600 text-white font-semibold text-sm hover:bg-brand-700 transition-colors shadow-sm flex items-center gap-2"
            >
              <span>Start 4-Step Onboarding Walkthrough</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/dashboard/operator-workbench"
              className="px-5 py-3 rounded-xl bg-white text-foreground border border-border font-semibold text-sm hover:bg-surface transition-colors shadow-sm flex items-center gap-2"
            >
              <Inbox className="w-4 h-4 text-brand-600" />
              <span>Explore Live Operator Desk</span>
            </Link>
          </div>
        </div>

        {/* 4-Step Visual Journey Card */}
        <div className="bg-white rounded-2xl p-6 sm:p-8 border border-border shadow-sm mb-14">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-6">
            <div>
              <div className="text-xs font-bold text-brand-700 uppercase tracking-wider mb-1">
                How JOY Works &bull; 4 Clear Steps
              </div>
              <h2 className="text-xl font-bold text-foreground">
                Follow this simple linear flow to activate your digital workforce:
              </h2>
            </div>
            <span className="text-xs text-muted font-medium bg-surface px-3 py-1 rounded-full border border-border">
              Takes under 5 minutes
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Step 1 */}
            <Link
              href="/dashboard/integration-hub"
              className="group p-5 rounded-xl bg-surface border border-border hover:border-brand-500/50 hover:bg-white transition-all shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-700 font-bold text-xs mb-3">
                  1
                </div>
                <h3 className="font-bold text-sm text-foreground group-hover:text-brand-700 transition-colors flex items-center justify-between">
                  <span>Connect Stores</span>
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </h3>
                <p className="text-xs text-muted mt-1 leading-relaxed">
                  Link Meta (Instagram &amp; Facebook), Shopify, or WooCommerce with 1 click.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] font-semibold text-brand-700">
                Go to Step 1 &rarr;
              </div>
            </Link>

            {/* Step 2 */}
            <Link
              href="/dashboard/knowledge-brain"
              className="group p-5 rounded-xl bg-surface border border-border hover:border-brand-500/50 hover:bg-white transition-all shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-700 font-bold text-xs mb-3">
                  2
                </div>
                <h3 className="font-bold text-sm text-foreground group-hover:text-brand-700 transition-colors flex items-center justify-between">
                  <span>Train Staff Brain</span>
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </h3>
                <p className="text-xs text-muted mt-1 leading-relaxed">
                  Drop your PDF/CSV catalog or paste your store URL for instant AI lookup.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] font-semibold text-brand-700">
                Go to Step 2 &rarr;
              </div>
            </Link>

            {/* Step 3 */}
            <Link
              href="/dashboard/employee-roster"
              className="group p-5 rounded-xl bg-surface border border-border hover:border-brand-500/50 hover:bg-white transition-all shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-700 font-bold text-xs mb-3">
                  3
                </div>
                <h3 className="font-bold text-sm text-foreground group-hover:text-brand-700 transition-colors flex items-center justify-between">
                  <span>Set Guardrails</span>
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </h3>
                <p className="text-xs text-muted mt-1 leading-relaxed">
                  Configure tone, discount caps (e.g. 10%), and daytime calling hours.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] font-semibold text-brand-700">
                Go to Step 3 &rarr;
              </div>
            </Link>

            {/* Step 4 */}
            <Link
              href="/dashboard/operator-workbench"
              className="group p-5 rounded-xl bg-surface border border-border hover:border-brand-500/50 hover:bg-white transition-all shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-700 font-bold text-xs mb-3">
                  4
                </div>
                <h3 className="font-bold text-sm text-foreground group-hover:text-brand-700 transition-colors flex items-center justify-between">
                  <span>Operator Desk</span>
                  <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </h3>
                <p className="text-xs text-muted mt-1 leading-relaxed">
                  Watch live sales conversations and step in anytime with 1-Click Crimson Takeover.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-border/60 text-[11px] font-semibold text-brand-700">
                Go to Step 4 &rarr;
              </div>
            </Link>
          </div>
        </div>

        {/* Digital Employee Roster Cards */}
        <div className="mb-14">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-bold text-foreground">Active Digital Staff</h2>
              <p className="text-xs text-muted">Specialized AI employees working inside your business right now</p>
            </div>
            <Link 
              href="/dashboard/employee-roster"
              className="text-xs font-semibold px-4 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 transition-colors shadow-sm"
            >
              + Hire New Employee
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Employee #1 Card */}
            <div className="bg-white rounded-2xl p-6 border border-border shadow-sm hover:border-brand-500/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600">
                    <MessageSquare className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground text-lg">Social Sales Specialist</h3>
                    <p className="text-xs text-muted">Employee #1 &bull; Instagram, Facebook &amp; Web Chat</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                  Active
                </span>
              </div>

              <p className="text-sm text-muted mb-6 leading-normal">
                Monitors public comments, Reels, and direct messages 24/7. Researches stock in your catalog, answers pricing questions, and sends checkout links within seconds.
              </p>

              <div className="grid grid-cols-3 gap-3 p-3 rounded-xl bg-surface border border-border mb-4 text-center">
                <div>
                  <div className="text-xs text-muted">Response Time</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">&lt; 3s</div>
                </div>
                <div>
                  <div className="text-xs text-muted">Max Discount</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">10% Capped</div>
                </div>
                <div>
                  <div className="text-xs text-muted">Catalog Match</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">Hybrid BM25</div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border/60 text-xs">
                <span className="text-muted">Intelligence: DeepSeek + MCP Tools</span>
                <Link
                  href="/dashboard/employee-roster"
                  className="font-semibold text-brand-600 hover:text-brand-700 cursor-pointer flex items-center gap-0.5"
                >
                  Configure Settings &rarr;
                </Link>
              </div>
            </div>

            {/* Employee #2 Card */}
            <div className="bg-white rounded-2xl p-6 border border-border shadow-sm hover:border-brand-500/40 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600">
                    <PhoneCall className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground text-lg">Phone Confirmation Specialist</h3>
                    <p className="text-xs text-muted">Employee #2 &bull; Shopify &amp; WooCommerce Orders</p>
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse" />
                  Active
                </span>
              </div>

              <p className="text-sm text-muted mb-6 leading-normal">
                Autonomously calls customers to verify delivery address and order items. Adheres to local timezones and falls back to WhatsApp/SMS if unanswered.
              </p>

              <div className="grid grid-cols-3 gap-3 p-3 rounded-xl bg-surface border border-border mb-4 text-center">
                <div>
                  <div className="text-xs text-muted">Latency</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">&lt; 800ms WebRTC</div>
                </div>
                <div>
                  <div className="text-xs text-muted">SIP Trunk</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">AmberIT / Local</div>
                </div>
                <div>
                  <div className="text-xs text-muted">Timezone Gate</div>
                  <div className="text-sm font-bold text-foreground mt-0.5">8 AM - 9 PM</div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border/60 text-xs">
                <span className="text-muted">Voice Engine: LiveKit + Cartesia</span>
                <Link
                  href="/dashboard/employee-roster"
                  className="font-semibold text-brand-600 hover:text-brand-700 cursor-pointer flex items-center gap-0.5"
                >
                  Configure Settings &rarr;
                </Link>
              </div>
            </div>
          </div>
        </div>

        {/* Infrastructure & Security Health */}
        <div className="bg-white rounded-2xl p-6 border border-border">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-brand-600" />
              <h3 className="font-bold text-foreground">Infrastructure &amp; Compliance Status</h3>
            </div>
            <span className="text-xs text-muted">PostgreSQL 16 &bull; Redis 7 &bull; FastAPI</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 pt-2">
            <div className="p-4 rounded-xl bg-surface border border-border">
              <div className="text-xs text-muted mb-1">FastAPI Backend</div>
              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-brand-600" />
                Port 8000 (Active)
              </div>
            </div>
            <div className="p-4 rounded-xl bg-surface border border-border">
              <div className="text-xs text-muted mb-1">PostgreSQL 16 + pgvector</div>
              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-brand-600" />
                Port 5432 (Healthy)
              </div>
            </div>
            <div className="p-4 rounded-xl bg-surface border border-border">
              <div className="text-xs text-muted mb-1">Redis Cluster / Cache</div>
              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-brand-600" />
                Port 6379 (Healthy)
              </div>
            </div>
            <div className="p-4 rounded-xl bg-surface border border-border">
              <div className="text-xs text-muted mb-1">Multi-Tenant Isolation</div>
              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-brand-600" />
                PostgreSQL RLS Active
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Visible Bottom Footer with Legal & Compliance Links */}
      <footer className="border-t border-border bg-white mt-20">
        <div className="max-w-6xl mx-auto px-6 py-12">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div className="md:col-span-2 space-y-3">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl font-black tracking-tight text-foreground">JOY</span>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                  Digital Workforce
                </span>
              </div>
              <p className="text-xs text-muted max-w-sm leading-relaxed">
                Autonomous AI sales agents and voice order verification for retail &amp; e-commerce merchants. Securely integrates with Meta Business Suite, Instagram, Shopify, and WooCommerce.
              </p>
              <div className="flex items-center gap-3 text-[11px] text-zinc-500 pt-1">
                <span className="flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-brand-600" /> AES-256 Vault Encrypted
                </span>
                <span>&bull;</span>
                <span>Meta Platform Compliant</span>
              </div>
            </div>

            <div>
              <h4 className="text-xs font-bold text-foreground uppercase tracking-wider mb-3">Platform</h4>
              <ul className="space-y-2 text-xs">
                <li>
                  <Link href="/dashboard/integration-hub" className="text-muted hover:text-foreground transition-colors">
                    Integration Hub (Meta &amp; Shopify)
                  </Link>
                </li>
                <li>
                  <Link href="/dashboard/knowledge-brain" className="text-muted hover:text-foreground transition-colors">
                    Knowledge Brain
                  </Link>
                </li>
                <li>
                  <Link href="/dashboard/operator-workbench" className="text-muted hover:text-foreground transition-colors">
                    Operator Workbench
                  </Link>
                </li>
                <li>
                  <a href="/docs" target="_blank" rel="noopener noreferrer" className="text-muted hover:text-foreground transition-colors">
                    Backend API Docs
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <h4 className="text-xs font-bold text-foreground uppercase tracking-wider mb-3">Legal &amp; Policy</h4>
              <ul className="space-y-2 text-xs">
                <li>
                  <Link href="/privacy" className="font-semibold text-brand-700 hover:text-brand-900 transition-colors flex items-center gap-1.5">
                    <span>Privacy Policy</span>
                  </Link>
                </li>
                <li>
                  <Link href="/terms" className="font-semibold text-brand-700 hover:text-brand-900 transition-colors flex items-center gap-1.5">
                    <span>Terms of Service</span>
                  </Link>
                </li>
                <li>
                  <Link href="/privacy#deletion" className="text-muted hover:text-foreground transition-colors">
                    User Data Deletion Callback
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          <div className="pt-8 border-t border-border/80 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted">
            <div>
              &copy; {new Date().getFullYear()} JOY Inc. All rights reserved.
            </div>
            <div className="flex items-center gap-6">
              <Link href="/privacy" className="text-foreground hover:text-brand-600 font-medium transition-colors">
                Privacy Policy
              </Link>
              <Link href="/terms" className="text-foreground hover:text-brand-600 font-medium transition-colors">
                Terms of Service
              </Link>
              <span className="text-zinc-400">Dhaka, Bangladesh</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
