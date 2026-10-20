import React from "react";
import { Link } from "wouter";
import { Shield, ArrowLeft, Lock, FileText, CheckCircle2 } from "lucide-react";

export const metadata = {
  title: "Privacy Policy | JOY Digital Workforce",
  description: "Privacy Policy and Meta Platform Compliance documentation for JOY.",
};

export default function PrivacyPolicyPage() {
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
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold">
            <Shield className="w-3.5 h-3.5" />
            <span>Meta Platform &amp; GDPR Compliant Privacy Policy</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-foreground tracking-tight">
            Privacy Policy
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
              Introduction &amp; Overview
            </h2>
            <p>
              JOY (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) provides an autonomous multi-tenant AI workforce platform designed for retail, e-commerce stores, and digital merchants. This Privacy Policy details how we collect, store, process, and protect your information, as well as the data received from third-party social platforms including Meta Platforms, Inc. (Facebook, Instagram, and WhatsApp), Shopify, and WooCommerce.
            </p>
          </section>

          {/* Section 2 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">2</span>
              Information We Collect &amp; Process
            </h2>
            <p>
              When you use JOY to automate customer sales and order verification, we collect and process the following categories of data:
            </p>
            <ul className="list-disc pl-5 space-y-2 text-zinc-600">
              <li>
                <strong>Merchant Account Details:</strong> Store name, operational currency, business contact information, and account authentication credentials.
              </li>
              <li>
                <strong>Meta Platform Data:</strong> In accordance with the Meta Developer Terms, when you authorize JOY via Facebook Login for Business, we access your Facebook Page details, connected Instagram Professional Account IDs, Page Access Tokens, public post/Reel comments, and direct messages (Messenger and Instagram Direct) solely to automate customer inquiries and lead conversions.
              </li>
              <li>
                <strong>Storefront &amp; Order Data:</strong> Customer names, delivery addresses, product selections, and cash-on-delivery (COD) totals synced via Shopify or WooCommerce webhooks.
              </li>
              <li>
                <strong>Voice Telephony Data:</strong> Phone numbers and call transcripts generated during automated outbound order verification calls conducted by Employee #2 via LiveKit and SIP telephony providers.
              </li>
            </ul>
          </section>

          {/* Section 3 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">3</span>
              Security &amp; Envelope Encryption Guarantee
            </h2>
            <div className="p-4 rounded-xl bg-surface border border-border space-y-2">
              <div className="flex items-center gap-2 font-bold text-foreground">
                <Lock className="w-4 h-4 text-brand-600" />
                <span>AES-256 Fernet Token Vault</span>
              </div>
              <p className="text-xs text-muted leading-relaxed">
                All third-party access credentials—including Meta Page Access Tokens, Shopify API Secrets, and WooCommerce Webhook Keys—are encrypted using authenticated AES-256 Fernet envelope encryption prior to persistence. Secret keys are never exposed in plaintext logs, client-side bundles, or unauthenticated database reads. Multi-tenant database isolation ensures strict tenant partition privacy.
              </p>
            </div>
          </section>

          {/* Section 4 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">4</span>
              How We Use Social &amp; Messaging Data
            </h2>
            <p>
              We adhere strictly to Meta&apos;s Platform Terms and Commercial Terms. Social platform data accessed through Meta Graph APIs is used exclusively to:
            </p>
            <ul className="list-disc pl-5 space-y-1.5 text-zinc-600">
              <li>Respond directly to customer comments and direct messages on your authorized Facebook Pages and Instagram accounts.</li>
              <li>Facilitate the standard 24-hour Meta messaging handshake to answer customer product questions and confirm purchase intent.</li>
              <li>Perform real-time sentiment analysis to alert human operators when customer dissatisfaction or high-risk queries are detected.</li>
            </ul>
            <p className="font-semibold text-foreground mt-2">
              We never sell, rent, or monetize your customer data or Meta Graph API data to third-party data brokers or advertising networks.
            </p>
          </section>

          {/* Section 5 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">5</span>
              Data Deletion Instructions (Meta Compliance)
            </h2>
            <p>
              In compliance with the Meta Platform Policy for User Data Deletion, you have the right to request deletion of any data associated with your Facebook or Instagram account at any time:
            </p>
            <div className="p-4 rounded-xl bg-surface border border-border space-y-2 text-xs">
              <p>
                <strong>Option A (Automated in Dashboard):</strong> Navigate to <em>Integration Hub</em> &rarr; Click <em>Disconnect</em> on the Meta Business card. This immediately purges all encrypted tokens and associated webhook subscriptions from PostgreSQL.
              </p>
              <p>
                <strong>Option B (Direct Request):</strong> To request full deletion of all historical conversation logs and order records, send an email to <span className="font-mono text-foreground font-semibold">privacy@joyplatform.ai</span> with your Tenant ID. All associated tenant records will be purged within 48 hours.
              </p>
            </div>
          </section>

          {/* Section 6 */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-surface border border-border flex items-center justify-center text-xs">6</span>
              Contact Us
            </h2>
            <p>
              If you have any questions about this Privacy Policy or wish to exercise your data privacy rights, please contact our data protection team:
            </p>
            <div className="text-xs bg-surface p-3.5 rounded-lg border border-border font-mono">
              Email: privacy@joyplatform.ai<br />
              Legal Entity: JOY Platform SaaS Inc.<br />
              Location: Dhaka, Bangladesh &bull; Global Cloud Operations
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
            <Link href="/privacy" className="text-foreground font-semibold hover:text-brand-600 transition-colors">
              Privacy Policy
            </Link>
            <Link href="/terms" className="hover:text-foreground transition-colors">
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
