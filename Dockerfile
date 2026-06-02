# ============================================================
# Dockerfile — TechCorp Employee Onboarding Portal
# ============================================================
# Build:  docker build -t techcorp-onboarding .
# Run:    docker run -p 5001:5001 --env-file .env techcorp-onboarding
# ============================================================

# Use the official slim Python 3.11 image as the base.
# "slim" removes test files and docs, keeping the image small (~130 MB).
FROM python:3.11-slim

# ---------------------------------------------------------------------------
# 1. Set the working directory inside the container.
#    All subsequent COPY, RUN, and CMD instructions operate from here.
# ---------------------------------------------------------------------------
WORKDIR /app

# ---------------------------------------------------------------------------
# 2. Install Python dependencies.
#    Copying requirements.txt BEFORE the rest of the source code means
#    Docker can cache this layer — a pure code change won't re-run pip.
# ---------------------------------------------------------------------------
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# 3. Copy only the files the running application needs.
#    Everything else is excluded via .dockerignore.
# ---------------------------------------------------------------------------
COPY app.py       .
COPY templates/   ./templates/
COPY static/      ./static/

# ---------------------------------------------------------------------------
# 4. Document the port the app listens on.
#    This is metadata only — the actual port mapping is set with -p at runtime.
# ---------------------------------------------------------------------------
EXPOSE 5001

# ---------------------------------------------------------------------------
# 5. Default environment variables.
#    These are safe non-secret defaults; real secrets are injected at runtime
#    via --env-file .env and are never baked into the image.
# ---------------------------------------------------------------------------
ENV FLASK_DEBUG=false
ENV AWS_REGION=us-east-1

# ---------------------------------------------------------------------------
# 6. Start the Flask application.
#    Uses exec form (JSON array) so signals (Ctrl+C, docker stop) are
#    forwarded directly to the Python process, not a shell wrapper.
# ---------------------------------------------------------------------------
CMD ["python", "app.py"]
