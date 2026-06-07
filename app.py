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
# Route: POST /ask  — query the Bedrock Knowledge Base
# ---------------------------------------------------------------------------
@app.route("/ask", methods=["POST"])
def ask():
    """
    Accepts a JSON body: { "question": "..." }
    Calls Bedrock retrieve_and_generate and returns:
      { "answer": "...", "citations": [...], "error": null }
    """

    # Guard: verify the Agent is configured before making any AWS call
    if not AGENT_ID or not AGENT_ALIAS_ID:
        return jsonify({
            "answer": None,
            "citations": [],
            "error": (
                "Bedrock Agent is not configured. "
                "Please set AGENT_ID and AGENT_ALIAS_ID in your .env file, "
                "then restart the server."
            ),
        }), 503

    # Parse and validate the request body
    body = request.get_json(silent=True)
    if not body or not body.get("question", "").strip():
        return jsonify({
            "answer": None,
            "citations": [],
            "error": "Please enter a question before submitting.",
        }), 400

    question = body["question"].strip()

    # Call the Bedrock Agent via invoke_agent
    try:
        client = get_bedrock_client()

        # Session management for invoke_agent is different from retrieve_and_generate:
        # WE create the session ID ourselves and pass it on every call.
        # Bedrock stores the conversation history against this ID on its side.
        bedrock_session_id = session.get("bedrock_session_id")
        if not bedrock_session_id:
            # First message in this conversation — generate a fresh session ID
            bedrock_session_id = secrets.token_hex(16)
            session["bedrock_session_id"] = bedrock_session_id

        # invoke_agent returns a streaming EventStream — do NOT await it
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=bedrock_session_id,
            inputText=question,
        )

        # Walk the stream: assemble the full answer text and collect citations
        answer, citations = parse_agent_response(response)

        # An empty response is treated the same as "unable to assist"
        if not answer:
            answer = FALLBACK_TRIGGER

        # If the Agent found no relevant document, fall back to general Claude knowledge
        if answer.strip() == FALLBACK_TRIGGER:
            fallback_answer = call_general_knowledge_fallback(question)
            return jsonify({
                "answer":    fallback_answer,
                "citations": [{"source": "General Knowledge", "uri": "", "snippet": ""}],
                "error":     None,
            })

        return jsonify({
            "answer":    answer,
            "citations": citations,
            "error":     None,
        })

    # Handle AWS-specific errors
    except ClientError as e:
        code    = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]
        return jsonify({
            "answer":    None,
            "citations": [],
            "error":     f"AWS Error [{code}]: {message}",
        }), 500

    # Handle missing or invalid credentials
    except NoCredentialsError:
        return jsonify({
            "answer":    None,
            "citations": [],
            "error":     "AWS credentials are missing or invalid. Check your .env file.",
        }), 500

    # Catch-all for unexpected errors
    except Exception as e:
        return jsonify({
            "answer":    None,
            "citations": [],
            "error":     f"Unexpected error: {str(e)}",
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
