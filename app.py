"""
app.py — TechCorp Employee Onboarding RAG Portal

A Flask web server that accepts natural-language questions from employees
and answers them using an Amazon Bedrock Knowledge Base (retrieve_and_generate).

Usage:
    1. Fill in your .env file (copy from .env.example).
    2. pip install -r requirements.txt
    3. python app.py
    4. Open http://localhost:5001 in your browser.
"""

import os
import json
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
# Configuration — loaded from .env
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")

# These two are set AFTER you create the Knowledge Base in the AWS Console
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")

# Accepts either a full ARN or a plain model ID.
# If a model ID is given (e.g. "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
# it is automatically expanded into the required ARN format.
_MODEL_ARN_RAW = os.getenv("MODEL_ARN", "")


def build_model_arn(value: str) -> str:
    """
    Return a Bedrock-compatible model ARN.
    If `value` is already a full ARN (starts with "arn:") it is returned as-is.
    Otherwise it is treated as a model ID and wrapped in the standard ARN format.
    """
    if value.startswith("arn:"):
        return value
    # Construct the ARN from the region + model ID
    return f"arn:aws:bedrock:{AWS_REGION}::foundation-model/{value}"


MODEL_ARN = build_model_arn(_MODEL_ARN_RAW) if _MODEL_ARN_RAW else ""

# The exact string Bedrock returns when no relevant document exists in the KB
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

    # Guard: verify Bedrock is configured before making any AWS call
    if not KNOWLEDGE_BASE_ID or not MODEL_ARN:
        return jsonify({
            "answer": None,
            "citations": [],
            "error": (
                "The Bedrock Knowledge Base is not configured yet. "
                "Please set KNOWLEDGE_BASE_ID and MODEL_ARN in your .env file, "
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

    # Call Amazon Bedrock retrieve_and_generate
    try:
        client = get_bedrock_client()

        # Read the Bedrock session ID stored from the previous turn (None on first message).
        # Passing it back to Bedrock lets the model remember earlier Q&A in this conversation.
        bedrock_session_id = session.get("bedrock_session_id")

        # Build the request dictionary step by step (simple and easy to read)
        bedrock_request = {
            "input": {"text": question},
            "retrieveAndGenerateConfiguration": {
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": MODEL_ARN,
                },
            },
        }

        # Only add sessionId when we already have one from a previous turn
        if bedrock_session_id:
            bedrock_request["sessionId"] = bedrock_session_id

        response = client.retrieve_and_generate(**bedrock_request)

        # Save the sessionId Bedrock returned so the next request continues this conversation
        session["bedrock_session_id"] = response.get("sessionId")

        # The generated answer lives at response["output"]["text"]
        answer = response.get("output", {}).get("text", "No answer returned.")

        # If Bedrock found no relevant document in the Knowledge Base it returns
        # this exact string. Fall back to a direct Claude call so the user still
        # gets a helpful response from the model's general knowledge.
        if answer == FALLBACK_TRIGGER:
            fallback_answer = call_general_knowledge_fallback(question)
            return jsonify({
                "answer":    fallback_answer,
                "citations": [{"source": "General Knowledge", "uri": "", "snippet": ""}],
                "error":     None,
            })

        # Extract source citations from the response.
        # Each citation can have multiple retrievedReferences pointing back to S3 objects.
        citations = []
        for citation in response.get("citations", []):
            for ref in citation.get("retrievedReferences", []):
                # Pull the S3 URI from the location object
                s3_uri  = ref.get("location", {}).get("s3Location", {}).get("uri", "")
                # Show just the filename, not the full s3://bucket/path
                filename = s3_uri.split("/")[-1] if s3_uri else "Unknown source"
                # Grab the first 250 characters of the retrieved chunk as a preview
                snippet  = ref.get("content", {}).get("text", "")[:250]
                citations.append({
                    "source":  filename,
                    "uri":     s3_uri,
                    "snippet": snippet,
                })

        # De-duplicate citations that point to the same source file
        seen = set()
        unique_citations = []
        for c in citations:
            if c["source"] not in seen:
                seen.add(c["source"])
                unique_citations.append(c)

        return jsonify({
            "answer":    answer,
            "citations": unique_citations,
            "error":     None,
        })

    # Handle AWS-specific errors with targeted, actionable messages
    except ClientError as e:
        code    = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]

        # ValidationException with "inference profile" in the message means the
        # MODEL_ARN points to a plain model ID. Claude 3.5+ and Claude 4.x models
        # require a cross-region inference profile ARN instead.
        # Fix: add the regional prefix "us." (or "eu." / "ap.") before the model ID.
        #
        # Wrong:  arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0
        # Correct: arn:aws:bedrock:us-east-1::foundation-model/us.anthropic.claude-haiku-4-5-20251001-v1:0
        if code == "ValidationException" and "inference profile" in message.lower():
            # Try to build the corrected ARN automatically so the user can copy-paste it
            suggested = MODEL_ARN or ""
            # Insert "us." before the model slug if it's a plain foundation-model ARN
            if "foundation-model/anthropic." in suggested:
                suggested = suggested.replace(
                    "foundation-model/anthropic.",
                    "foundation-model/us.anthropic.",
                )
            hint = (
                "Your MODEL_ARN uses a direct model ID. "
                "Claude 3.5+ and Claude 4.x models require a cross-region inference profile ARN. "
                "Update MODEL_ARN in your .env file and restart the server.\n\n"
                f"Suggested fix:\nMODEL_ARN={suggested}"
            )
            return jsonify({
                "answer":    None,
                "citations": [],
                "error":     hint,
            }), 400

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
    print(f"  Knowledge Base ID : {KNOWLEDGE_BASE_ID or '⚠ NOT SET'}")
    print(f"  Model ARN         : {MODEL_ARN or '⚠ NOT SET'}")
    print("=" * 50)
    if not KNOWLEDGE_BASE_ID or not MODEL_ARN:
        print("  WARNING: Set KNOWLEDGE_BASE_ID and MODEL_ARN in .env")
        print("           to enable Bedrock queries.\n")
    print("  Running at: http://localhost:5000\n")
    # host='0.0.0.0' is required inside Docker so the container
    # accepts connections from outside (the host machine).
    # Outside Docker it behaves identically to 127.0.0.1.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
