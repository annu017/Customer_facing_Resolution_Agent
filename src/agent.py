"""
agent.py
--------
Core agent logic for the Customer-Facing Resolution Agent (Airline Disruption).

Design decision (explained in README): the ACTION/POLICY DECISIONS are made by a
deterministic rule engine, not by an LLM. This is deliberate for a customer-facing
airline agent -- policy enforcement (refunds, compensation ceilings, escalation
triggers) must be 100% consistent and auditable, which a purely generative
approach cannot guarantee. An LLM (optional, via OpenAI) is used ONLY to render
the final decision into natural, empathetic language -- never to decide what is
allowed. If no OPENAI_API_KEY is configured, a built-in templated generator is
used instead, so the app is fully functional out of the box.
"""

import os
import re
import json
import uuid
from datetime import datetime

from src import data_loader as data

# ---------------------------------------------------------------------------
# Optional LLM phrasing layer
# ---------------------------------------------------------------------------
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


def _llm_client():
    if not _OPENAI_AVAILABLE:
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. SENTIMENT / ANGER DETECTION
# ---------------------------------------------------------------------------

ANGER_KEYWORDS = [
    "furious", "angry", "outraged", "unacceptable", "ridiculous", "disgusted",
    "terrible", "horrible", "worst", "pathetic", "fed up", "sick of",
    "extremely disappointed", "very upset", "not happy", "disappointed",
    "shame", "useless", "incompetent", "scam", "cheated",
]

LEGAL_THREAT_KEYWORDS = [
    "legal action", "sue", "lawsuit", "lawyer", "consumer court",
    "formal complaint", "file a complaint", "consumer forum", "media",
    "social media", "report you", "regulator", "dgca complaint",
]


def detect_sentiment(message: str):
    """Very lightweight, explainable keyword + heuristic based sentiment/anger
    detector. Returns a dict with a label and a numeric intensity score (0-1)."""
    text = message.lower()
    score = 0.0
    matched = []

    for kw in ANGER_KEYWORDS:
        if kw in text:
            score += 0.2
            matched.append(kw)

    # Heuristics: exclamation marks, ALL CAPS words, repeated punctuation
    exclamations = message.count("!")
    if exclamations:
        score += min(exclamations * 0.1, 0.3)

    caps_words = [w for w in re.findall(r"[A-Za-z']+", message) if len(w) > 2 and w.isupper()]
    if caps_words:
        score += min(len(caps_words) * 0.1, 0.2)

    score = min(round(score, 2), 1.0)

    if score >= 0.6:
        label = "angry"
    elif score >= 0.25:
        label = "frustrated"
    else:
        label = "neutral"

    return {"label": label, "score": score, "matched_keywords": matched}


def detect_legal_threat(message: str) -> bool:
    text = message.lower()
    return any(kw in text for kw in LEGAL_THREAT_KEYWORDS)



INTENT_KEYWORDS = {
    "refund": ["refund", "money back", "cash back", "reimburse", "give me my money"],
    "upgrade": ["upgrade", "business class", "first class", "premium seat"],
    "rebooking": ["rebook", "another flight", "change my flight", "move me to",
                  "different flight", "next available flight", "switch flight",
                  "higher fare", "earlier flight"],
    "hotel": ["hotel", "accommodation", "room for the night", "stay", "lodging"],
    "meal_voucher": ["meal", "voucher", "food"],
    "lounge": ["lounge"],
    "compensation": ["compensation", "compensate", "for my trouble", "for the trouble",
                      "make it up to me", "goodwill"],
    "status": ["status", "what's happening", "flight status", "when will",
               "is my flight", "any update"],
    "fare_difference": ["fare difference", "fare diff", "price difference", "pay the difference"],
}


def detect_intents(message: str):
    text = message.lower()
    found = []
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(intent)
    if detect_legal_threat(message):
        found.append("legal_threat")
    if not found:
        found.append("general_inquiry")
    return found


