import React from "react";
import Link from "next/link";
import { Scale, ArrowLeft, ShieldCheck, FileCheck, CheckCircle2 } from "lucide-react";

export const metadata = {
  title: "Terms of Service | JOY Digital Workforce",
  description: "Terms of Service and Merchant Usage Guidelines for JOY.",
};

export default function TermsOfServicePage() {
  return (
    <div className="min-h-screen bg-surface text-foreground font-sans antialiased selection:bg-brand-100 selection:text-brand-900 flex flex-col justify-between">
      {/* Top Header */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-border">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 group">
            <span className="text-2xl font-black tracking-tight text-foreground group-hover:text-brand-600 transition-colors">
              JOY
            </span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
              Legal &amp; Compliance
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard/integration-hub"
              className="text-xs font-semibold text-brand-700 hover:text-brand-900 px-3 py-1.5 rounded-lg hover:bg-brand-50 transition-colors flex items-center gap-1.5"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Dashboard</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-12 flex-1">
        <div className="space-y-4 mb-10 pb-8 border-b border-border">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-100 text-zinc-800 border border-zinc-200 text-xs font-semibold">
            <Scale className="w-3.5 h-3.5" />
            <span>Merchant Agreement &amp; Platform Terms</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-foreground tracking-tight">
            Terms of Service
          </h1>
          <p className="text-sm text-muted">
            Last Updated: October 20, 2026 &bull; Effective Date: October 20, 2026
          </p>
        </div>

        <div className="prose prose-zinc max-w-none space-y-8 text-sm leading-relaxed text-zinc-700">
          {/* Section 1 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">1</span>
              Agreement &amp; Acceptance of Terms
            </h2>
            <p>
              By accessing or using the JOY platform (&quot;JOY,&quot; &quot;Service,&quot; &quot;we,&quot; or &quot;us&quot;), including connecting your Facebook Pages, Instagram Professional Accounts, WhatsApp, Shopify, or WooCommerce stores, you agree to be bound by these Terms of Service. If you are entering into this agreement on behalf of a company or commercial retail entity, you represent that you possess the authority to bind such entity.
            </p>
          </section>

          {/* Section 2 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">2</span>
              Platform Description &amp; Digital Employees
            </h2>
            <p>
              JOY provides an autonomous agentic platform featuring digital employees:
            </p>
            <ul className="list-disc pl-5 space-y-1.5 text-zinc-600">
              <li>
                <strong>Employee #1 (Social Sales Agent):</strong> Automatically responds to customer post comments, Reels comments, and direct messages on Instagram, Facebook Messenger, and website live chat widgets.
              </li>
              <li>
                <strong>Employee #2 (Voice Confirmation Agent):</strong> Conducts automated outbound phone calls via SIP telephony to verify cash-on-delivery (COD) addresses, item sizes, and buyer intent.
              </li>
              <li>
                <strong>Operator Workbench:</strong> Provides real-time human-in-the-loop (HITL) oversight, sentiment alerts, and manual takeover controls.
              </li>
            </ul>
          </section>

          {/* Section 3 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">3</span>
              Meta Platform Terms &amp; Acceptable Messaging
            </h2>
            <p>
              Merchants connecting Meta social channels via Facebook Login must adhere strictly to Meta&apos;s Platform Policies, including but not limited to:
            </p>
            <ul className="list-disc pl-5 space-y-2 text-zinc-600">
              <li>
                <strong>The 24-Hour Messaging Window:</strong> Automated outbound responses and Comment-to-DM handshakes must operate strictly within Meta&apos;s standard 24-hour messaging guidelines unless permitted via approved Message Tags.
              </li>
              <li>
                <strong>No Prohibited Content or Spam:</strong> Merchants must not use JOY to send unsolicited bulk spam, deceptive promotional claims, or prohibited goods as defined under Meta&apos;s Commerce and Advertising Policies.
              </li>
              <li>
                <strong>Accurate Account Representation:</strong> You must only connect Facebook Pages and Instagram accounts that you legally own, operate, or are an authorized administrator of.
              </li>
            </ul>
          </section>

          {/* Section 4 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">4</span>
              Human-in-the-Loop (HITL) &amp; Merchant Responsibility
            </h2>
            <div className="p-4 rounded-xl bg-surface border border-border space-y-2 text-xs">
              <div className="flex items-center gap-2 font-bold text-foreground">
                <ShieldCheck className="w-4 h-4 text-brand-600" />
                <span>Supervision &amp; Guardrail Safeguards</span>
              </div>
              <p className="text-muted leading-relaxed">
                While JOY utilizes advanced language models and guardrail thresholds (discount caps, daytime calling restrictions, sentiment interrupts), you as the merchant remain ultimately responsible for your customer communications, product catalog accuracy, and fulfillment practices. Operators should monitor the Operator Workbench for sentiment flags and intervene when appropriate.
              </p>
            </div>
          </section>

          {/* Section 5 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">5</span>
              Data Ownership &amp; Intellectual Property
            </h2>
            <p>
              You retain 100% full ownership of your product catalogs, store trademarks, customer lists, and business content uploaded to JOY. JOY grants you a limited, non-exclusive, revocable license to access the platform software in accordance with your subscription plan.
            </p>
          </section>

          {/* Section 6 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">6</span>
              Limitation of Liability
            </h2>
            <p>
              To the maximum extent permitted by applicable law, JOY shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including loss of profits, data, or business interruption arising from carrier telephony outages, third-party API rate limits (Meta, Shopify, WooCommerce), or unauthorized account access.
            </p>
          </section>

          {/* Section 7 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">7</span>
              Termination &amp; Disconnection
            </h2>
            <p>
              You may terminate your usage of JOY at any time by disconnecting your channels in the Integration Hub and closing your account. Upon termination, all encrypted tokens and active webhooks are revoked immediately.
            </p>
          </section>

          {/* Section 8 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">8</span>
              Contact Information
            </h2>
            <div className="text-xs bg-surface p-3.5 rounded-lg border border-border font-mono">
              Email: legal@joyplatform.ai<br />
              Entity: JOY SaaS Platform Inc.<br />
              Dhaka, Bangladesh &bull; Global Operations
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-white py-8 mt-16">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted">
          <div className="flex items-center gap-2">
            <span className="font-bold text-foreground">JOY</span>
            <span>&copy; {new Date().getFullYear()} JOY Inc. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/privacy" className="hover:text-foreground transition-colors">
              Privacy Policy
            </Link>
            <Link href="/terms" className="text-foreground font-semibold hover:text-brand-600 transition-colors">
              Terms of Service
            </Link>
            <Link href="/dashboard/integration-hub" className="hover:text-foreground transition-colors">
              Integration Hub
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
