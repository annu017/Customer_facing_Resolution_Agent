### System Architecture & Decision Flow

```mermaid
graph TD
    A[Customer Message] --> B[Intent & Sentiment Detection]
    B --> C{Violates Prohibited Rules?}
    C -- Yes (e.g. Fare Diff > ₹1500) --> D[Trigger Supervisor Escalation Log]
    C -- No --> E[Apply Python Policy Rule Engine]
    E --> F[Generate Dynamic Response & Action]