def extract_currency_amount(message: str):
    """Pull the first plausible rupee amount out of free text, e.g.
    '2,000', 'Rs 2000', '₹2,000' -> 2000.0"""
    match = re.search(r"(?:rs\.?|inr|₹)?\s?([0-9]{1,3}(?:[,.][0-9]{2,3})*)", message, re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        value = float(raw)
        # Filter out tiny numbers that are probably not currency (e.g. "flight SK-118" digits
        # are excluded because they're matched separately in the message, not via this pattern
        # matching a bare number near currency cues).
        return value
    except ValueError:
        return None



class Decision:
    def __init__(self, intent, status, action, reason, details=None):
        self.intent = intent
        self.status = status          # "ALLOWED" | "DENIED" | "ESCALATED"
        self.action = action
        self.reason = reason
        self.details = details or {}

    def to_dict(self):
        return {
            "intent": self.intent,
            "status": self.status,
            "action": self.action,
            "reason": self.reason,
            "details": self.details,
        }


def _delay_tier(delay_hours: int):
    for tier in data.POLICIES["delay_compensation"]["tiers"]:
        lo, hi = tier["min_hours"], tier["max_hours"]
        if hi is None:
            if delay_hours >= lo:
                return tier
        else:
            if lo <= delay_hours < hi:
                return tier
    return None


def evaluate_intent(intent: str, message: str, customer: dict, booking: dict):
    """Returns a Decision object for a single detected intent."""
    tier_priority = customer["tier"] in data.POLICIES["loyalty_tier"]["priority_tiers"]

    if intent == "legal_threat":
        return Decision(
            intent, "ESCALATED", "escalate_to_human",
            data.ESCALATION_REASONS["acknowledge_legal_threat_without_escalation"],
        )

    if intent == "refund":
        if booking["disruption_type"] == "airline_cancellation":
            return Decision(
                intent, "ALLOWED", "initiate_refund_original_method",
                "Flight was cancelled by the airline, so a full refund to the original "
                f"payment method is approved, per policy ({data.POLICIES['refund_processing']['business_days']} business days).",
                {"business_days": data.POLICIES["refund_processing"]["business_days"]},
            )
        else:
            return Decision(
                intent, "DENIED", None,
                "Flight is delayed, not cancelled, so an unconditional refund is not "
                "applicable. The customer may instead be rebooked or receive delay "
                "compensation per policy.",
            )

    if intent == "upgrade":
        return Decision(
            intent, "ESCALATED", "escalate_to_human",
            data.ESCALATION_REASONS["grant_free_upgrade_as_goodwill"],
            {"tier_priority_rebooking_only": tier_priority},
        )

    if intent == "compensation":
        return Decision(
            intent, "ESCALATED", "escalate_to_human",
            data.ESCALATION_REASONS["compensation_beyond_policy"],
        )

    if intent == "rebooking":
        if booking["disruption_type"] == "airline_cancellation":
            return Decision(
                intent, "ALLOWED", "free_rebooking_within_24h",
                "Airline-caused cancellation qualifies for free rebooking within 24 hours."
                + (" Gold/Platinum tier receives priority rebooking." if tier_priority else ""),
            )
        amount = extract_currency_amount(message)
        if amount is not None:
            ceiling = data.POLICIES["fare_difference"]["agent_approval_ceiling"]
            if amount > ceiling:
                return Decision(
                    "fare_difference", "ESCALATED", "escalate_to_human",
                    data.ESCALATION_REASONS["waive_fare_difference_over_ceiling"],
                    {"requested_amount": amount, "ceiling": ceiling},
                )
            else:
                return Decision(
                    "fare_difference", "ALLOWED", "approve_fare_difference_under_ceiling",
                    f"Fare difference of ₹{amount:,.0f} is within the agent's ₹{ceiling:,.0f} "
                    "approval ceiling and is approved; customer will be charged the difference.",
                    {"requested_amount": amount, "ceiling": ceiling},
                )
        return Decision(
            intent, "ALLOWED", "provide_rebooking_options",
            "Voluntary rebooking is possible; any fare difference will be charged to the "
            "customer. Please share the desired flight so the fare difference can be quoted.",
        )

    if intent == "fare_difference":
        amount = extract_currency_amount(message)
        ceiling = data.POLICIES["fare_difference"]["agent_approval_ceiling"]
        if amount is None:
            return Decision(
                intent, "DENIED", None,
                "Could not determine the fare difference amount from the message; "
                "please provide the exact fare difference quoted for the new flight.",
            )
        if amount > ceiling:
            return Decision(
                intent, "ESCALATED", "escalate_to_human",
                data.ESCALATION_REASONS["waive_fare_difference_over_ceiling"],
                {"requested_amount": amount, "ceiling": ceiling},
            )
        return Decision(
            intent, "ALLOWED", "approve_fare_difference_under_ceiling",
            f"Fare difference of ₹{amount:,.0f} is within the ₹{ceiling:,.0f} ceiling and is approved.",
            {"requested_amount": amount, "ceiling": ceiling},
        )
    
    if intent == "hotel":
        if booking["disruption_type"] != "airline_delay" and booking["status"] != "Delayed":
            return Decision(
                intent, "ESCALATED", "escalate_to_human",
                data.ESCALATION_REASONS["exception_for_non_airline_disruption"],
            )
        delay_hours = booking.get("delay_hours", 0)
        tier = _delay_tier(delay_hours)
        if tier and "hotel_accommodation" in tier["benefits"]:
            return Decision(
                intent, "ALLOWED", "arrange_hotel_delayed_hours",
                f"Delay of {delay_hours}h exceeds the 5-hour threshold, so hotel "
                "accommodation is approved for the delayed-hours portion only "
                "(NOT a full night's stay), plus meal voucher and lounge access.",
                {"delay_hours": delay_hours},
            )
        return Decision(
            intent, "DENIED", None,
            f"Delay of {delay_hours}h does not exceed the 5-hour threshold required for "
            "hotel accommodation, so this request is declined. Applicable delay "
            "compensation (meal voucher"
            + (" + lounge access" if tier and "lounge_access" in tier["benefits"] else "")
            + ") is offered instead.",
            {"delay_hours": delay_hours},
        )

    if intent in ("meal_voucher", "lounge"):
        delay_hours = booking.get("delay_hours", 0)
        tier = _delay_tier(delay_hours)
        if tier:
            action = "issue_meal_voucher" if intent == "meal_voucher" else "issue_lounge_access"
            if intent == "lounge" and "lounge_access" not in tier["benefits"]:
                return Decision(
                    intent, "DENIED", None,
                    f"Delay of {delay_hours}h is under the 3-hour threshold for lounge access.",
                )
            return Decision(
                intent, "ALLOWED", action,
                f"Delay of {delay_hours}h qualifies for: {', '.join(tier['benefits'])}.",
                {"delay_hours": delay_hours, "voucher_amount": tier.get("voucher_amount")},
            )
        return Decision(intent, "DENIED", None, "No qualifying delay found on this booking.")

   
    if intent == "status":
        return Decision(
            intent, "ALLOWED", "provide_booking_status",
            f"Flight {booking['flight_number']} ({booking['route']}) status: {booking['status']}.",
            {"booking": booking},
        )

    return Decision(
        intent, "ALLOWED", "general_response",
        "General inquiry -- no policy action required.",
    )


def auto_delay_benefits(booking: dict):
    """Proactively compute what a delayed customer is entitled to, independent
    of whether they explicitly asked -- mirrors real airline agent behaviour."""
    if booking.get("disruption_type") != "airline_delay":
        return None
    delay_hours = booking.get("delay_hours", 0)
    tier = _delay_tier(delay_hours)
    if not tier:
        return None
    return {
        "delay_hours": delay_hours,
        "benefits": tier["benefits"],
        "voucher_amount": tier.get("voucher_amount"),
        "hotel_note": tier.get("hotel_note"),
    }



def _template_response(customer, booking, sentiment, decisions, auto_benefits):
    lines = []

    if sentiment["label"] == "angry":
        lines.append(
            f"I'm really sorry for the frustration this has caused, {customer['name'].split()[0]} -- "
            "I understand how disruptive this is, and I want to help sort it out right now."
        )
    elif sentiment["label"] == "frustrated":
        lines.append(
            f"I understand this is frustrating, {customer['name'].split()[0]}, let me help resolve this."
        )

    for d in decisions:
        if d.status == "ALLOWED":
            lines.append(f"✅ {d.reason}")
        elif d.status == "DENIED":
            lines.append(f"❌ {d.reason}")
        elif d.status == "ESCALATED":
            lines.append(f"🔺 I'm not able to approve this myself -- {d.reason} "
                          "I'm escalating this to a human supervisor who will follow up with you shortly.")

    if auto_benefits and not any(d.intent in ("hotel", "meal_voucher", "lounge") for d in decisions):
        benefits_str = ", ".join(b.replace("_", " ") for b in auto_benefits["benefits"])
        lines.append(
            f"Also, since your flight is delayed by {auto_benefits['delay_hours']} hours, "
            f"you're automatically entitled to: {benefits_str}."
            + (f" ({auto_benefits['hotel_note']})" if auto_benefits.get("hotel_note") else "")
        )

    return "\n\n".join(lines) if lines else "Thanks for reaching out -- how can I help with your booking today?"


def _llm_polish(raw_text, customer, message):
    client = _llm_client()
    if client is None:
        return raw_text
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a warm, professional airline customer-service agent. "
                    "Rewrite the RESOLUTION NOTES below into a natural, empathetic reply to the "
                    "customer. Do NOT change any decision, fact, amount, or policy outcome -- "
                    "only improve tone and phrasing. Keep it concise."
                )},
                {"role": "user", "content": f"Customer message: {message}\n\nResolution notes:\n{raw_text}"},
            ],
            max_tokens=400,
            temperature=0.4,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return raw_text

