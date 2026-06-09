# Software Landing — AI-Powered Employee Onboarding Portal

> **"A soft landing for every new hire."**

**Software Landing** is an intelligent, conversational onboarding assistant built for new employees at TechCorp. It eliminates the friction of first-day orientation — no more hunting through scattered documents, emailing HR, or waiting for IT support. New hires simply type any question into a chat interface and receive an **instant, source-cited answer** drawn from official company documentation, enriched with real-time data from live tool integrations.

Powered by an **Amazon Bedrock Agent** running the **Claude Haiku 4.5** model, the system autonomously decides which tool or knowledge source to invoke for each query — with no hard-coded routing logic required.

---

## Architecture Overview

```
Browser
  │
  ├─► POST /ask  (Flask)
  │         │
  │         ▼
  │   Amazon Bedrock Agent  (Claude Haiku 4.5 · invoke_agent)
  │         │
  │         ├─► Knowledge Base (RAG)  ─────────► S3 bucket (onboarding docs)
  │         │
  │         ├─► Lambda: Weather          real-time weather data
  │         ├─► Lambda: Upcoming Holidays   company holiday calendar
  │         └─► Lambda: Employee Directory  reads employee_directory.json from S3
  │         │
  │         └─► Fallback: invoke_model → Claude Haiku (general knowledge)
  │
  ├─► GET  /chats            (list chat history — SQLite)
  └─► GET  /chats/<id>       (load a specific past conversation)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, Flask |
| **AI / Agent** | Amazon Bedrock Agent — Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) |
| **RAG** | Amazon Bedrock Knowledge Base backed by Amazon S3 |
| **Agent Tools** | 3 AWS Lambda Action Groups (Weather, Holidays, Directory) |
| **AWS SDK** | boto3 (`bedrock-agent-runtime`, `bedrock-runtime`) |
| **Chat History** | SQLite (`data/chat_history.db`) via Python's built-in `sqlite3` |
| **Frontend** | Vanilla HTML / CSS / JavaScript — skeuomorphic office-desk theme |
| **Containerisation** | Docker (`python:3.11-slim`) |
| **Cloud** | AWS EC2, Amazon S3, Amazon Bedrock, Amazon Bedrock Guardrails |

---

## Features

### Conversational AI
- **Multi-turn memory** — Bedrock maintains conversation context across turns using a persistent `sessionId`; the "New Conversation" button resets it cleanly
- **General knowledge fallback** — if the agent cannot answer from documents, the app automatically calls `invoke_model` (Claude Haiku) and labels the answer as general knowledge in the UI
- **Persistent chat history** — every conversation is saved to a local SQLite database; users can browse, resume, and continue any past session via the in-app history sidebar

### Agent Action Groups (Lambda Tools)

The Bedrock Agent autonomously decides which tool to call based on the user's question:

| Tool | Lambda Description |
|---|---|
| **Weather** | Fetches the current local weather for the requested office city and returns a forecast with clothing recommendations |
| **Upcoming Holidays** | Checks the official company holiday calendar for the specified region/office and returns upcoming days off and office closures |
| **Employee Directory** | A custom Python Lambda that reads `employee_directory.json` **directly from the S3 bucket at runtime**, enabling complex structured queries filtered by role, department, location, or name |

### Frontend UI
- **4 topic tabs** — each tab surfaces contextual suggestions and injects a routing hint to the backend (see Context Injection below)
- **Skeuomorphic office-desk design** — wood-grain desk surface, cream paper notebook, physical binder holes, metallic paperclip, sticky-note suggestion chips, typewriter fonts, and brass nameplate header
- **Context-aware ink stamps** — the frontend detects temperature values (°C regex) and holiday keywords in agent responses and renders matching hand-drawn SVG doodles inside the answer bubble
- **Chat history sidebar** — a slide-in filing-cabinet drawer lists all past conversations; clicking any entry re-renders the full thread and resumes Bedrock context for that session

---

## Context Injection

When the user submits a question, the JavaScript **silently prepends a hidden context tag** to the query before sending it to the backend. This tells the Bedrock Agent which Action Group to prioritise without exposing the tag to the user in the chat UI.

| Tab | Context tag injected | Bedrock routing |
|---|---|---|
| Knowledge Base | *(none)* | RAG over onboarding documents |
| Weather & Lunch | `[Context: Weather] ` | Weather Lambda |
| Upcoming Holidays | `[Context: Holidays] ` | Holidays Lambda |
| Employee Directory | `[Context: Employee Directory] ` | Directory Lambda (S3) |

---

## Security & Guardrails

The agent is protected by **Amazon Bedrock Guardrails**, configured at the infrastructure level. The following categories of queries are **automatically blocked and refused** — regardless of how the question is phrased:

| Blocked Category | Examples |
|---|---|
| **Sensitive PII** | Requests for personal identification numbers, passport details, or private contact information |
| **Compensation & equity** | Employee salaries, bonus structures, stock options, or equity grants |
| **Legal & HR complaints** | Legal interpretations of company policy, filing formal complaints, or HR dispute advice |
| **IT security bypass** | Circumventing VPN rules, disabling MFA, or bypassing security protocols |

Guardrails operate at the **model invocation level** — the agent never generates a response for these topics, even when framed as hypothetical or indirect questions.

---

## Project Structure

```
mid_project/
├── app.py                    # Flask backend — /ask, /new-chat, /chats routes + SQLite helpers
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container build instructions
├── .env.example              # Required environment variable template
├── templates/
│   └── index.html            # Single-page frontend (HTML + CSS + JS)
├── static/
│   └── style.css             # Skeuomorphic office-desk theme
└── data/
    ├── chat_history.db       # SQLite chat history (auto-created on first run)
    ├── employee_directory.json  # Employee data (also read by Lambda directly from S3)
    ├── it_setup_guide.md
    ├── hr_policies.md
    ├── company_culture.md
    └── office_and_campus_guide.md
