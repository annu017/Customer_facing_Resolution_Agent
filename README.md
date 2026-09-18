# 1. Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) enable LLM-polished phrasing
#    Without this, the agent uses a built-in templated response generator —
#    the app is fully functional either way. Policy decisions never depend
#    on the LLM.
export OPENAI_API_KEY="sk-..."     # Windows (PowerShell): $env:OPENAI_API_KEY="sk-..."

# 4. Run the app
streamlit run app.py

Open the URL Streamlit prints (default http://localhost:8501).

2. Project Structure
airline_agent/
├── data.py           # Customer profiles, bookings, policies, allowed/prohibited actions
├── agent.py          # Sentiment detection, intent recognition, rule engine, audit trail
├── app.py            # Streamlit UI: chat, customer selector, sidebar (DB/policy/escalations)
├── requirements.txt  # Python dependencies
└── README.md         # This file
3. Architecture

The agent is deliberately not "ask an LLM what to do." For a customer-facing airline agent, policy enforcement (who gets a refund, when a hotel is owed, when a fare difference must be escalated) has to be 100% deterministic and explainable to an auditor — an LLM alone cannot guarantee that. So the system splits decision-making from language generation:

Layer	Responsibility	Implementation
Sentiment/Anger detection	Detect frustration/anger to shape tone	Keyword + heuristic scoring (detect_sentiment)
Intent recognition	Extract one or more asks from free text (a single message can contain several)	Keyword-based multi-intent extractor (detect_intents)
Rule engine	Decide ALLOWED / DENIED / ESCALATED per intent, against data.py policies	Deterministic Python rules (evaluate_intent)
Escalation logging	Any ESCALATED decision is surfaced immediately	Sidebar alert panel + audit log entry
Audit trail	Every turn is fully logged for compliance	In-memory list, downloadable as JSON
Response generation	Turn the rule engine's output into a natural reply	Templated generator by default; optional OpenAI polish (phrasing only, never decisions)
Process Flow
ALLOWED
DENIED
ESCALATED
Yes
No
Customer selects profile insidebar
Customer types message inchat
Sentiment / AngerDetection
Intent Recognitionmulti-intent extraction
For each detected intent
Rule Engine evaluatesagainstdata.py policies
Decision
Execute allowed actione.g. refund, voucher,rebooking
Deny with policy reason
Log escalation +alert supervisor panel
Compose response
OPENAI_API_KEY set?
LLM polishes phrasing onlydecisions unchanged
Use templated response
Display reply in chat
Append full turn to AuditTrail
Sidebar: Live escalationalerts+ downloadable JSON log
4. Policy Rules Implemented
Cancellation → free rebooking within 24h or full refund (airline-caused only).
Delay compensation (tiered):
< 3h → meal voucher (₹500)
3–5h → meal voucher + lounge access
> 5h → meal voucher + lounge access + hotel for the delayed-hours portion only (never a full night)
Refunds → always to the original payment method, 7 business days.
Fare difference on voluntary rebooking → customer pays the difference; an agent may approve up to ₹1,500; anything above that is escalated.
Loyalty tiers (Gold/Platinum) → priority rebooking only, no extra monetary compensation.
Always escalate: compensation requests beyond policy, fare differences > ₹1,500, goodwill upgrades, legal-action/formal-complaint threats, non-airline-disruption exceptions, refunds to a non-original payment method.
5. Validated Test Scenarios
#	Customer	Ask	Expected outcome	Verified
1	Priya Nair (Gold, SK4821X)	Furious; wants full cash refund + free business class upgrade	Refund ALLOWED (cancelled flight); upgrade ESCALATED	✅
2	Arvind Kulkarni (Silver, TR1190B)	Hotel accommodation for a 4h delay	Hotel DENIED (< 5h); meal voucher + lounge offered	✅
3	Meher Kaur (Platinum, WL7742)	Full night's hotel for a 6h delay; rebook to a flight with ₹2,000 fare difference	Hotel ALLOWED for delayed-hours only (not full night); fare difference ESCALATED (> ₹1,500)	✅

All three were run end-to-end against agent.py before delivery (see console output captured during development — reproducible by running the snippet below):

bash
python3 - <<'EOF'
from agent import ResolutionAgent
a = ResolutionAgent()
print(a.handle_message("SK4821X", "I am FURIOUS!! My flight was cancelled. I want a full cash refund AND a free business class upgrade for all this trouble!")["decisions"])
print(a.handle_message("TR1190B", "My flight is delayed. Can I get hotel accommodation please?")["decisions"])
print(a.handle_message("WL7742", "I need a full night's hotel stay because of this delay, and the fare difference for a higher fare flight is 2,000 rupees.")["decisions"])
EOF

You can also reproduce these instantly in the app using the "Try [Name]'s scenario" quick-test buttons above the chat window.

6. Assumptions
No live PNR/CRM system — data.py is a static in-memory substitute for what would be a booking-system and CRM integration in production.
LLM is optional and decision-free — since assessment run environments may not provide an API key, the app must work standalone; the OpenAI call only rephrases an already-decided outcome and silently falls back to a template if unavailable.
Fare-difference amount is extracted from free text via a simple currency-aware regex (₹2,000, Rs 2000, 2000, etc.). In production this would come from the fare-quote API, not from parsing chat text.
"Business days" for refunds and "delayed-hours only" hotel policy are stated as-is from the requirements and are not further interpreted.
Each browser/Streamlit session keeps its own audit log in memory (not persisted to disk/DB) — acceptable for a demo/assessment; a production system would write the audit trail to a persistent, tamper-evident store.
Sentiment/intent detection is keyword+heuristic based (not a trained classifier) to keep the solution transparent, dependency-light, and fully explainable for audit purposes — appropriate given the policy-enforcement nature of this agent.
7. AI Tools Used
Claude (Anthropic) was used to design and generate the initial architecture, rule engine, Streamlit UI, and documentation in this repository, per the assessment's own instructions to use an AI pair-programmer.
OpenAI's Chat Completions API (gpt-4o-mini) is optionally used at runtime, only to polish the tone of already-decided responses — never to make policy decisions.
8. Extending This Project
Swap data.py for real API calls to a PNR/booking system and CRM.
Replace the keyword-based sentiment/intent layers with a fine-tuned classifier or an LLM function-calling setup (LangChain/LangGraph), keeping the rule engine as a hard guardrail that the LLM's proposed action must pass through before execution.
Persist the audit trail to a database (e.g. Postgres) instead of in-memory session state.
Add authentication so each customer can only see/act on their own PNR.