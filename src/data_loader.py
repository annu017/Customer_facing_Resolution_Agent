"""
data.py
-------
Static "database" for the Customer-Facing Resolution Agent (Airline Disruption) demo.
In a production system this would be replaced by calls to a PNR/booking system,
a CRM, and a policy-management service. Here it is an in-memory structure so the
whole assignment runs standalone with zero external dependencies or API keys.
"""

from datetime import datetime

# ---------------------------------------------------------------------------
# 1. CUSTOMER PROFILES (keyed by PNR for O(1) lookup from the booking record)
# ---------------------------------------------------------------------------

CUSTOMERS = {
    "SK4821X": {
        "name": "Priya Nair",
        "pnr": "SK4821X",
        "tier": "Gold",
        "email": "priya.nair@sample.com",
        "phone": "+91-98xxxxxxx1",
        "travel_history": {
            "total_flights": 8,
            "prior_complaints": [
                {"issue": "Delayed baggage", "resolution": "Resolved with voucher"}
            ],
        },
    },
    "TR1190B": {
        "name": "Arvind Kulkarni",
        "pnr": "TR1190B",
        "tier": "Silver",
        "email": "arvind.kulkarni@example.com",
        "phone": "+91-98xxxxxxx2",
        "travel_history": {
            "total_flights": 3,
            "prior_complaints": [],
        },
    },
    "WL7742": {
        "name": "Meher Kaur",
        "pnr": "WL7742",
        "tier": "Platinum",
        "email": "meher.kaur@example.com",
        "phone": "+91-98xxxxxxx3",
        "travel_history": {
            "total_flights": 10,
            "prior_complaints": [
                {"issue": "Overbooking", "resolution": "Tier-status upgrade"}
            ],
        },
    },
}

# ---------------------------------------------------------------------------
# 2. BOOKING / TRANSACTION DATA (keyed by PNR)
# ---------------------------------------------------------------------------
# delay_hours / disruption_type / new_departure are pre-computed so the rule
# engine never has to parse dates at runtime.

BOOKINGS = {
    "SK4821X": {
        "pnr": "SK4821X",
        "flight_number": "SK-204",
        "route": "Delhi -> Goa",
        "date": "2026-09-23",
        "scheduled_departure": "18:40",
        "status": "Cancelled",
        "disruption_type": "airline_cancellation",
        "disruption_reason": "operational reasons",
        "delay_hours": 0,
        "return_leg": {
            "route": "Goa -> Delhi",
            "date": "2026-09-25",
            "scheduled_departure": "16:20",
            "status": "Unaffected",
        },
    },
    "TR1190B": {
        "pnr": "TR1190B",
        "flight_number": "SK-118",
        "route": "Mumbai -> Bengaluru",
        "date": "2026-09-23",
        "scheduled_departure": "07:10",
        "new_departure": "11:20",
        "status": "Delayed",
        "disruption_type": "airline_delay",
        "delay_hours": 4,
    },
    "WL7742": {
        "pnr": "WL7742",
        "flight_number": "SK-305",
        "route": "Delhi -> Hyderabad",
        "date": "2026-09-23",
        "scheduled_departure": "14:00",
        "new_departure": "20:00",
        "status": "Delayed",
        "disruption_type": "airline_delay",
        "delay_hours": 6,
    },
}

# ---------------------------------------------------------------------------
# 3. SERVICE RULES / POLICIES
# ---------------------------------------------------------------------------

POLICIES = {
    "cancellation_rebooking": {
        "description": "Free rebooking within 24h OR full refund if the airline cancelled the flight.",
        "window_hours": 24,
    },
    "delay_compensation": {
        "description": "Tiered compensation based on length of delay.",
        "tiers": [
            {"max_hours": 3, "min_hours": 0, "benefits": ["meal_voucher"], "voucher_amount": 500},
            {"max_hours": 5, "min_hours": 3, "benefits": ["meal_voucher", "lounge_access"], "voucher_amount": 500},
            {"max_hours": None, "min_hours": 5, "benefits": ["meal_voucher", "lounge_access", "hotel_accommodation"],
             "voucher_amount": 500,
             "hotel_note": "Hotel covers the delayed-hours portion only, NOT a full night's stay."},
        ],
    },
    "refund_processing": {
        "description": "Full refund in 7 business days, to the ORIGINAL payment method only.",
        "business_days": 7,
        "payment_method_restriction": "original_only",
    },
    "fare_difference": {
        "description": "Voluntary rebooking to a higher fare requires the customer to pay the fare difference.",
        "agent_approval_ceiling": 1500,
        "note": "Agents CANNOT waive/absorb a fare difference greater than ₹1,500 without supervisor approval.",
    },
    "loyalty_tier": {
        "description": "Gold & Platinum tiers get priority rebooking only. No additional monetary compensation beyond policy is granted for tier status.",
        "priority_tiers": ["Gold", "Platinum"],
    },
}

# ---------------------------------------------------------------------------
# 4. ALLOWED vs. PROHIBITED ACTIONS
# ---------------------------------------------------------------------------

ALLOWED_ACTIONS = [
    "free_rebooking_within_24h",       # only for airline-caused disruption
    "issue_meal_voucher",
    "issue_lounge_access",
    "arrange_hotel_delayed_hours",     # only when delay > 5h, delayed-hours portion only
    "initiate_refund_original_method",
    "provide_booking_status",
    "approve_fare_difference_under_ceiling",  # <= 1500
]

PROHIBITED_ACTIONS = [
    "compensation_beyond_policy",
    "waive_fare_difference_over_ceiling",   # > 1500
    "exception_for_non_airline_disruption",
    "acknowledge_legal_threat_without_escalation",
    "refund_to_non_original_payment_method",
    "grant_full_night_hotel_when_not_entitled",
    "grant_free_upgrade_as_goodwill",
]

# Human-readable escalation reasons mapped to the prohibited action they map to.
ESCALATION_REASONS = {
    "compensation_beyond_policy": "Requested compensation exceeds what policy allows an agent to grant.",
    "waive_fare_difference_over_ceiling": "Fare difference exceeds the ₹1,500 agent approval ceiling.",
    "exception_for_non_airline_disruption": "Disruption is not airline-caused; exceptions require supervisor sign-off.",
    "acknowledge_legal_threat_without_escalation": "Customer has raised a legal action / formal complaint threat.",
    "refund_to_non_original_payment_method": "Customer requested refund to a payment method other than the original one.",
    "grant_free_upgrade_as_goodwill": "Free class upgrade as goodwill is compensation beyond policy.",
}


def get_customer_by_pnr(pnr: str):
    return CUSTOMERS.get(pnr)


def get_booking_by_pnr(pnr: str):
    return BOOKINGS.get(pnr)


def all_customer_names():
    return [f"{c['name']} ({c['tier']}) - {c['pnr']}" for c in CUSTOMERS.values()]


def snapshot_timestamp():
    return datetime.now().isoformat(timespec="seconds")
print("data loaded successfully")