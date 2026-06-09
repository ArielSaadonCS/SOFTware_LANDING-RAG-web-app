"""
app.py — TechCorp Employee Onboarding RAG Portal

A Flask web server that accepts natural-language questions from employees
and answers them using an Amazon Bedrock Knowledge Base (retrieve_and_generate).

Usage:
    1. Fill in your .env file (copy from .env.example).
    2. pip install -r requirements.txt
    3. python app.py
    4. Open http://localhost:5000 in your browser.
"""

import os
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, session
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load all variables from the .env file into the environment
load_dotenv()

app = Flask(__name__)

# Flask needs a secret key to sign the session cookie.
# Set FLASK_SECRET_KEY in your .env for a stable value across restarts.
# The fallback is fine for development.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "techcorp-dev-secret-key-change-in-prod")

# ---------------------------------------------------------------------------
# Configuration — loaded from .env / Docker --env-file at runtime
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")

# Bedrock Agent — set these after creating the Agent in the AWS Console
AGENT_ID       = os.getenv("AGENT_ID")
AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")

# The exact string the Agent returns when no relevant document is found
FALLBACK_TRIGGER = "Sorry, I am unable to assist you with this request."

# Cross-region inference profile used for the direct fallback call to Claude
FALLBACK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# SQLite file that stores chat history (persists across restarts)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chat_history.db")

# Context prefixes injected by the frontend — stripped before DB storage
_CONTEXT_PREFIXES = (
    "[Context: Weather] ",
    "[Context: Holidays] ",
    "[Context: Employee Directory] ",
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def strip_context_prefix(text: str) -> str:
    for prefix in _CONTEXT_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title      TEXT NOT NULL DEFAULT 'New Conversation',
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            text       TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def save_exchange(session_id: str, display_question: str, answer: str) -> None:
    """Upsert the session record and append both messages to the DB."""
    now = datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    exists = cur.execute(
        "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if exists is None:
        cur.execute(
            "INSERT INTO sessions (session_id, title, updated_at) VALUES (?, ?, ?)",
            (session_id, display_question[:40], now),
        )
    else:
        cur.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id)
        )
    cur.execute(
        "INSERT INTO messages (session_id, role, text, timestamp) VALUES (?, 'user', ?, ?)",
        (session_id, display_question, now),
    )
    cur.execute(
        "INSERT INTO messages (session_id, role, text, timestamp) VALUES (?, 'agent', ?, ?)",
        (session_id, answer, now),
    )
    con.commit()
    con.close()


init_db()


# ---------------------------------------------------------------------------
# Helper — create the Bedrock Agent Runtime client
# ---------------------------------------------------------------------------
def get_bedrock_client():
    """Return a boto3 bedrock-agent-runtime client using credentials from .env."""
    return boto3.client(
        "bedrock-agent-runtime",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


def call_general_knowledge_fallback(question: str) -> str:
    """
    Called when the Knowledge Base has no relevant document for the question.
    Makes a direct invoke_model call to Claude (bedrock-runtime, not agent-runtime)
    so the model can answer from its general training knowledge.
    Returns the answer text as a plain string.
    """
    # bedrock-runtime is the client for direct model calls — different from the
    # bedrock-agent-runtime client used by retrieve_and_generate above.
    runtime_client = boto3.client(
        "bedrock-runtime",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )

    # Build the request payload for Anthropic's Messages API
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": (
            "You are a helpful general-knowledge assistant. "
            "Answer the user's question clearly and accurately using your training knowledge."
        ),
        "messages": [
            {"role": "user", "content": question}
        ],
    }

    # invoke_model expects the body as a JSON-encoded string
    response = runtime_client.invoke_model(
        modelId=FALLBACK_MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )

    # The response body is a streaming object — read it and parse the JSON
    response_body = json.loads(response["body"].read())

    # The generated text lives in the first content block
    return response_body["content"][0]["text"]


def parse_agent_response(response):
    """
    Iterates the EventStream returned by invoke_agent and assembles the full
    answer plus source citations.

    invoke_agent sends the reply as a stream of events. Each 'chunk' event
    contains a piece of the answer in chunk['bytes'] and optionally citation
    metadata in chunk['attribution'].

    Returns:
        answer_text  (str)  — the complete decoded answer
        citations    (list) — de-duplicated list of {"source", "uri", "snippet"}
    """
    full_text     = ""
    raw_citations = []

    for event in response.get("completion", []):
        # Only 'chunk' events carry answer text; skip trace / returnControl events
        if "chunk" not in event:
            continue

        chunk = event["chunk"]

        # Decode and accumulate the text fragment
        if "bytes" in chunk:
            full_text += chunk["bytes"].decode("utf-8")

        # Citations arrive in chunk['attribution']['citations'][*]['retrievedReferences']
        if "attribution" in chunk:
            for citation in chunk["attribution"].get("citations", []):
                for ref in citation.get("retrievedReferences", []):
                    s3_uri   = ref.get("location", {}).get("s3Location", {}).get("uri", "")
                    filename = s3_uri.split("/")[-1] if s3_uri else "Unknown source"
                    snippet  = ref.get("content", {}).get("text", "")[:250]
                    raw_citations.append({
                        "source":  filename,
                        "uri":     s3_uri,
                        "snippet": snippet,
                    })

    # De-duplicate citations that point to the same source file
    seen             = set()
    unique_citations = []
    for c in raw_citations:
        if c["source"] not in seen:
            seen.add(c["source"])
            unique_citations.append(c)

    return full_text.strip(), unique_citations


