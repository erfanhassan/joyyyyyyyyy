
import React, { useState, useEffect, useRef } from "react";
import { Link } from "wouter";
import {
  Inbox,
  MessageSquare,
  PhoneCall,
  Share2,
  AlertTriangle,
  ShieldAlert,
  Send,
  UserCheck,
  PauseCircle,
  PlayCircle,
  CheckCircle2,
  Lock,
  RefreshCw,
  Search,
  Filter,
  ExternalLink,
  Sparkles,
  ArrowLeft,
  ArrowRight
} from "lucide-react";
import { apiUrl, getWsUrl } from "@/lib/api";

interface ConversationItem {
  id: string;
  channel: string;
  customer_name: string;
  customer_identifier: string;
  sentiment_score: number;
  risk_score: number;
  risk_badge?: "green_safe" | "yellow_warning" | "crimson_alert";
  is_paused_for_human: boolean;
  updated_at?: string;
  latest_message?: string;
}

interface MessageItem {
  id: string;
  sender_type: "customer" | "agent" | "human_operator";
  message_text: string;
  created_at?: string;
  raw_payload?: any;
}

export default function OperatorWorkbenchPage() {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [wsConnected, setWsConnected] = useState(false);
  const [operatorReply, setOperatorReply] = useState("");
  const [aiDraft, setAiDraft] = useState("");
  const [alertBanner, setAlertBanner] = useState<any | null>(null);
  const [simulationStatus, setSimulationStatus] = useState<string | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  const tenantId = "a1e6f58d-b575-420e-b4d6-1fef0064e746";
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch conversations function
  const fetchConversations = () => {
    fetch(apiUrl(`/api/v1/workbench/conversations/${tenantId}`))
      .then((res) => res.json())
      .then((data) => {
        if (data.conversations && data.conversations.length > 0) {
          setConversations(data.conversations);
          if (!selectedConvId) {
            setSelectedConvId(data.conversations[0].id);
          }
        }
      })
      .catch((err) => {
        console.warn("Error fetching conversations:", err);
      });
  };

  // Initial load
  useEffect(() => {
    fetchConversations();
  }, [tenantId]);

  // Connect WebSocket for Real-time Streaming
  useEffect(() => {
    let ws: WebSocket;
    try {
      ws = new WebSocket(getWsUrl(`/ws/workbench/${tenantId}`));
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          if (payload.type === "hitl_alert") {
            setAlertBanner({
              customer: payload.customer_name,
              reason: payload.reason,
              risk: payload.risk_score,
            });
            setConversations((prev) =>
              prev.map((c) =>
                c.id === payload.conversation_id
                  ? {
                      ...c,
                      risk_score: payload.risk_score,
                      sentiment_score: payload.sentiment_score,
                      risk_badge: "crimson_alert",
                      is_paused_for_human: true,
                    }
                  : c
              )
            );
          } else if (payload.type === "takeover_toggled") {
            setConversations((prev) =>
              prev.map((c) =>
                c.id === payload.conversation_id
                  ? { ...c, is_paused_for_human: payload.is_paused_for_human }
                  : c
              )
            );
          } else if (payload.type === "new_message") {
            if (payload.conversation_id === selectedConvId) {
              setMessages((prev) => [
                ...prev,
                {
                  id: `msg-${Date.now()}`,
                  sender_type: payload.sender_type,
                  message_text: payload.message_text,
                },
              ]);
            }
          }
        } catch (e) {
          console.error("WS Parse error", e);
        }
      };

      ws.onclose = () => setWsConnected(false);
    } catch (e) {
      console.warn("WebSocket init failed, falling back to REST");
    }

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [tenantId, selectedConvId]);

  // Load messages for selected conversation
  useEffect(() => {
    if (!selectedConvId) return;

    fetch(apiUrl(`/api/v1/workbench/conversations/${tenantId}/${selectedConvId}/logs`))
      .then((res) => res.json())
      .then((data) => {
        if (data.messages && data.messages.length > 0) {
          setMessages(data.messages);
        } else {
          setMessages([]);
        }
      })
      .catch(() => {
        setMessages([]);
      });

    setAiDraft("Hello, I am checking your order details with the warehouse right now. One moment please.");
  }, [selectedConvId, tenantId]);

  const activeConversation = conversations.find((c) => c.id === selectedConvId) || conversations[0];

  const handleToggleTakeover = async (takeOver: boolean) => {
    if (!activeConversation) return;

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          action: "takeover",
          conversation_id: activeConversation.id,
          take_over: takeOver,
          operator_name: "Store Lead (Tanvir)",
        })
      );
    }

    try {
      await fetch(apiUrl("/api/v1/workbench/takeover"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          conversation_id: activeConversation.id,
          take_over: takeOver,
          operator_name: "Store Lead (Tanvir)",
        }),
      });
    } catch (e) {
      console.warn("REST takeover sync error", e);
    }

    setConversations((prev) =>
      prev.map((c) => (c.id === activeConversation.id ? { ...c, is_paused_for_human: takeOver } : c))
    );
  };

  const handleSendHumanReply = async () => {
    if (!operatorReply.trim() || !activeConversation) return;

    const replyPayload = {
      action: "send_reply",
      conversation_id: activeConversation.id,
      text: operatorReply,
      operator_name: "Store Lead (Tanvir)",
    };

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(replyPayload));
    }

    try {
      await fetch(apiUrl("/api/v1/workbench/reply"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          conversation_id: activeConversation.id,
          message_text: operatorReply,
          operator_name: "Store Lead (Tanvir)",
        }),
      });
    } catch (e) {
      console.warn("REST reply error", e);
    }

    setMessages((prev) => [
      ...prev,
      {
        id: `m-${Date.now()}`,
        sender_type: "human_operator",
        message_text: operatorReply,
      },
    ]);
    setOperatorReply("");
  };

  // --- Interactive Simulation Lab Handlers ---
  const handleSimulateSocialSale = async () => {
    setIsSimulating(true);
    setSimulationStatus("Simulating Instagram Lead & Catalog RAG...");
    try {
      const res = await fetch(apiUrl("/api/v1/widget/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          session_id: `sim_sess_${Date.now()}`,
          customer_id: "ig_shopper_dhaka",
          message: "Hi! Do you have the Mulberry silk Panjabi in stock?",
        }),
      });
      const data = await res.json();
      setSimulationStatus("Success: Employee #1 matched catalog and generated checkout link!");
      fetchConversations();
      if (data.conversation_id) {
        setSelectedConvId(data.conversation_id);
      }
    } catch (e: any) {
      setSimulationStatus("Simulation error: " + e.message);
    } finally {
      setIsSimulating(false);
    }
  };

  const handleSimulateAngryCustomer = async () => {
    setIsSimulating(true);
    setSimulationStatus("Simulating Angry Customer Refund Request...");
    try {
      const res = await fetch(apiUrl("/api/v1/workbench/simulate-sentiment-alert"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          customer_message: "You scammers delivered the wrong size! Cancel this order and refund my money right now!",
          channel: "instagram",
          customer_name: "Sadia (Angry Shopper)",
          customer_identifier: "@sadia_dhaka",
        }),
      });
      const data = await res.json();
      setSimulationStatus("Triggered: Sentiment Risk = 0.85 (Crimson Alert & AI Halted)");
      setAlertBanner({
        customer: "Sadia (Angry Shopper)",
        reason: "Refund/cancellation request detected: cancel, refund",
        risk: 0.85,
      });
      fetchConversations();
      if (data.conversation_id) {
        setSelectedConvId(data.conversation_id);
      }
    } catch (e: any) {
      setSimulationStatus("Simulation error: " + e.message);
    } finally {
      setIsSimulating(false);
    }
  };

  const handleSimulateVoiceCall = async () => {
    setIsSimulating(true);
    setSimulationStatus("Simulating Automated Phone Confirmation Call...");
    try {
      const callId = `call_${Math.random().toString(36).substring(7)}`;
      const res = await fetch(apiUrl("/api/v1/webhooks/telephony/completion"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          call_id: callId,
          customer_phone: "+8801712345678",
          confirmed: true,
          transcript: "Agent: Hi Rahim, calling from Joy Store to verify your delivery address to Banani, Dhaka.\nCustomer: Yes, please deliver to Road 11, House 42.\nAgent: Address verified and order confirmed!",
          sentiment_score: 0.95,
        }),
      });
      setSimulationStatus("Success: Employee #2 completed outbound call & synced order!");
      fetchConversations();
    } catch (e: any) {
      setSimulationStatus("Simulation error: " + e.message);
    } finally {
      setIsSimulating(false);
    }
  };

  const filteredConversations = conversations.filter((c) => {
    if (channelFilter === "all") return true;
    return c.channel.toLowerCase().includes(channelFilter);
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Status & Controls */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100 text-xs font-semibold mb-2">
            <span>Step 4 of 4</span>
            <span>&bull;</span>
            <span>24/7 Live Operations Desk</span>
          </div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Operator Desk (Unified Inbox)
            </h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100 flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? "bg-brand-600 animate-pulse" : "bg-warning"}`} />
              {wsConnected ? "WebSocket Live" : "Polling Active"}
            </span>
          </div>
          <p className="text-sm text-muted mt-1">
            Real-time multi-channel messaging stream with sentiment alerts and 1-click human takeover.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 bg-white p-1 rounded-lg border border-border text-xs">
          {["all", "instagram", "facebook", "widget", "phone"].map((ch) => (
            <button
              key={ch}
              onClick={() => setChannelFilter(ch)}
              className={`px-3 py-1.5 rounded-md font-medium capitalize transition-colors ${
                channelFilter === ch ? "bg-foreground text-white shadow-sm" : "text-muted hover:text-foreground"
              }`}
            >
              {ch === "widget" ? "Web Chat" : ch === "phone" ? "Voice Calls" : ch}
            </button>
          ))}
        </div>
      </div>

      {/* Interactive Simulation Lab Bar */}
      <div className="bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-700">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-foreground">Interactive Test &amp; Scenario Simulator</h3>
              <p className="text-[11px] text-muted">
                Test your autonomous digital staff and experience real-time sentiment alerts with 1-click simulations.
              </p>
            </div>
          </div>
          {simulationStatus && (
            <span className="text-[11px] font-semibold text-brand-700 bg-brand-50 border border-brand-100 px-2.5 py-1 rounded-full animate-in fade-in">
              {simulationStatus}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
          {/* Simulator 1: Social Sales */}
          <button
            onClick={handleSimulateSocialSale}
            disabled={isSimulating}
            className="p-3 rounded-lg bg-surface hover:bg-surface-hover border border-border text-left transition-all group flex items-start gap-2.5"
          >
            <div className="w-7 h-7 rounded-md bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600 flex-shrink-0 mt-0.5">
              <MessageSquare className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-bold text-foreground group-hover:text-brand-700 flex items-center gap-1">
                <span>1. Test Social Lead (Employee #1)</span>
              </div>
              <p className="text-[11px] text-muted mt-0.5 leading-snug">
                Simulate Instagram shopper asking for silk Panjabi pricing &amp; checkout link.
              </p>
            </div>
          </button>

          {/* Simulator 2: Crimson Alert */}
          <button
            onClick={handleSimulateAngryCustomer}
            disabled={isSimulating}
            className="p-3 rounded-lg bg-surface hover:bg-surface-hover border border-border text-left transition-all group flex items-start gap-2.5"
          >
            <div className="w-7 h-7 rounded-md bg-alert-light border border-alert/30 flex items-center justify-center text-alert flex-shrink-0 mt-0.5">
              <ShieldAlert className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-bold text-foreground group-hover:text-alert flex items-center gap-1">
                <span>2. Test Crimson Risk Takeover</span>
              </div>
              <p className="text-[11px] text-muted mt-0.5 leading-snug">
                Simulate angry refund demand (Risk &gt; 0.70) to trigger AI halt and Crimson alert.
              </p>
            </div>
          </button>

          {/* Simulator 3: Voice Confirmation */}
          <button
            onClick={handleSimulateVoiceCall}
            disabled={isSimulating}
            className="p-3 rounded-lg bg-surface hover:bg-surface-hover border border-border text-left transition-all group flex items-start gap-2.5"
          >
            <div className="w-7 h-7 rounded-md bg-brand-50 border border-brand-100 flex items-center justify-center text-brand-600 flex-shrink-0 mt-0.5">
              <PhoneCall className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-bold text-foreground group-hover:text-brand-700 flex items-center gap-1">
                <span>3. Test Phone Order (Employee #2)</span>
              </div>
              <p className="text-[11px] text-muted mt-0.5 leading-snug">
                Simulate automated outbound call verifying customer delivery address.
              </p>
            </div>
          </button>
        </div>
      </div>

      {/* HITL Sentiment Interrupt Banner */}
      {alertBanner && (
        <div className="p-4 rounded-xl bg-alert-light border border-alert/30 text-alert-dark flex items-center justify-between animate-in slide-in-from-top-2 duration-200">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-alert text-white flex items-center justify-center font-bold text-xs flex-shrink-0">
              !
            </div>
            <div>
              <h4 className="text-xs font-bold text-alert">
                Human-In-The-Loop Sentiment Alert (Risk: {alertBanner.risk})
              </h4>
              <p className="text-xs text-alert-dark mt-0.5">
                Customer: <strong>{alertBanner.customer}</strong> &bull; {alertBanner.reason}
              </p>
            </div>
          </div>
          <button
            onClick={() => setAlertBanner(null)}
            className="text-xs font-semibold px-3 py-1 bg-alert text-white rounded-lg hover:bg-alert-dark transition-colors shadow-sm"
          >
            Acknowledge
          </button>
        </div>
      )}

      {/* Main Inbox Workspace (3 Panes) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 bg-white border border-border rounded-xl shadow-sm overflow-hidden min-h-[640px]">
        {/* Left Pane: Conversation List (4 Cols) */}
        <div className="lg:col-span-4 border-r border-border flex flex-col justify-between">
          <div>
            <div className="p-4 border-b border-border bg-surface flex items-center justify-between">
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider">
                Active Conversations ({filteredConversations.length})
              </h3>
              <button
                onClick={fetchConversations}
                className="text-muted hover:text-foreground p-1 transition-colors"
                title="Refresh Conversations"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="divide-y divide-border overflow-y-auto max-h-[560px]">
              {filteredConversations.map((conv) => {
                const isSelected = conv.id === selectedConvId;
                const badgeColor =
                  conv.risk_score > 0.70
                    ? "bg-alert-light text-alert border-alert/30"
                    : conv.risk_score >= 0.40
                    ? "bg-warning-light text-warning-dark border-warning/30"
                    : "bg-brand-50 text-brand-700 border-brand-100";

                return (
                  <div
                    key={conv.id}
                    onClick={() => setSelectedConvId(conv.id)}
                    className={`p-4 cursor-pointer transition-colors ${
                      isSelected ? "bg-surface" : "hover:bg-surface/50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-foreground">{conv.customer_name}</span>
                        <span className="text-[10px] text-muted">({conv.channel})</span>
                      </div>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeColor}`}>
                        {conv.risk_score > 0.70 ? "CRIMSON ALERT" : conv.risk_score >= 0.40 ? "WARNING" : "SAFE"}
                      </span>
                    </div>

                    <p className="text-xs text-muted truncate">
                      {conv.latest_message || "Active customer communication stream"}
                    </p>

                    <div className="mt-2 flex items-center justify-between text-[11px]">
                      <span className="font-mono text-muted">Risk: {conv.risk_score}</span>
                      {conv.is_paused_for_human ? (
                        <span className="text-alert font-bold flex items-center gap-1">
                          <Lock className="w-3 h-3" /> Human Takeover
                        </span>
                      ) : (
                        <span className="text-brand-700 font-semibold flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> AI Active
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Center Pane: Live Stream & Chat (5 Cols) */}
        <div className="lg:col-span-5 border-r border-border flex flex-col justify-between">
          <div>
            {/* Conversation Header */}
            <div className="p-4 border-b border-border bg-surface flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-foreground">
                  {activeConversation?.customer_name || "Conversation"}
                </h3>
                <p className="text-[11px] text-muted">{activeConversation?.customer_identifier}</p>
              </div>

              {activeConversation?.is_paused_for_human ? (
                <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-alert-light text-alert border border-alert/30">
                  Human Control Active
                </span>
              ) : (
                <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                  Autonomous AI Active
                </span>
              )}
            </div>

            {/* Message Stream */}
            <div className="p-4 space-y-3 overflow-y-auto max-h-[460px]">
              {messages.map((m) => {
                const isCustomer = m.sender_type === "customer";
                const isHuman = m.sender_type === "human_operator";

                return (
                  <div
                    key={m.id}
                    className={`flex flex-col ${isCustomer ? "items-start" : "items-end"}`}
                  >
                    <span className="text-[10px] text-muted mb-0.5 font-medium">
                      {isCustomer ? activeConversation?.customer_name : isHuman ? "You (Human Operator)" : "Joy Digital Employee"}
                    </span>
                    <div
                      className={`max-w-[85%] p-3 rounded-xl text-xs leading-relaxed ${
                        isCustomer
                          ? "bg-surface text-foreground border border-border"
                          : isHuman
                          ? "bg-foreground text-white"
                          : "bg-brand-50 text-brand-900 border border-brand-100"
                      }`}
                    >
                      {m.message_text}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Operator Reply Input */}
          <div className="p-4 border-t border-border bg-white">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={operatorReply}
                onChange={(e) => setOperatorReply(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendHumanReply()}
                placeholder={
                  activeConversation?.is_paused_for_human
                    ? "Type human response to customer..."
                    : "Take over to type directly to customer..."
                }
                className="flex-1 px-3 py-2 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground"
              />
              <button
                onClick={handleSendHumanReply}
                disabled={!operatorReply.trim()}
                className="p-2 bg-foreground text-white rounded-lg hover:bg-foreground/90 disabled:opacity-40 transition-colors shadow-sm"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Right Pane: Sentiment & Takeover Controls (3 Cols) */}
        <div className="lg:col-span-3 p-4 flex flex-col justify-between bg-surface/50">
          <div className="space-y-6">
            <div>
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider mb-3">
                Sentiment &amp; Risk Guardrails
              </h3>

              <div className="space-y-3 bg-white p-3.5 rounded-xl border border-border text-xs">
                <div>
                  <div className="flex items-center justify-between text-muted mb-1">
                    <span>Sentiment Score</span>
                    <span className="font-semibold text-foreground">
                      {Math.round((activeConversation?.sentiment_score ?? 0.8) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-surface rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-600 rounded-full"
                      style={{ width: `${(activeConversation?.sentiment_score ?? 0.8) * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-muted mb-1">
                    <span>Intervention Risk</span>
                    <span className={`font-semibold ${activeConversation?.risk_score && activeConversation.risk_score > 0.70 ? "text-alert" : "text-foreground"}`}>
                      {Math.round((activeConversation?.risk_score ?? 0.2) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-surface rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        activeConversation?.risk_score && activeConversation.risk_score > 0.70
                          ? "bg-alert"
                          : activeConversation?.risk_score && activeConversation.risk_score >= 0.40
                          ? "bg-warning"
                          : "bg-brand-600"
                      }`}
                      style={{ width: `${(activeConversation?.risk_score ?? 0.2) * 100}%` }}
                    />
                  </div>
                </div>

                <div className="pt-2 border-t border-border/60 text-[11px] text-muted">
                  <span>Halt Threshold: </span>
                  <span className="font-mono font-semibold text-foreground">Risk &gt; 0.70</span>
                </div>
              </div>
            </div>

            {/* Takeover Toggle Action */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                Operator Action
              </h4>

              {activeConversation?.is_paused_for_human ? (
                <button
                  onClick={() => handleToggleTakeover(false)}
                  className="w-full py-2.5 px-3 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-bold transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                >
                  <PlayCircle className="w-4 h-4" />
                  <span>Resume Autonomous AI</span>
                </button>
              ) : (
                <button
                  onClick={() => handleToggleTakeover(true)}
                  className="w-full py-2.5 px-3 bg-alert hover:bg-alert-dark text-white rounded-lg text-xs font-bold transition-colors flex items-center justify-center gap-1.5 shadow-sm"
                >
                  <PauseCircle className="w-4 h-4" />
                  <span>Take Over Conversation</span>
                </button>
              )}
            </div>

            {/* Live AI Draft Inspector & Editor */}
            <div className="bg-white p-4 rounded-xl border border-border shadow-sm space-y-2">
              <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                Live Employee Draft
              </h4>
              <p className="text-[11px] text-muted">
                Inspect or edit what the digital employee prepared before transmission.
              </p>

              <textarea
                value={aiDraft}
                onChange={(e) => setAiDraft(e.target.value)}
                rows={3}
                className="w-full p-2.5 text-xs bg-surface border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-foreground font-sans leading-relaxed"
              />

              <button
                onClick={() => {
                  setOperatorReply(aiDraft);
                  handleToggleTakeover(true);
                }}
                className="w-full py-2 px-3 bg-surface hover:bg-surface-hover text-foreground rounded-lg text-xs font-semibold border border-border transition-colors"
              >
                Use Draft &amp; Take Over
              </button>
            </div>
          </div>

          <div className="pt-4 border-t border-border text-[11px] text-muted flex items-center justify-between">
            <span>Human-In-The-Loop (HITL)</span>
            <span className="font-semibold text-foreground">Active Policy</span>
          </div>
        </div>
      </div>

      {/* Workflow Complete Navigation Footer */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm flex items-center justify-between flex-wrap gap-4">
        <Link
          href="/dashboard/employee-roster"
          className="px-4 py-2.5 rounded-lg bg-surface border border-border text-foreground font-semibold text-xs hover:bg-white transition-colors shadow-sm flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Step 3: Staff Guardrails</span>
        </Link>

        <div className="text-left sm:text-right">
          <div className="flex items-center sm:justify-end gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-600 animate-pulse" />
            <h3 className="text-sm font-bold text-foreground">Workflow Active: Digital Workforce On Duty 24/7</h3>
          </div>
          <p className="text-xs text-muted mt-0.5">
            Your sales channels, catalog brain, guardrails, and operator desk are operating together.
          </p>
        </div>

        <Link
          href="/dashboard/integration-hub"
          className="px-5 py-2.5 rounded-lg bg-surface border border-border text-foreground font-semibold text-xs hover:bg-surface-hover transition-colors shadow-sm flex items-center gap-1.5"
        >
          <span>Review Store Integrations (Step 1)</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}
