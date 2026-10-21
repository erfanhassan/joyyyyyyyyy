import React, { useState, useEffect, useRef } from "react";
import { Link } from "wouter";
import {
  Brain,
  UploadCloud,
  Globe,
  FileText,
  Search,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Trash2,
  Database,
  ShieldCheck,
  ArrowRight,
  ArrowLeft,
  Info,
} from "lucide-react";
import { apiUrl } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

interface DocumentItem {
  id: string;
  title: string;
  sourceType: string;
  sourceUrl?: string;
  chunksCount: number;
  createdAt: string;
  status: string;
}

export default function KnowledgeBrainPage() {
  const { tenant } = useTenant();
  const tenantId = tenant?.id || "a1e6f58d-b575-420e-b4d6-1fef0064e746";

  const [crawlUrl, setCrawlUrl] = useState("https://mystore.com");
  const [isCrawling, setIsCrawling] = useState(false);
  const [crawlStatus, setCrawlStatus] = useState<string | null>(null);
  const [crawlError, setCrawlError] = useState<string | null>(null);

  const [testQuery, setTestQuery] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryResults, setQueryResults] = useState<any[] | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(true);

  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      setIsLoadingDocs(true);
      const res = await fetch(apiUrl(`/api/v1/knowledge/documents?tenant_id=${tenantId}`));
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (e: any) {
      console.error("Failed to load documents:", e);
    } finally {
      setIsLoadingDocs(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [tenantId]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadStatus(`Parsing and embedding ${file.name}...`);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("tenant_id", tenantId);

    try {
      const res = await fetch(apiUrl("/api/v1/knowledge/upload"), {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Upload failed with status ${res.status}`);
      }

      setUploadStatus(`Indexed ${file.name} successfully into ${data.chunks_count || 1} vector chunks!`);
      await fetchDocuments();
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload document");
      setUploadStatus(null);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!confirm("Are you sure you want to remove this document from the Knowledge Brain?")) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/knowledge/documents/${docId}?tenant_id=${tenantId}`), {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchDocuments();
      } else {
        const data = await res.json();
        alert(data.detail || "Failed to delete document");
      }
    } catch (err: any) {
      alert("Error deleting document: " + err.message);
    }
  };

  const handleCrawl = async () => {
    if (!crawlUrl) return;
    setIsCrawling(true);
    setCrawlStatus("Crawling storefront and extracting catalog text...");
    setCrawlError(null);

    try {
      const res = await fetch(apiUrl("/api/v1/knowledge/crawl"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: crawlUrl,
          tenant_id: tenantId,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Crawl failed with status ${res.status}`);
      }

      setCrawlStatus(`Success! Crawled and indexed ${data.chunks_count || data.chunks_stored || 1} vector chunks.`);
      await fetchDocuments();
    } catch (e: any) {
      setCrawlError(e.message || "Crawl failed. Ensure the URL is publicly reachable.");
      setCrawlStatus(null);
    } finally {
      setIsCrawling(false);
    }
  };

  const handleTestQuery = async () => {
    if (!testQuery) return;
    setIsQuerying(true);
    setQueryError(null);
    setQueryResults(null);

    try {
      const res = await fetch(apiUrl("/api/v1/knowledge/query"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: testQuery,
          tenant_id: tenantId,
          top_k: 3,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Query failed");
      }

      const results = data.results || data.snippets || [];
      setQueryResults(results);
    } catch (e: any) {
      setQueryError(e.message || "Failed to retrieve knowledge snippets.");
    } finally {
      setIsQuerying(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 text-xs font-semibold mb-2">
          <span>Step 2 of 4</span>
          <span>&bull;</span>
          <span>Catalog Ingestion &amp; Staff Training</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Employee Training (Knowledge Brain)
        </h1>
        <p className="text-sm text-muted mt-1">
          Upload product price sheets, size guides, and storefront URLs. JOY indexes your business knowledge for conversational sales, policy checks, and accurate customer guidance.
        </p>
      </div>

      {/* Notice on Knowledge vs Live Store Inventory */}
      <div className="p-3.5 bg-blue-50/60 border border-blue-200 rounded-xl text-xs text-blue-900 flex items-start gap-2.5">
        <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
        <div>
          <span className="font-semibold">Knowledge Brain vs. Live Store Inventory: </span>
          Knowledge documents train the AI on product descriptions, return terms, and FAQs. Authoritative real-time variant stock, pricing, and order creation are synced directly via Shopify or WooCommerce store integrations.
        </div>
      </div>

      {/* Grid: Uploader & Crawler */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* File Drag-and-Drop Uploader */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <UploadCloud className="w-5 h-5 text-brand-600" />
              <h2 className="text-base font-bold text-foreground">Upload Catalogs &amp; Documents</h2>
            </div>
            <p className="text-xs text-muted mb-4">
              Upload PDF brochures, CSV price books, or return policies. Text is recursively chunked (500 tokens / 50 overlap) with pgvector HNSW indexing.
            </p>

            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".pdf,.csv,.txt,.md"
              className="hidden"
            />

            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) {
                  const fakeEvent = {
                    target: { files: e.dataTransfer.files },
                  } as any;
                  handleFileUpload(fakeEvent);
                }
              }}
              className="border-2 border-dashed border-border hover:border-foreground/30 rounded-xl p-8 text-center bg-surface transition-colors cursor-pointer group"
            >
              <div className="w-12 h-12 rounded-full bg-white border border-border flex items-center justify-center mx-auto mb-3 shadow-sm group-hover:scale-105 transition-transform">
                <FileText className="w-6 h-6 text-brand-600" />
              </div>
              <p className="text-xs font-semibold text-foreground">
                {isUploading ? "Uploading & Generating Embeddings..." : "Click to browse or drag and drop files here"}
              </p>
              <p className="text-[11px] text-muted mt-1">
                Supports PDF catalogs, CSV inventories, TXT, and Markdown files up to 25MB
              </p>
            </div>

            {uploadStatus && (
              <div className="mt-3 p-3 bg-brand-50 border border-brand-100 rounded-lg text-xs text-brand-900 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-brand-600 flex-shrink-0" />
                <span>{uploadStatus}</span>
              </div>
            )}

            {uploadError && (
              <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}
          </div>

          <div className="mt-4 pt-4 border-t border-border flex items-center justify-between text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-brand-600" />
              <span>HNSW Vector Indexing Active</span>
            </span>
            <span className="font-semibold text-foreground">1536-dim Embeddings</span>
          </div>
        </div>

        {/* Website Crawler */}
        <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Globe className="w-5 h-5 text-brand-600" />
              <h2 className="text-base font-bold text-foreground">Storefront Web Crawler</h2>
            </div>
            <p className="text-xs text-muted mb-4">
              Scrape product stories, FAQs, and return terms directly from your public website URL for conversational context.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-foreground">Storefront URL</label>
                <input
                  type="url"
                  value={crawlUrl}
                  onChange={(e) => setCrawlUrl(e.target.value)}
                  placeholder="https://yourstore.com"
                  className="w-full mt-1.5 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground font-mono"
                />
              </div>

              <button
                onClick={handleCrawl}
                disabled={isCrawling || !crawlUrl}
                className="w-full py-2.5 px-4 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors flex items-center justify-center gap-2 shadow-sm disabled:opacity-60"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isCrawling ? "animate-spin" : ""}`} />
                <span>{isCrawling ? "Crawling & Vector Indexing..." : "Crawl & Train Employees"}</span>
              </button>

              {crawlStatus && (
                <div className="p-3 bg-brand-50 border border-brand-100 rounded-lg text-xs text-brand-900 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-brand-600 flex-shrink-0" />
                  <span>{crawlStatus}</span>
                </div>
              )}

              {crawlError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                  <span>{crawlError}</span>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-border flex items-center justify-between text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-brand-600" />
              <span>Multi-Tenant RLS Isolated</span>
            </span>
            <span className="font-semibold text-foreground">Zero Cross-Store Leaks</span>
          </div>
        </div>
      </div>

      {/* Interactive Staff Knowledge Query Tester */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Search className="w-5 h-5 text-brand-600" />
          <h2 className="text-base font-bold text-foreground">Test Staff Knowledge (Hybrid RAG)</h2>
        </div>
        <p className="text-xs text-muted mb-4">
          Ask questions in natural language to test the hybrid retrieval engine combining PostgreSQL full-text search (BM25) and pgvector cosine similarity.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={testQuery}
            onChange={(e) => setTestQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleTestQuery()}
            placeholder="e.g., What is our return and exchange policy for nationwide deliveries?"
            className="flex-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
          />
          <button
            onClick={handleTestQuery}
            disabled={isQuerying || !testQuery}
            className="px-4 py-2 bg-foreground text-white rounded-lg text-xs font-semibold hover:bg-foreground/90 transition-colors flex items-center gap-1.5 shadow-sm disabled:opacity-60"
          >
            {isQuerying ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            <span>Query Brain</span>
          </button>
        </div>

        {/* Query Error */}
        {queryError && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{queryError}</span>
          </div>
        )}

        {/* Results */}
        {queryResults !== null && (
          <div className="mt-4 space-y-3">
            <div className="text-xs font-semibold text-foreground uppercase tracking-wider">
              Retrieved Context Snippets ({queryResults.length} found):
            </div>
            {queryResults.length === 0 ? (
              <p className="text-xs text-muted py-3">No matching knowledge snippets found in your catalog for this query.</p>
            ) : (
              queryResults.map((res, i) => (
                <div key={i} className="p-3.5 rounded-lg bg-surface border border-border text-xs space-y-2">
                  <div className="flex items-center justify-between text-muted text-[11px]">
                    <span className="font-semibold text-foreground">
                      Snippet #{i + 1} {res.document_title ? `• ${res.document_title}` : ""}
                    </span>
                    <div className="flex items-center gap-3 font-mono">
                      <span>Score: <strong className="text-brand-700">{res.hybrid_score !== undefined ? Number(res.hybrid_score).toFixed(2) : (res.combined_score || "N/A")}</strong></span>
                      {res.vector_similarity !== undefined && (
                        <span>Vector: {Number(res.vector_similarity).toFixed(2)}</span>
                      )}
                      {res.text_rank !== undefined && (
                        <span>BM25: {Number(res.text_rank).toFixed(2)}</span>
                      )}
                    </div>
                  </div>
                  <p className="text-foreground leading-relaxed font-sans">{res.content}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Indexed Documents Table */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-foreground">Training Materials Library</h2>
            <p className="text-xs text-muted">Authoritative knowledge documents stored and indexed for this workspace.</p>
          </div>
          <button
            onClick={fetchDocuments}
            disabled={isLoadingDocs}
            className="p-1.5 text-muted hover:text-foreground rounded-lg hover:bg-surface transition-colors"
            title="Refresh documents"
          >
            <RefreshCw className={`w-4 h-4 ${isLoadingDocs ? "animate-spin" : ""}`} />
          </button>
        </div>

        {isLoadingDocs ? (
          <div className="py-8 text-center text-xs text-muted flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-brand-600" />
            <span>Loading training materials...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="py-8 text-center">
            <Brain className="w-8 h-8 text-muted/40 mx-auto mb-2" />
            <p className="text-xs font-semibold text-foreground">No knowledge documents indexed yet</p>
            <p className="text-[11px] text-muted mt-1 max-w-sm mx-auto">
              Upload PDF price sheets, policies, or crawl your website to train your AI employees on your product offerings.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {documents.map((doc) => (
              <div key={doc.id} className="py-3 flex items-center justify-between gap-4 first:pt-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-surface border border-border flex items-center justify-center flex-shrink-0">
                    {doc.sourceType === "pdf" ? (
                      <FileText className="w-4 h-4 text-brand-600" />
                    ) : (
                      <Globe className="w-4 h-4 text-foreground" />
                    )}
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">{doc.title}</h4>
                    <p className="text-[11px] text-muted">{doc.chunksCount} chunks &bull; {doc.createdAt}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                    {doc.status}
                  </span>
                  <button
                    onClick={() => handleDeleteDocument(doc.id)}
                    className="p-1.5 text-muted hover:text-red-600 rounded-md hover:bg-red-50 transition-colors"
                    title="Delete document"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Workflow Navigation Footer */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex items-center justify-between flex-wrap gap-4">
        <Link
          href="/dashboard/integration-hub"
          className="px-4 py-2.5 rounded-lg bg-surface border border-border text-foreground font-semibold text-xs hover:bg-white transition-colors shadow-sm flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Step 1: Connect Stores</span>
        </Link>

        <div className="text-left sm:text-right">
          <div className="flex items-center sm:justify-end gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-600" />
            <h3 className="text-sm font-bold text-foreground">Step 2 Complete: Brain Knowledge Indexed</h3>
          </div>
          <p className="text-xs text-muted mt-0.5">
            Next, configure discount caps, tone of voice, and daytime calling hours.
          </p>
        </div>

        <Link
          href="/dashboard/employee-roster"
          className="px-5 py-2.5 rounded-lg bg-brand-600 text-white font-semibold text-xs hover:bg-brand-700 transition-colors shadow-sm flex items-center gap-1.5"
        >
          <span>Proceed to Step 3: Staff Guardrails</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}
