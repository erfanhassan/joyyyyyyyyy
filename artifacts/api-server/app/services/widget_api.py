import json
import logging
import uuid
from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Conversation, InteractionLog

logger = logging.getLogger("joy.widget_api")


class WidgetAPIService:
    """
    Service backing the Universal JavaScript Web Embed Widget (widget.js):
    - Manages live chat conversations in PostgreSQL
    - Records customer and AI interaction logs
    - Serves the standalone, embeddable widget.js script
    """

    @staticmethod
    async def get_or_create_conversation(
        db: AsyncSession,
        tenant_id: UUID,
        customer_identifier: str,
        customer_name: str = "Web Visitor",
    ) -> Conversation:
        """Find active web chat conversation or create a new one."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_identifier == customer_identifier,
                Conversation.channel == "web_widget",
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        conv = result.scalars().first()

        if not conv:
            conv = Conversation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                channel="web_widget",
                customer_identifier=customer_identifier,
                customer_name=customer_name,
                sentiment_score=1.0,
                risk_score=0.0,
                is_paused_for_human=False,
            )
            db.add(conv)
            await db.commit()
            await db.refresh(conv)

        return conv

    @staticmethod
    async def log_message(
        db: AsyncSession,
        tenant_id: UUID,
        conversation_id: UUID,
        sender_type: str,
        message_text: str,
        raw_payload: Dict[str, Any] = None,
    ) -> InteractionLog:
        """Log an incoming or outgoing message in interaction_logs."""
        log_entry = InteractionLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            sender_type=sender_type,
            message_text=message_text,
            raw_payload=raw_payload or {},
        )
        db.add(log_entry)
        await db.commit()
        return log_entry

    @staticmethod
    def generate_embed_script(backend_base_url: str) -> str:
        """
        Generates the standalone widget.js embed script.
        Adheres to pure white minimalist design (Emerald Forest #059669 accents, zero blue/purple).
        """
        return f"""(function() {{
  if (window.JoyWidgetLoaded) return;
  window.JoyWidgetLoaded = true;

  var scriptTag = document.currentScript || (function() {{
    var scripts = document.getElementsByTagName('script');
    for (var i = scripts.length - 1; i >= 0; i--) {{
      if (scripts[i].getAttribute('data-tenant-id') || (scripts[i].src && scripts[i].src.indexOf('widget.js') !== -1)) {{
        return scripts[i];
      }}
    }}
    return scripts[scripts.length - 1];
  }})();

  var tenantId = (scriptTag && scriptTag.getAttribute('data-tenant-id')) || '';
  if (!tenantId && scriptTag && scriptTag.src) {{
    try {{
      var urlParams = new URL(scriptTag.src).searchParams;
      tenantId = urlParams.get('tenant_id') || '';
    }} catch (e) {{}}
  }}

  var apiBase = '{backend_base_url}';
  var visitorId = localStorage.getItem('joy_visitor_id') || ('v_' + Math.random().toString(36).substr(2, 9));
  localStorage.setItem('joy_visitor_id', visitorId);

  // Helper: Escape HTML to prevent XSS
  function escapeHtml(str) {{
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }}

  // 1. Inject Styles
  var style = document.createElement('style');
  style.innerHTML = `
    .joy-widget-btn {{
      position: fixed; bottom: 24px; right: 24px; width: 56px; height: 56px;
      border-radius: 28px; background: #059669; color: #ffffff; border: none;
      box-shadow: 0 4px 14px rgba(5, 150, 105, 0.35); cursor: pointer; z-index: 999998;
      display: flex; align-items: center; justify-content: center; transition: all 0.2s ease;
    }}
    .joy-widget-btn:hover {{ transform: scale(1.05); background: #047857; }}
    .joy-chat-panel {{
      position: fixed; bottom: 92px; right: 24px; width: 380px; max-width: calc(100vw - 48px);
      height: 520px; max-height: calc(100vh - 120px); background: #ffffff;
      border-radius: 20px; box-shadow: 0 12px 36px rgba(0,0,0,0.12); border: 1px solid #E4E4E7;
      display: none; flex-direction: column; overflow: hidden; z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .joy-chat-header {{
      padding: 16px 20px; background: #FAFAF9; border-bottom: 1px solid #E4E4E7;
      display: flex; align-items: center; justify-content: space-between;
    }}
    .joy-header-title {{ font-weight: 700; font-size: 15px; color: #18181B; display: flex; align-items: center; gap: 8px; }}
    .joy-status-dot {{ width: 8px; height: 8px; border-radius: 4px; background: #10B981; display: inline-block; }}
    .joy-chat-body {{ flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; background: #FAFAF9; }}
    .joy-msg {{ max-width: 82%; padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.4; word-break: break-word; }}
    .joy-msg-agent {{ background: #ffffff; color: #18181B; align-self: flex-start; border: 1px solid #E4E4E7; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }}
    .joy-msg-customer {{ background: #059669; color: #ffffff; align-self: flex-end; }}
    .joy-chat-footer {{ padding: 12px 16px; background: #ffffff; border-top: 1px solid #E4E4E7; display: flex; gap: 8px; }}
    .joy-input {{ flex: 1; padding: 10px 14px; border-radius: 24px; border: 1px solid #E4E4E7; font-size: 14px; outline: none; }}
    .joy-input:focus {{ border-color: #059669; }}
    .joy-send-btn {{ background: #059669; color: #ffffff; border: none; border-radius: 20px; padding: 0 16px; cursor: pointer; font-weight: 600; font-size: 13px; }}
  `;
  document.head.appendChild(style);

  // 2. Inject Launcher Button
  var btn = document.createElement('button');
  btn.className = 'joy-widget-btn';
  btn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
  document.body.appendChild(btn);

  // 3. Inject Chat Window
  var panel = document.createElement('div');
  panel.className = 'joy-chat-panel';
  panel.innerHTML = `
    <div class="joy-chat-header">
      <div class="joy-header-title">
        <span class="joy-status-dot"></span>
        <span>Sales Assistant</span>
      </div>
      <button style="border:none;background:none;cursor:pointer;color:#71717A;font-size:18px;" id="joy-close-btn">&times;</button>
    </div>
    <div class="joy-chat-body" id="joy-msg-container">
      <div class="joy-msg joy-msg-agent">Hi there! 👋 How can I help you find the perfect product today?</div>
    </div>
    <div class="joy-chat-footer">
      <input type="text" class="joy-input" id="joy-input" placeholder="Type a message..." />
      <button class="joy-send-btn" id="joy-send-btn">Send</button>
    </div>
  `;
  document.body.appendChild(panel);

  var isOpen = false;
  btn.onclick = function() {{
    isOpen = !isOpen;
    panel.style.display = isOpen ? 'flex' : 'none';
  }};
  document.getElementById('joy-close-btn').onclick = function() {{
    isOpen = false;
    panel.style.display = 'none';
  }};

  // 4. Send Message Handler
  var input = document.getElementById('joy-input');
  var sendBtn = document.getElementById('joy-send-btn');
  var container = document.getElementById('joy-msg-container');

  function send() {{
    var text = input.value.trim();
    if (!text) return;
    input.value = '';

    // Append user message safely
    var userBubble = document.createElement('div');
    userBubble.className = 'joy-msg joy-msg-customer';
    userBubble.innerText = text;
    container.appendChild(userBubble);
    container.scrollTop = container.scrollHeight;

    // Call API
    fetch(apiBase + '/api/v1/widget/chat', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        tenant_id: tenantId,
        customer_id: visitorId,
        message: text
      }})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      var agentBubble = document.createElement('div');
      agentBubble.className = 'joy-msg joy-msg-agent';
      var rawReply = data.reply || 'Thanks for reaching out!';
      var safeContent = escapeHtml(rawReply).replace(/\\n/g, '<br/>');
      safeContent = safeContent.replace(/(https?:\\\/\\\/[^\\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:#059669;text-decoration:underline;font-weight:600;">$1</a>');
      agentBubble.innerHTML = safeContent;
      container.appendChild(agentBubble);
      container.scrollTop = container.scrollHeight;
    }})
    .catch(function(err) {{
      console.error('Joy widget error:', err);
    }});
  }}

  sendBtn.onclick = send;
  input.onkeypress = function(e) {{ if (e.key === 'Enter') send(); }};
}})();
"""