```

---

## Knowledge Base Documents

All Markdown documents are stored in an **Amazon S3 bucket** and indexed by an **Amazon Bedrock Knowledge Base** for semantic retrieval. `employee_directory.json` is also in S3 and read at runtime by the Directory Lambda.

| File | Contents |
|---|---|
| `it_setup_guide.md` | Developer environment, VPN (Tailscale + Duo MFA), Jenkins CI/CD, Docker registry, network security, troubleshooting |
| `hr_policies.md` | Vacation / sick leave by region (US, EU, APAC), expense reporting, hardware procurement, disciplinary protocols, GDPR |
| `company_culture.md` | Company history, five core values, All-Hands meetings, Friday Demos, quarterly planning |
| `office_and_campus_guide.md` | SF HQ floor directory, meeting room booking, badge tiers, visitor registration, emergency evacuation |
| `employee_directory.json` | Structured directory of 50 employees across all departments and offices (SF, London, Singapore, Warsaw) |

---

## Prerequisites

- An AWS account with the following resources provisioned:
  - **Amazon Bedrock Agent** with an alias — note the Agent ID and Alias ID
  - **Amazon Bedrock Knowledge Base** attached to the agent, backed by an S3 bucket containing the files in `data/`
  - **3 Lambda Action Groups** configured on the agent (Weather, Holidays, Employee Directory)
  - **Amazon Bedrock Guardrails** applied to the agent alias
  - IAM user or role with `bedrock-agent-runtime:InvokeAgent` and `bedrock-runtime:InvokeModel` permissions
- AWS credentials (Access Key ID + Secret Access Key)
- Python 3.11+ **or** Docker Desktop

> **Region note:** The agent must be in `us-east-1`. The fallback model uses a cross-region inference profile (`us.` prefix) which requires this region.

---

## Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/ArielSaadonCS/mid_project.git
cd mid_project
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1

AGENT_ID=your_bedrock_agent_id
AGENT_ALIAS_ID=your_bedrock_agent_alias_id

FLASK_SECRET_KEY=change-this-to-a-long-random-string
```

> **Never commit `.env` to git.** It is listed in `.gitignore`.

---

## Running the App

### Option A — Local Python (recommended for development)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Start the Flask server
python app.py
```

Open `http://localhost:5000` in your browser.

The SQLite database (`data/chat_history.db`) is created automatically on first run.

### Option B — Docker

```bash
# Build the image
docker build -t software-landing .

# Start the container
docker run -d -p 5000:5000 --env-file .env --name onboarding software-landing

# Open the app
# http://localhost:5000

# Stop and remove
docker stop onboarding && docker rm onboarding
```

---

## API Endpoints

| Method | Route | Body / Params | Description |
|---|---|---|---|
| `GET` | `/` | — | Renders the main page |
| `POST` | `/ask` | `{ "question": "...", "session_id": "..." }` | Queries the Bedrock Agent; `session_id` is optional — omit to start a new conversation or supply an existing one to resume |
| `POST` | `/new-chat` | — | Clears the server-side Bedrock session |
| `GET` | `/chats` | — | Returns up to 50 past sessions ordered by last activity |
| `GET` | `/chats/<session_id>` | — | Returns the full message history for a specific session |

**Response shape for `/ask`:**
```json
{
  "answer": "...",
  "citations": [{ "source": "hr_policies.md", "uri": "s3://...", "snippet": "..." }],
  "session_id": "a3f8...",
  "error": null
}
```

---

## Cloud Deployment (EC2)

```bash
# On the EC2 instance — install Docker
sudo yum update -y && sudo yum install docker -y
sudo service docker start
sudo usermod -aG docker ec2-user

# Transfer project files (scp or git clone), then:
docker build -t software-landing .
docker run -d -p 5000:5000 --env-file .env --name onboarding software-landing
```

The app will be accessible at `http://<EC2-PUBLIC-IP>:5000`.

Ensure port **5000** is open in the EC2 Security Group (inbound TCP rule).
