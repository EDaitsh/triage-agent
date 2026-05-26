# Triage Agent — AI Support Automation

An AI-powered support triage system for SaaS companies.  
The system receives user messages, classifies them, generates responses, evaluates them, and escalates to a human when needed — all automatically.

---

## Architecture

```
User Message
     │
     ▼
  Router         → Classifies the request (support / bug / inquiry / spam / urgent_human)
     │
     ▼
  Worker         → Generates a response based on the category (up to 2 attempts)
     │
     ▼
  Evaluator      → Validates the response quality
     │
     ▼
  HITL           → Human-in-the-Loop approval (when required)
     │
     ▼
  Final Output
```

### Components

| Component | Role |
|-----------|------|
| **Router** | Categorizes the incoming message |
| **Worker** | Generates a draft response or GitHub issue |
| **Evaluator** | Quality-checks the worker's output |
| **HITL** | Human review step for sensitive/urgent cases |

---

## Tech Stack

- **Backend:** Python, FastAPI, OpenAI API (GPT-4o)
- **Frontend:** React (Vite)
- **Infrastructure:** Docker, Docker Compose
- **Proxy:** Nginx

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- An OpenAI API key

### Setup

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd <repo-folder>
   ```

2. Set your OpenAI API key as an environment variable:

   **Windows (PowerShell):**
   ```powershell
   $env:OPENAI_API_KEY="sk-..."
   ```

   **macOS / Linux:**
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   Or create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=sk-...
   ```

3. Build and run:
   ```bash
   docker-compose up --build
   ```

### Access

| Service | URL |
|---------|-----|
| Frontend | http://localhost:80 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app & endpoints
│   │   ├── workflow.py    # Main agent workflow (Router → Worker → Evaluator → HITL)
│   │   ├── llm.py         # OpenAI client wrapper
│   │   ├── prompts.py     # System prompts for each agent
│   │   ├── models.py      # Pydantic response models
│   │   └── store.py       # In-memory task store
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── App.jsx        # Main React UI
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
└── docker-compose.yml
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/message` | Submit a new message, returns `task_id` |
| `GET` | `/tasks/{task_id}` | Get current task status |
| `POST` | `/tasks/{task_id}/approve` | Approve a pending HITL task |
| `POST` | `/tasks/{task_id}/reject` | Reject a pending HITL task |

---

## Message Categories

| Category | Description |
|----------|-------------|
| `support` | General support question → direct answer |
| `bug` | Bug report → draft GitHub Issue |
| `inquiry` | General inquiry → informational response |
| `spam` | Spam → blocked |
| `urgent_human` | Urgent → immediate human escalation |
