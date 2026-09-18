## Process & Decision Flow

```mermaid
flowchart TD
    A[Customer Message] --> B[Intent & Sentiment Detection]
    B --> C{Check Policy Rules}
    C -->|Allowed Action| D[Execute Resolution & Respond]
    C -->|Prohibited Action / Exceeds Limit| E[Flag & Escalate to Supervisor]
    D --> F[Display Status in UI]
    E --> F