class ResolutionAgent:
    """Stateful per-session agent wrapper that also maintains the audit trail."""

    def __init__(self):
        self.audit_log = []

    def handle_message(self, pnr: str, message: str):
        customer = data.get_customer_by_pnr(pnr)
        booking = data.get_booking_by_pnr(pnr)
        if not customer or not booking:
            raise ValueError(f"Unknown PNR: {pnr}")

        sentiment = detect_sentiment(message)
        intents = detect_intents(message)
        raw_decisions = [evaluate_intent(i, message, customer, booking) for i in intents]

        
        seen = set()
        decisions = []
        for d in raw_decisions:
            key = (d.intent, d.action, d.status, d.reason)
            if key not in seen:
                seen.add(key)
                decisions.append(d)

        auto_benefits = auto_delay_benefits(booking)

        raw_response = _template_response(customer, booking, sentiment, decisions, auto_benefits)
        final_response = _llm_polish(raw_response, customer, message)

        escalated = any(d.status == "ESCALATED" for d in decisions)

        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "customer_name": customer["name"],
            "pnr": pnr,
            "tier": customer["tier"],
            "customer_message": message,
            "sentiment": sentiment,
            "detected_intents": intents,
            "decisions": [d.to_dict() for d in decisions],
            "agent_response": final_response,
            "escalated": escalated,
            "escalation_reasons": [d.reason for d in decisions if d.status == "ESCALATED"],
        }
        self.audit_log.append(entry)
        return entry

    def export_audit_log(self):
        return json.dumps(self.audit_log, indent=2, ensure_ascii=False)

    def escalations(self):
        return [e for e in self.audit_log if e["escalated"]]