# ---------------------------------------------------------------------------
# Route: GET /  — render the main portal page
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Route: POST /ask  — query the Bedrock Agent
# ---------------------------------------------------------------------------
@app.route("/ask", methods=["POST"])
def ask():
    """
    Accepts a JSON body: { "question": "...", "session_id": "..." (optional) }
    Returns: { "answer": "...", "citations": [...], "session_id": "...", "error": null }

    If session_id is supplied the frontend resumes a specific past conversation;
    otherwise the current Flask session is used (or a fresh one is generated).
    """

    if not AGENT_ID or not AGENT_ALIAS_ID:
        return jsonify({
            "answer": None, "citations": [], "session_id": None,
            "error": (
                "Bedrock Agent is not configured. "
                "Please set AGENT_ID and AGENT_ALIAS_ID in your .env file, "
                "then restart the server."
            ),
        }), 503

    body = request.get_json(silent=True)
    if not body or not body.get("question", "").strip():
        return jsonify({
            "answer": None, "citations": [], "session_id": None,
            "error": "Please enter a question before submitting.",
        }), 400

    question          = body["question"].strip()
    client_session_id = body.get("session_id")  # optional — resumes a past conversation

    try:
        client = get_bedrock_client()

        # Priority: client-supplied > Flask session > brand-new
        bedrock_session_id = (
            client_session_id
            or session.get("bedrock_session_id")
            or secrets.token_hex(16)
        )
        session["bedrock_session_id"] = bedrock_session_id

        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=bedrock_session_id,
            inputText=question,
        )

        answer, citations = parse_agent_response(response)

        if not answer:
            answer = FALLBACK_TRIGGER

        if answer.strip() == FALLBACK_TRIGGER:
            fallback_answer = call_general_knowledge_fallback(question)
            save_exchange(bedrock_session_id, strip_context_prefix(question), fallback_answer)
            return jsonify({
                "answer":     fallback_answer,
                "citations":  [{"source": "General Knowledge", "uri": "", "snippet": ""}],
                "session_id": bedrock_session_id,
                "error":      None,
            })

        save_exchange(bedrock_session_id, strip_context_prefix(question), answer)
        return jsonify({
            "answer":     answer,
            "citations":  citations,
            "session_id": bedrock_session_id,
            "error":      None,
        })

    except ClientError as e:
        code    = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]
        return jsonify({
            "answer": None, "citations": [], "session_id": None,
            "error": f"AWS Error [{code}]: {message}",
        }), 500

    except NoCredentialsError:
        return jsonify({
            "answer": None, "citations": [], "session_id": None,
            "error": "AWS credentials are missing or invalid. Check your .env file.",
        }), 500

    except Exception as e:
        return jsonify({
            "answer": None, "citations": [], "session_id": None,
            "error": f"Unexpected error: {str(e)}",
        }), 500


# ---------------------------------------------------------------------------
# Route: POST /new-chat  — clear the conversation session
# ---------------------------------------------------------------------------
@app.route("/new-chat", methods=["POST"])
def new_chat():
    """Remove the stored Bedrock session ID so the next /ask starts a fresh conversation."""
    session.pop("bedrock_session_id", None)
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Route: GET /chats  — list all past sessions
# ---------------------------------------------------------------------------
@app.route("/chats", methods=["GET"])
def get_chats():
    """Return up to 50 past sessions ordered by most-recent activity."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT session_id, title, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 50"
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Route: GET /chats/<session_id>  — full message history for one session
# ---------------------------------------------------------------------------
@app.route("/chats/<session_id>", methods=["GET"])
def get_chat_messages(session_id):
    """Return all messages for the requested session in chronological order."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT role, text, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  TechCorp Onboarding Portal — Starting Up")
    print("=" * 50)
    print(f"  AWS Region        : {AWS_REGION}")
    print(f"  Agent ID          : {AGENT_ID       or '⚠ NOT SET'}")
    print(f"  Agent Alias ID    : {AGENT_ALIAS_ID or '⚠ NOT SET'}")
    print("=" * 50)
    if not AGENT_ID or not AGENT_ALIAS_ID:
        print("  WARNING: Set AGENT_ID and AGENT_ALIAS_ID in .env")
        print("           to enable Bedrock Agent queries.\n")
    print("  Running at: http://localhost:5000\n")
    # host='0.0.0.0' is required inside Docker so the container
    # accepts connections from outside (the host machine).
    # Outside Docker it behaves identically to 127.0.0.1.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
