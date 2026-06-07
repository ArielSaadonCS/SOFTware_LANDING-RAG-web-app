# Software Landing — AI-Powered Employee Onboarding Portal

An **AI-powered onboarding assistant for new employees at TechCorp**, built with Flask, Amazon Bedrock Agent, and a skeuomorphic office-desk UI.

The goal is to eliminate the friction new hires face on their first days — searching through scattered documents, emailing HR, or waiting for IT support. Employees type any question into a conversational chat interface and receive an **instant, accurate, source-cited answer** drawn directly from official company documentation.

---

## Features

- **RAG via Amazon Bedrock Agent** — questions are answered using retrieval-augmented generation over a knowledge base of official TechCorp documents stored in Amazon S3
- **Three-tab navigation** — Knowledge Base, Weather & Lunch, and Upcoming Holidays tabs each surface different quick topics and inject hidden context tags (`[Context: Weather]` / `[Context: Holidays]`) into backend queries; the Weather and Holiday features are backed by **AWS Lambda functions** invoked through the Bedrock Agent as tools, enabling real-time data retrieval beyond the static knowledge base
- **General knowledge fallback** — if the Bedrock Agent cannot answer from documents, the app automatically falls back to Claude Haiku (`invoke_model`) for general responses
- **Conversational memory** — session-based `sessionId` (generated with `secrets.token_hex`) keeps multi-turn context across the same conversation; "New Conversation" resets it
- **Context-aware ink stamps** — the frontend detects temperatures (Celsius regex) and holiday keywords in responses and renders matching hand-drawn SVG ink-stamp graphics inside the answer bubble
- **Dynamic home page** — intro text and quick-topic chips update automatically when switching tabs
- **Skeuomorphic office-desk UI** — wood-grain desk background, cream ruled-paper chat area, physical folder tabs, binder holes, metallic paperclip, sticky-note suggestion chips, and typewriter fonts
- **Docker containerised** — runs identically locally and on AWS EC2; credentials are never baked into the image

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask |
| AI / RAG | Amazon Bedrock Agent (`bedrock-agent-runtime`, `invoke_agent`) |
| Fallback LLM | Amazon Bedrock `invoke_model` — Claude Haiku (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) |
| AWS SDK | boto3 |
| Frontend | Vanilla HTML / CSS / JavaScript (no framework) |
| Containerisation | Docker (`python:3.11-slim`) |
| Cloud | AWS EC2, Amazon S3, Amazon Bedrock Knowledge Base |

---

## Project Structure

```
mid_project/
├── app.py                  # Flask backend — /ask, /new-chat routes
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build instructions
├── .env.example            # Required environment variables (template)
├── templates/
│   └── index.html          # Single-page frontend (HTML + CSS + JS)
├── static/
│   └── style.css           # Skeuomorphic office-desk theme (~1100 lines)
└── data/                   # Source documents synced to S3 / Bedrock KB
    ├── it_setup_guide.md
    ├── hr_policies.md
    ├── company_culture.md
    ├── office_and_campus_guide.md
    └── employee_directory.json
```

---

## Knowledge Base Documents

All documents are stored in an **Amazon S3 bucket** and indexed by an **Amazon Bedrock Knowledge Base** for semantic retrieval.

| File | Contents |
|---|---|
| `it_setup_guide.md` | Developer environment setup, VPN (Tailscale + Duo MFA), Jenkins CI/CD, Docker registry, network security, troubleshooting |
| `hr_policies.md` | Vacation / sick leave by region (US, EU, APAC), expense reporting, hardware procurement, disciplinary protocols, GDPR |
| `company_culture.md` | Company history, five core values, All-Hands meetings, Friday Demos, quarterly planning |
| `office_and_campus_guide.md` | SF HQ floor directory, meeting room booking, badge tiers, visitor registration, emergency evacuation |
| `employee_directory.json` | Structured directory of 50 employees across all departments and offices |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- An AWS account with the following resources provisioned:
  - **Amazon Bedrock Agent** with an alias (note the Agent ID and Alias ID)
  - **Amazon Bedrock Knowledge Base** attached to the agent, backed by an S3 bucket containing the documents in `data/`
  - IAM user or role with permissions for `bedrock-agent-runtime:InvokeAgent` and `bedrock-runtime:InvokeModel`
- AWS credentials (Access Key ID + Secret Access Key) for the above IAM identity

> **Note:** The Bedrock Agent must be in `us-east-1`. The fallback model uses a cross-region inference profile (`us.` prefix) which requires the `us-east-1` region.

---

## Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/ArielSaadonCS/mid_project.git
cd mid_project
```

### 2. Create the `.env` file

Copy the template and fill in your values:

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

FLASK_SECRET_KEY=change-this-to-a-random-secret
```

> **Never commit `.env` to git.** It is listed in `.gitignore`.

---

## Running with Docker (recommended)

### Build the image

```bash
docker build -t techcorp-onboarding .
```

### Start the container

```bash
docker run -d -p 5000:5000 --env-file .env --name onboarding techcorp-onboarding
```

### Open the app

```
http://localhost:5000
```

### Stop the container

```bash
docker stop onboarding
```

### Rebuild after code changes

```bash
docker stop onboarding && docker rm onboarding
docker build -t techcorp-onboarding .
docker run -d -p 5000:5000 --env-file .env --name onboarding techcorp-onboarding
```

---

## Running Locally (without Docker)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Start the Flask development server
python app.py
```

Then open `http://localhost:5000`.

---

## How It Works

```
Browser  →  POST /ask  →  Flask  →  Bedrock Agent (invoke_agent)
                                          │
                                          ▼
                                   RAG: searches S3-backed
                                   Knowledge Base for relevant
                                   document chunks
                                          │
                                          ▼
                                   Claude generates answer
                                   grounded in retrieved docs
                                          │
                          ┌─────────────-┘
                          │  If agent returns "unable to assist"
                          ▼
                   Fallback: invoke_model → Claude Haiku
                   (general knowledge, labelled in UI)
                          │
                          ▼
              Flask parses EventStream → returns JSON
              {answer, citations}
                          │
                          ▼
              Frontend renders answer bubble +
              optional ink-stamp graphic
```

### Tab context injection

When the user submits a question from the **Weather & Lunch** or **Upcoming Holidays** tab, the JavaScript prepends a hidden context tag to the query before sending it to the backend:

| Active tab | Prefix added to backend query |
|---|---|
| Knowledge Base | *(none)* |
| Weather & Lunch | `[Context: Weather] ` |
| Upcoming Holidays | `[Context: Holidays] ` |

The user only sees their original question in the chat; the prefix is invisible in the UI.

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Serves the main page |
| `POST` | `/ask` | Accepts `{ "question": "..." }`, returns `{ "answer": "...", "citations": [...] }` |
| `POST` | `/new-chat` | Clears the Bedrock session ID from the Flask session cookie |

---

## Cloud Deployment (EC2)

To deploy on an AWS EC2 instance:

```bash
# On the EC2 instance — install Docker
sudo yum update -y && sudo yum install docker -y
sudo service docker start
sudo usermod -aG docker ec2-user

# Transfer your project files (scp or git clone), then:
docker build -t techcorp-onboarding .
docker run -d -p 5000:5000 --env-file .env --name onboarding techcorp-onboarding
```

The app will be accessible at `http://<EC2-PUBLIC-IP>:5000`.

Make sure port 5000 is open in the EC2 Security Group (inbound TCP rule).
