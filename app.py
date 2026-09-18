"""
app.py
------
Streamlit UI for the Customer-Facing Resolution Agent (Airline Disruption).

Run with:  streamlit run app.py
"""

import importlib

try:
    st = importlib.import_module("streamlit")
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "Streamlit is required to run this app. Install it with: pip install streamlit"
    ) from exc

from src import data_loader as data
from src.agent import ResolutionAgent
st.set_page_config(
    page_title="Airline Resolution Agent",
    page_icon="✈️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "agent" not in st.session_state:
    st.session_state.agent = ResolutionAgent()

if "selected_pnr" not in st.session_state:
    st.session_state.selected_pnr = list(data.CUSTOMERS.keys())[0]

if "chats" not in st.session_state:
    # per-PNR chat history so switching customers doesn't lose context
    st.session_state.chats = {pnr: [] for pnr in data.CUSTOMERS}

agent = st.session_state.agent

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("✈️ Resolution Agent")
st.sidebar.caption("Customer-Facing Resolution Agent — Airline Disruption")

customer_labels = {pnr: f"{c['name']}  ·  {c['tier']}  ·  {pnr}" for pnr, c in data.CUSTOMERS.items()}
selected_label = st.sidebar.selectbox(
    "Active customer",
    options=list(customer_labels.values()),
    index=list(customer_labels.keys()).index(st.session_state.selected_pnr),
)
# map label back to pnr
st.session_state.selected_pnr = [pnr for pnr, label in customer_labels.items() if label == selected_label][0]
pnr = st.session_state.selected_pnr
customer = data.get_customer_by_pnr(pnr)
booking = data.get_booking_by_pnr(pnr)

st.sidebar.markdown("### 🧾 Active Customer Status")
status_color = "🟢" if booking["status"] == "Unaffected" else ("🟠" if booking["status"] == "Delayed" else "🔴")
st.sidebar.markdown(
    f"**{customer['name']}** ({customer['tier']} tier)\n\n"
    f"PNR: `{pnr}`  \n"
    f"Flight: `{booking['flight_number']}` — {booking['route']}  \n"
    f"Status: {status_color} **{booking['status']}**"
    + (f" ({booking.get('delay_hours')}h)" if booking["status"] == "Delayed" else "")
)

with st.sidebar.expander("👤 Full customer profile"):
    st.json(customer)

with st.sidebar.expander("🎫 Full booking record"):
    st.json(booking)

with st.sidebar.expander("📖 Live policy database"):
    st.json(data.POLICIES)

with st.sidebar.expander("✅ Allowed vs 🚫 Prohibited actions"):
    st.markdown("**Allowed:**")
    for a_ in data.ALLOWED_ACTIONS:
        st.markdown(f"- {a_.replace('_', ' ')}")
    st.markdown("**Prohibited (must escalate):**")
    for p_ in data.PROHIBITED_ACTIONS:
        st.markdown(f"- {p_.replace('_', ' ')}")

st.sidebar.markdown("### 🚨 Escalation Alerts")
escalations = agent.escalations()
if escalations:
    for e in escalations[-5:][::-1]:
        st.sidebar.error(
            f"**{e['customer_name']}** ({e['pnr']}) — {e['timestamp']}\n\n"
            + "; ".join(e["escalation_reasons"])
        )
else:
    st.sidebar.info("No escalations logged yet.")

st.sidebar.markdown("### 🗂️ Audit Trail")
if agent.audit_log:
    st.sidebar.download_button(
        "Download full audit log (JSON)",
        data=agent.export_audit_log(),
        file_name="audit_trail.json",
        mime="application/json",
        use_container_width=True,
    )
else:
    st.sidebar.caption("No conversation logged yet.")

if st.sidebar.button("🔄 Reset this customer's conversation", use_container_width=True):
    st.session_state.chats[pnr] = []
    st.rerun()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("Airline Disruption Resolution Agent")
st.caption(
    "A rule-governed customer service agent: policy decisions (refunds, compensation, "
    "escalation) are enforced deterministically; conversation is natural language."
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Customer", customer["name"])
col2.metric("Tier", customer["tier"])
col3.metric("Flight", booking["flight_number"])
col4.metric("Status", booking["status"])

st.markdown("#### 🧪 Quick scenario test messages")
qcols = st.columns(3)
scenario_messages = {
    "SK4821X": "I am FURIOUS!! My flight was cancelled. I want a full cash refund AND a free business class upgrade for all this trouble!",
    "TR1190B": "My flight is delayed. Can I get hotel accommodation please?",
    "WL7742": "I need a full night's hotel stay because of this delay, and I also want to move to a higher fare flight — the fare difference is 2,000 rupees.",
}
pending_prefill_key = "pending_prefill"
if pending_prefill_key not in st.session_state:
    st.session_state[pending_prefill_key] = None

with qcols[0]:
    if st.button("Try Priya's scenario", use_container_width=True, disabled=(pnr != "SK4821X")):
        st.session_state[pending_prefill_key] = scenario_messages["SK4821X"]
with qcols[1]:
    if st.button("Try Arvind's scenario", use_container_width=True, disabled=(pnr != "TR1190B")):
        st.session_state[pending_prefill_key] = scenario_messages["TR1190B"]
with qcols[2]:
    if st.button("Try Meher's scenario", use_container_width=True, disabled=(pnr != "WL7742")):
        st.session_state[pending_prefill_key] = scenario_messages["WL7742"]

st.divider()

# --- chat history render ---
chat_container = st.container(height=420)
with chat_container:
    for turn in st.session_state.chats[pnr]:
        with st.chat_message("user"):
            st.write(turn["customer_message"])
        with st.chat_message("assistant"):
            st.write(turn["agent_response"])
            badges = []
            for d in turn["decisions"]:
                icon = {"ALLOWED": "✅", "DENIED": "❌", "ESCALATED": "🔺"}.get(d["status"], "•")
                badges.append(f"{icon} `{d['intent']}` → **{d['status']}**")
            if badges:
                st.caption(" | ".join(badges))
            if turn["escalated"]:
                st.warning("This interaction was escalated to a human supervisor.")


def _run_turn(message: str):
    entry = agent.handle_message(pnr, message)
    st.session_state.chats[pnr].append(entry)


# --- input ---
prefill = st.session_state.get(pending_prefill_key)
user_message = st.chat_input("Type the customer's message here...")

if prefill:
    st.session_state[pending_prefill_key] = None
    _run_turn(prefill)
    st.rerun()

if user_message:
    _run_turn(user_message)
    st.rerun()

st.divider()
with st.expander("ℹ️ How decisions are made"):
    st.markdown(
        "1. **Sentiment/anger detection** — keyword + heuristic scoring flags angry/frustrated customers "
        "so the reply opens with appropriate empathy.\n"
        "2. **Intent recognition** — keyword-based multi-intent extraction (a single message can contain "
        "several asks, e.g. *refund* + *upgrade*).\n"
        "3. **Rule engine** — every intent is checked against `data.py` policies. Refunds only for airline "
        "cancellations; hotel only when delay > 5h (delayed-hours portion only); fare differences over "
        "₹1,500 always escalate; legal threats always escalate; goodwill upgrades always escalate.\n"
        "4. **Escalation logging** — any `ESCALATED` decision is written to the sidebar alert panel and the "
        "audit trail immediately.\n"
        "5. **Audit trail** — every turn (message, detected intents, decisions, sentiment, final response) "
        "is stored in-memory and downloadable as JSON for compliance review."
    )