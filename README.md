# Software Landing — AI-Powered Employee Onboarding Portal

The  topic is an **AI-powered onboarding assistant for new employees at TechCorp**.

The goal of the application is to eliminate the friction that new hires typically face on their first days — having to search through scattered documents, email HR, or wait for IT support to answer basic questions. Instead, employees can type any question into a conversational chat interface and receive an **instant, accurate, source-cited answer** drawn directly from official company documentation.

The assistant is specifically designed to handle questions related to:

- **IT Setup** — configuring development environments, installing dependencies, and setting up tools
- **VPN & Network Access** — connecting to the corporate VPN, zero-trust network policies, and Tailscale configuration
- **HR Policies** — vacation entitlements, expense reporting, parental leave by region, and code of conduct
- **Office & Facilities** — building access, meeting room booking, and emergency procedures
- **Company Culture** — TechCorp's history, core values, and recurring events

---

## Documents Used

The knowledge base that powers the assistant was built from a curated set of **internal TechCorp documentation**, all stored in an **Amazon S3 bucket** and synced to an **Amazon Bedrock Knowledge Base** for semantic retrieval.

The documents included are:

| File | Description |
|---|---|
| `it_setup_guide.md` | Full developer environment setup — Python/Java environments, VPN configuration (Tailscale + Duo MFA), Jenkins CI/CD pipeline authentication, Docker registry access, network security protocols, and a troubleshooting matrix |
| `hr_policies.md` | Global HR policies including regional vacation/sick leave (US, EU, APAC), expense reporting workflows, hardware procurement tiers, disciplinary protocols (PIP process), and GDPR/data classification rules |
| `company_culture.md` | TechCorp company history, five core values, and recurring events (All-Hands meetings, Friday Demos, quarterly planning) |
| `office_and_campus_guide.md` | San Francisco HQ floor directory, meeting room naming conventions and booking system, building access badge tiers, visitor registration, parking, and emergency evacuation procedures |
| `employee_directory.json` | Structured directory of 50 employees across all departments, offices, and seniority levels — used as a reference for organizational queries |

These documents were deliberately written to simulate a real enterprise environment, covering a 10,000+ employee global company with offices in San Francisco, London, Singapore, and Warsaw.

---

## How the App Works

The application follows a clean, end-to-end **Retrieval-Augmented Generation (RAG)** architecture:

1. **User Interface** — The user types a question into a conversational chat interface built with **Flask** and served as a single-page web application. The UI maintains a running chat thread, displaying both questions and answers as message bubbles without page reloads.

2. **Backend Query** — The Flask backend receives the question via a `POST /ask` request and calls the **Amazon Bedrock Knowledge Base** using the **boto3** SDK (`bedrock-agent-runtime` client, `retrieve_and_generate` API).

3. **Session Memory** — A `sessionId` returned by Bedrock on the first call is stored in Flask's server-side session cookie and passed back on every subsequent call, giving the model **full conversational memory** across multiple turns without any database.

4. **Retrieval & Generation** — Bedrock semantically searches the S3-backed knowledge base for the most relevant document chunks, then passes them as context to **Anthropic's Claude model** (Haiku 4.5, via cross-region inference profile), which synthesises a coherent, grounded answer.

5. **General Knowledge Fallback** — If no relevant document is found, Bedrock returns a fixed "unable to assist" string. The app detects this and automatically falls back to a **direct `invoke_model` call** to Claude, answering from general knowledge and labelling the source as "General Knowledge" in the UI.

6. **Source Citations** — Every answer sourced from the Knowledge Base includes the originating document filename(s), displayed as index-card style citations below the answer bubble.

7. **Containerisation** — The entire application (Flask server, templates, static assets) is packaged into a **Docker image** using a `python:3.11-slim` base, with all AWS credentials injected at runtime via `--env-file` and never baked into the image.

8. **Cloud Deployment** — The Docker container was deployed to a **public AWS EC2 instance** (Amazon Linux 2, `t2.micro`), making the application accessible over the public internet for testing and evaluation.

---

## Public IP Used During Testing

During the final deployment phase, the Dockerised application was launched on an AWS EC2 instance and confirmed to be **fully functional and publicly accessible** at the following address:

> **http://54.221.169.239:5000**


---

## AWS Resources Cleanup

**EC2 provisioned for this project have been fully terminated and deleted.**

Immediately after capturing the required screenshots and completing functional testing at the public IP above, the following cleanup actions were performed to prevent ongoing costs:

- **EC2 Instance** — terminated via the AWS Console (`Instances → Terminate Instance`)

