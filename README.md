## Process & Decision Flow

```mermaid
flowchart TD
    A[Customer Message] --> B[Intent & Sentiment Detection]
    B --> C{Check Policy Rules}
    C -->|Allowed Action| D[Execute Resolution & Respond]
    C -->|Prohibited Action / Exceeds Limit| E[Flag & Escalate to Supervisor]
    D --> F[Display Status in UI]
    E --> F




     AI Tools Used

This project was developed with assistance from AI tools as permitted by the assignment brief:

Gemini (Google): Used as a technical collaborator for initial project architecture setup, virtual environment configuration, terminal troubleshooting, and Git integration.
Cursor AI: Used as the primary AI-native code editor for automated code generation, real-time code completions, refactoring file structures, and linking imported modules across `app.py` and `src/`.
Claude AI (Anthropic): Used for deep reasoning and writing complex Python logic, specifically structuring the deterministic policy enforcement engine and handling scenario edge cases.
ChatGPT / GitHub Copilot: Used for rapid code snippet validation, syntax checking, and drafting mock data models.