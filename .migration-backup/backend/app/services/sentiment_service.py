import json
import logging
import re
from typing import Dict, Any, List
import httpx
from app.core.config import settings

logger = logging.getLogger("joy.services.sentiment")

# Critical Risk Lexicons
ANGER_KEYWORDS = [
    "scam", "cheat", "cheater", "cheated", "cheating", "fraud", "fake", "terrible",
    "horrible", "worst", "bad service", "angry", "anger", "furious", "disgusted",
    "unacceptable", "broken", "defective", "stolen", "harass", "hate", "trash",
    "rubbish", "rip off", "ripoff", "liar", "threat"
]

REFUND_KEYWORDS = [
    "refund", "refunds", "money back", "return", "returns", "chargeback", "dispute",
    "cancel", "cancelled", "cancelling", "cancellation", "compensation", "boycott", "cancel order"
]

LEGAL_KEYWORDS = [
    "lawyer", "police", "sue", "legal action", "court",
    "consumer rights", "consumer forum", "fraud report", "attorney", "lawsuit"
]

ALL_RISK_KEYWORDS = sorted(list(set(ANGER_KEYWORDS + REFUND_KEYWORDS + LEGAL_KEYWORDS)))


class SentimentService:
    """
    Real-Time Customer Sentiment & Risk Evaluator:
    - Analyzes incoming messages for emotional tone, frustration, and commercial risk.
    - Strictly enforces safety guardrail: risk > 0.70 triggers immediate HITL halt.
    - DeepSeek reasoning core with deterministic keyword security floor (prompt-injection resistant).
    """

    @classmethod
    def find_flagged_keywords(cls, text: str) -> List[str]:
        """Scans message text for high-risk tokens."""
        lower_text = text.lower()
        flagged = []
        for kw in ALL_RISK_KEYWORDS:
            # Word boundary regex or phrase matching
            if " " in kw:
                if kw in lower_text:
                    flagged.append(kw)
            else:
                if re.search(rf"\b{re.escape(kw)}\b", lower_text):
                    flagged.append(kw)
        return flagged

    @classmethod
    async def evaluate_sentiment(cls, message_text: str) -> Dict[str, Any]:
        """
        Evaluates sentiment (0.0=negative to 1.0=positive) and risk (0.0=safe to 1.0=danger).
        Guarantees sub-50ms deterministic safety check.
        """
        flagged = cls.find_flagged_keywords(message_text)

        # Baseline deterministic calculation
        if any(k in flagged for k in LEGAL_KEYWORDS):
            base_sentiment = 0.05
            base_risk = 0.95
            intent = "legal_threat"
            reason = f"Legal action/escalation detected: {', '.join(flagged)}"
        elif any(k in flagged for k in REFUND_KEYWORDS):
            base_sentiment = 0.20
            base_risk = 0.85
            intent = "refund_or_cancellation"
            reason = f"Refund/cancellation request detected: {', '.join(flagged)}"
        elif flagged:
            base_sentiment = 0.25
            base_risk = 0.80
            intent = "angry_complaint"
            reason = f"Frustrated/anger terms detected: {', '.join(flagged)}"
        else:
            base_sentiment = 0.85
            base_risk = 0.15
            intent = "general_inquiry"
            reason = "Standard customer inquiry with normal emotional tone."

        sentiment_score = base_sentiment
        risk_score = base_risk

        # Optional: Enrich with DeepSeek API if available and no critical keywords forced
        if settings.DEEPSEEK_API_KEY and not flagged:
            try:
                sanitized = message_text.replace("<", "&lt;").replace(">", "&gt;")
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(
                        f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a customer sentiment and risk analysis engine for an e-commerce platform.\n"
                                        "Evaluate the user's message and return a JSON object with keys:\n"
                                        "- sentiment_score: float from 0.0 (furious/distressed) to 1.0 (ecstatic)\n"
                                        "- risk_score: float from 0.0 (safe) to 1.0 (immediate risk/churn)\n"
                                        "- intent: short string (e.g., product_inquiry, compliment, confusion, complaint)\n"
                                        "- reason: 1 concise sentence explaining the score"
                                    ),
                                },
                                {"role": "user", "content": f"<customer_message>\n{sanitized}\n</customer_message>"},
                            ],
                            "response_format": {"type": "json_object"},
                        },
                    )
                    if resp.status_code == 200:
                        data = json.loads(resp.json()["choices"][0]["message"]["content"])
                        sentiment_score = float(data.get("sentiment_score", sentiment_score))
                        risk_score = float(data.get("risk_score", risk_score))
                        intent = data.get("intent", intent)
                        reason = data.get("reason", reason)
            except Exception as e:
                logger.debug(f"DeepSeek sentiment enrichment skipped: {e}")

        # Strict Security Floor: If any risk keywords are detected, risk cannot be below 0.75
        if flagged and risk_score < 0.75:
            risk_score = 0.80

        is_risk_breached = (risk_score > 0.70) or (len(flagged) > 0)

        # Risk badge coloring per DESIGN_BRIEF.md
        if risk_score > 0.70:
            risk_badge = "crimson_alert"   # Clean Crimson (#E11D48)
        elif risk_score >= 0.40:
            risk_badge = "yellow_warning"  # Amber (#F59E0B)
        else:
            risk_badge = "green_safe"      # Emerald Forest Green (#059669)

        return {
            "sentiment_score": round(sentiment_score, 2),
            "risk_score": round(risk_score, 2),
            "is_risk_breached": is_risk_breached,
            "risk_badge": risk_badge,
            "flagged_keywords": flagged,
            "intent": intent,
            "reason": reason,
        }
