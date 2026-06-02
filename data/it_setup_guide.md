# IT Setup Guide — TechCorp Global Engineering

## Overview

Welcome to TechCorp Engineering. This guide is the authoritative reference for configuring a compliant, fully operational engineering workstation at TechCorp. It applies to all engineering roles across all global offices (San Francisco, London, Singapore, Warsaw, Toronto, and Sydney) and all remote employees.

Complete every section relevant to your role before your first sprint. Skipping sections is not permitted — non-compliant machines are automatically flagged by our endpoint detection agent (**CrowdStrike Falcon**) and will lose access to internal resources within 72 hours of onboarding.

**Primary support contacts:**

| Issue Type | Channel | SLA |
|---|---|---|
| Access provisioning | it-access@techcorp.io | 4 business hours |
| Hardware / OS | it-support@techcorp.io | 8 business hours |
| Security incident | security@techcorp.io | 30 minutes (24/7) |
| Slack | `#it-help` | Best effort |
| On-call incident bridge | `#incident-response` | Immediate |

All tickets are tracked in **ServiceNow** at `servicenow.techcorp.io`. Reference your ticket number in all follow-up communications.

---

## Section 1 — Workstation Provisioning & Baseline Configuration

### 1.1 Minimum Hardware Specifications

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 8 cores (x86-64 or Apple Silicon) | 12+ cores |
| RAM | 16 GB | 32 GB |
| Storage | 512 GB NVMe SSD | 1 TB NVMe SSD |
| Display | 1080p | 1440p or 4K |
| Network | 100 Mbps | 1 Gbps wired |

For roles involving ML model training or large-scale data processing, an additional GPU workstation allocation must be requested via `hardware-requests@techcorp.io` with manager approval.

### 1.2 Operating System Requirements

TechCorp officially supports the following operating system configurations. Unsupported OS versions will not receive IT assistance and may be blocked from internal network access.

- **macOS**: Ventura 13.6+ or Sonoma 14+ (Apple Silicon and Intel)
- **Linux**: Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (x86-64 only for containerized workloads)
- **Windows**: Windows 11 22H2+ with WSL2 (Ubuntu 22.04 WSL distribution required)

### 1.3 Initial OS Hardening

Before installing any development tooling, apply the baseline OS hardening steps:

**macOS:**

```bash
# Enable full-disk encryption (FileVault)
sudo fdesetup enable

# Enable firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on

# Disable remote login (SSH) if not required for your role
sudo systemsetup -setremotelogin off

# Verify Gatekeeper is enforcing signed code
spctl --status
# Expected output: assessments enabled
```

**Ubuntu / Linux:**

```bash
# Apply all pending security patches
sudo apt update && sudo apt upgrade -y

# Enable and configure UFW (Uncomplicated Firewall)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
sudo ufw status verbose

# Disable unused services
sudo systemctl disable avahi-daemon cups bluetooth 2>/dev/null || true

# Install and run Lynis for a baseline audit score
sudo apt install -y lynis
sudo lynis audit system --quick
# Target score: 70 or higher. Remediate any CRITICAL findings before proceeding.
```

### 1.4 Endpoint Security Agent

Install **CrowdStrike Falcon** before connecting to any internal resource. The installer is available in the internal software portal at `software.techcorp.io` under `Security > Endpoint Protection`.

```bash
# Linux — example install after downloading the .deb package
sudo dpkg -i falcon-sensor_*.deb
sudo /opt/CrowdStrike/falconctl -s --cid=<CUSTOMER_ID_FROM_IT>

# Verify the sensor is running
sudo systemctl status falcon-sensor
```

The Customer ID (CID) is provided by IT during account provisioning. The sensor runs in the background and reports to TechCorp's Falcon tenant. It does **not** access personal data on your machine, but it does monitor process execution, network connections, and file system events on company-managed paths.

---

## Section 2 — VPN Connection & Zero-Trust Network Access

### 2.1 Architecture Overview

TechCorp implements a **zero-trust network architecture (ZTNA)** using **Tailscale** as the mesh VPN layer and **Cloudflare Access** as the application-layer policy enforcement point. This means:

- VPN connectivity alone does not grant access to applications.
- Each internal application evaluates your identity, device posture, and geographic location independently.
- Device posture is evaluated continuously, not just at login time. A machine that falls out of compliance (e.g., CrowdStrike sensor stops reporting) will lose access silently.

### 2.2 Tailscale Installation

```bash
# macOS — via Homebrew
brew install --cask tailscale

# Ubuntu / Debian
curl -fsSL https://tailscale.com/install.sh | sh

# Windows (PowerShell as Administrator)
winget install Tailscale.Tailscale
```

Alternatively, download from the internal mirror at `software.techcorp.io/tailscale` to avoid hitting Tailscale's public CDN on restricted networks.

### 2.3 Authentication & MFA

```bash
# Bring up the Tailscale daemon and authenticate
sudo tailscale up --login-server=https://vpn-idp.techcorp.io --operator=$USER
```

You will be redirected to TechCorp's IdP (Okta). Complete the following:

1. Sign in with your `@techcorp.io` Google Workspace account.
2. Complete Duo Security push MFA on your registered device.
3. If logging in from a new country or unusual IP range, a **step-up authentication** challenge will appear requiring a hardware FIDO2 token (YubiKey). Contact IT in advance when traveling internationally.

### 2.4 Verifying VPN Connectivity

```bash
# Confirm Tailscale reports your device as authenticated
tailscale status

# Verify reachability of internal DNS
dig @100.100.100.100 internal.techcorp.io

# Confirm connectivity to the internal health endpoint
curl -v https://internal.techcorp.io/health
# Expected: HTTP/2 200

# Check your assigned Tailscale IP (should be in the 100.x.x.x range)
tailscale ip -4
```

### 2.5 VPN Network Segments

Internal services are segmented into ACL-controlled network groups. Your access depends on your role:

| Segment | CIDR | Accessible By |
|---|---|---|
| `prod-cluster` | 10.0.0.0/16 | SRE, Senior Engineers (requires justification ticket) |
| `staging-cluster` | 10.1.0.0/16 | All engineers |
| `dev-services` | 10.2.0.0/16 | All engineers |
| `data-platform` | 10.3.0.0/16 | Data Engineering, Data Science |
| `corp-infra` | 10.4.0.0/16 | IT, Security, Infrastructure |

Access to `prod-cluster` requires a ServiceNow access request approved by your Engineering Director and the Security team. Requests are reviewed within 2 business days.

### 2.6 VPN Usage Policy

- The VPN must be active whenever accessing any internal resource, including staging environments, internal dashboards, code repositories, and databases.
- Do not split-tunnel personal traffic through the VPN. TechCorp's Tailscale ACLs are configured to route only RFC 1918 internal traffic through the mesh; your public internet traffic is not routed through TechCorp infrastructure.
- Do not install third-party VPN clients (NordVPN, ExpressVPN, Mullvad, etc.) on company-managed devices. They may interfere with Tailscale routing and will be flagged by CrowdStrike.

---

## Section 3 — Advanced Developer Environments

### 3.1 Python Development Environment

TechCorp's backend services are built on Python 3.11 (LTS). The following setup is mandatory for all backend and data engineers.

#### 3.1.1 Python Version Management

Do **not** use the system Python. All Python versions must be managed through **pyenv** to enable per-project version pinning.

```bash
# Install pyenv (macOS / Linux)
curl https://pyenv.run | bash

# Add to shell profile (~/.zshrc, ~/.bashrc, or ~/.profile)
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Reload shell
source ~/.zshrc  # or source ~/.bashrc

# Install Python 3.11.9 (pinned version for TechCorp projects)
pyenv install 3.11.9
pyenv global 3.11.9

# Verify
python --version
# Expected: Python 3.11.9
```

#### 3.1.2 Dependency Management with Poetry

TechCorp uses **Poetry 1.8.x** for dependency management and virtual environment isolation. Do not use `pip install` at the global level for project dependencies.

```bash
# Install Poetry via the official installer (do NOT use pip)
curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"

# Configure Poetry to create virtualenvs inside the project directory
poetry config virtualenvs.in-project true

# Verify
poetry --version
# Expected: Poetry (version 1.8.x)
```

#### 3.1.3 Project Dependency Installation

```bash
cd platform/backend

# Install all dependencies (including dev and test groups)
poetry install --with dev,test

# Activate the virtual environment
poetry shell

# Confirm the environment is isolated
which python
# Expected: .../platform/backend/.venv/bin/python

# List installed packages and verify key ones
pip list | grep -E "flask|sqlalchemy|pytest|pydantic"
```

#### 3.1.4 Pre-commit Hooks (Mandatory)

All Python repositories enforce code quality via **pre-commit** hooks. These run automatically on every `git commit` and will block commits that fail linting or type checks.

```bash
# Install pre-commit
pip install pre-commit

# Install the hooks defined in .pre-commit-config.yaml
pre-commit install

# Run manually on all files to verify the baseline passes
pre-commit run --all-files
```

The standard hook stack at TechCorp includes:

| Hook | Purpose |
|---|---|
| `ruff` | Linting and import sorting |
| `black` | Code formatting (line length: 100) |
| `mypy` | Static type checking |
| `bandit` | Security vulnerability scanning |
| `detect-secrets` | Prevents committing secrets and API keys |

A commit that introduces a `bandit` HIGH severity finding or a `detect-secrets` hit will be blocked and must be remediated before the commit is accepted. There are no bypass flags available for these hooks.

#### 3.1.5 Running the Test Suite

```bash
# Run unit tests with coverage
poetry run pytest tests/unit/ --cov=app --cov-report=term-missing -v

# Run integration tests (requires Docker stack to be running)
poetry run pytest tests/integration/ -v --timeout=60

# Run full suite with HTML coverage report
poetry run pytest --cov=app --cov-report=html tests/
open htmlcov/index.html
```

Coverage thresholds enforced in CI:

| Test Type | Minimum Coverage |
|---|---|
| Unit tests | 85% |
| Integration tests | 70% |
| Combined | 80% |

Pull requests that drop overall coverage below 80% will fail the CI pipeline and cannot be merged.

---

### 3.2 Java Development Environment

TechCorp's platform services, data pipeline components, and internal SDKs are built on **Java 21 (LTS)**. This section is required for all backend engineers working on JVM services.

#### 3.2.1 Java Version Management with SDKMAN

Do **not** use a system-installed JDK. Use **SDKMAN** for JDK version management, mirroring the same principle as pyenv for Python.

```bash
# Install SDKMAN
curl -s "https://get.sdkman.io" | bash

# Reload shell
source "$HOME/.sdkman/bin/sdkman-init.sh"

# List available JDK distributions
sdk list java

# Install Eclipse Temurin 21 (TechCorp's approved distribution)
sdk install java 21.0.3-tem

# Set as default
sdk default java 21.0.3-tem

# Verify
java -version
# Expected: openjdk version "21.0.3" ...
javac -version
# Expected: javac 21.0.3
```

TechCorp uses **Eclipse Temurin (Adoptium)** as the approved JDK distribution. Oracle JDK is not approved for use due to licensing restrictions. Amazon Corretto is an acceptable alternative for services deployed on AWS Lambda.

#### 3.2.2 Build Tooling — Gradle

TechCorp Java services use **Gradle 8.x** with the Gradle Wrapper. Never install Gradle globally; always use the wrapper included in each repository.

```bash
cd platform/java-services

# Use the Gradle wrapper to build
./gradlew build

# Run tests
./gradlew test

# Generate test coverage report (JaCoCo)
./gradlew jacocoTestReport
open build/reports/jacoco/test/html/index.html

# Run a single test class
./gradlew test --tests "com.techcorp.platform.UserServiceTest"

# Clean and rebuild
./gradlew clean build
```

#### 3.2.3 Gradle Configuration for Internal Artifact Registry

TechCorp publishes internal libraries to an **Artifactory** instance at `artifacts.techcorp.io`. Configure your Gradle credentials to pull from this registry:

```bash
# Add credentials to your global Gradle properties (NOT to the repository build.gradle)
mkdir -p ~/.gradle
cat >> ~/.gradle/gradle.properties << 'EOF'
techcorpArtifactoryUser=yourname@techcorp.io
techcorpArtifactoryPassword=<API_KEY_FROM_1PASSWORD_ENGINEERING_SHARED_VAULT>
EOF

# Verify Gradle can resolve internal dependencies
./gradlew dependencies --configuration runtimeClasspath 2>&1 | grep "techcorp"
```

The Artifactory API key is generated at `artifacts.techcorp.io/ui/user_profile`. Store it in 1Password immediately. Never commit it to any repository.

#### 3.2.4 JVM Tuning for Local Development

Local development JVM settings are configured in `gradle.properties` within each repository. The standard configuration is:

```properties
# gradle.properties (already present in repos — do not modify without team discussion)
org.gradle.jvmargs=-Xmx4g -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configureondemand=true
```

If your local build OOMs (exit code 137), increase `-Xmx` in your local `~/.gradle/gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx8g -XX:+UseG1GC
```

#### 3.2.5 IntelliJ IDEA Configuration

TechCorp provides **IntelliJ IDEA Ultimate** licenses for all engineers working on JVM services. Retrieve your license key from 1Password under `Engineering Shared > JetBrains License`.

Required plugins (install via `Settings > Plugins`):

| Plugin | Purpose |
|---|---|
| **SonarLint** | Real-time code quality analysis (connect to `sonar.techcorp.io`) |
| **CheckStyle-IDEA** | Enforces TechCorp Java style guide |
| **Lombok** | Annotation processor support |
| **MapStruct Support** | DTO mapper code generation |
| **Docker** | Container management in IDE |
| **Database Tools** | Internal PostgreSQL and Redis connections |

Code style XML is located at `platform/java-services/.idea/codeStyleSettings.xml`. Import it via `Settings > Editor > Code Style > Import Scheme`.

---

## Section 4 — DevOps & Infrastructure

### 4.1 Jenkins CI/CD Pipeline Authentication

TechCorp's CI/CD infrastructure is built on **Jenkins** hosted at `jenkins.techcorp.io`. All code merged to `main` branches triggers automated build, test, security scan, and deployment pipelines.

#### 4.1.1 Generating a Jenkins API Token

You must generate a personal API token to authenticate CLI interactions with Jenkins. Web UI access uses SSO.

1. Navigate to `https://jenkins.techcorp.io` — you will be redirected to Okta for SSO login.
2. Click your username in the top-right corner → **Configure**.
3. Under **API Token**, click **Add new Token**.
4. Name it `local-cli-<your-name>` and click **Generate**.
5. Copy the token immediately — it will not be shown again.
6. Store it in 1Password under `Engineering Shared > Jenkins Tokens`.

#### 4.1.2 Installing and Configuring the Jenkins CLI

```bash
# Download the Jenkins CLI jar
curl -o ~/bin/jenkins-cli.jar \
  https://jenkins.techcorp.io/jnlpJars/jenkins-cli.jar

# Set environment variables (add to your shell profile)
export JENKINS_URL=https://jenkins.techcorp.io
export JENKINS_USER=yourname@techcorp.io
export JENKINS_TOKEN=<YOUR_API_TOKEN_FROM_1PASSWORD>

# Verify authentication
java -jar ~/bin/jenkins-cli.jar who-am-i
# Expected: Authenticated as: yourname@techcorp.io
```

#### 4.1.3 Triggering and Monitoring Pipeline Builds

```bash
# List all jobs in your team's folder
java -jar ~/bin/jenkins-cli.jar list-jobs platform-team

# Trigger a parameterized build
java -jar ~/bin/jenkins-cli.jar build platform-team/backend-api \
  -p BRANCH=feature/my-feature \
  -p DEPLOY_ENV=staging \
  -s  # -s waits for completion and exits with the build's exit code

# Stream console output in real time
java -jar ~/bin/jenkins-cli.jar console platform-team/backend-api -f

# Get the last build result
java -jar ~/bin/jenkins-cli.jar get-job platform-team/backend-api | \
  python3 -c "import sys,xml.etree.ElementTree as ET; \
  root=ET.parse(sys.stdin); print(root.find('.//lastBuild').text)"
```

#### 4.1.4 Understanding the Standard Pipeline Stages

Every TechCorp pipeline runs the following stages in order. A failure at any stage halts the pipeline and posts a notification to the team's Slack channel.

| Stage | Tooling | Failure Action |
|---|---|---|
| **Checkout** | Git | Hard stop |
| **Dependency Audit** | `pip-audit` / OWASP Dependency-Check | Hard stop if CVSS ≥ 7.0 |
| **Unit Tests** | pytest / JUnit | Hard stop |
| **Static Analysis** | Ruff, Mypy, SonarQube | Hard stop on blocker issues |
| **Container Build** | Docker BuildKit | Hard stop |
| **Image Scan** | Trivy | Hard stop if CRITICAL CVE found |
| **Integration Tests** | pytest / Testcontainers | Hard stop |
| **Deploy to Staging** | Helm / Kubernetes | Hard stop |
| **Smoke Tests** | Custom test suite | Hard stop |
| **Deploy to Production** | Helm / Kubernetes | Requires manual approval gate |

To manually approve a production deployment from the CLI:

```bash
java -jar ~/bin/jenkins-cli.jar input platform-team/backend-api \
  --id "prod-deploy-approval" \
  --message "Approve production deployment" \
  -p APPROVER=$JENKINS_USER
```

---

### 4.2 Internal Docker Registry

TechCorp hosts a private Docker registry at `registry.techcorp.io` using **Harbor**. All container images used in production must be sourced from this registry. Never use unvetted images from Docker Hub in production workloads.

#### 4.2.1 Authenticating to the Registry

```bash
# Log in using your TechCorp credentials
docker login registry.techcorp.io \
  --username yourname@techcorp.io \
  --password-stdin <<< "<HARBOR_CLI_SECRET_FROM_1PASSWORD>"

# Verify authentication was successful
cat ~/.docker/config.json | python3 -m json.tool | grep "registry.techcorp.io"
# Expected: "registry.techcorp.io": { "auth": "..." }
```

The Harbor CLI secret is different from your SSO password. Generate it at `registry.techcorp.io/harbor/users/profile` under **CLI Secret**.

#### 4.2.2 Pulling and Pushing Images

```bash
# Pull the base Python image (always use digests in production, tags in development)
docker pull registry.techcorp.io/base-images/python:3.11-slim

# Pull by digest for reproducible builds (required in Jenkinsfiles)
docker pull registry.techcorp.io/base-images/python@sha256:a3f2c1...

# Tag a locally built image and push to the project namespace
docker tag my-service:local registry.techcorp.io/platform/my-service:1.4.2
docker push registry.techcorp.io/platform/my-service:1.4.2

# Also tag and push as latest (for staging only; never tag as latest in prod)
docker tag my-service:local registry.techcorp.io/platform/my-service:latest
docker push registry.techcorp.io/platform/my-service:latest
```

#### 4.2.3 Image Naming Conventions

| Environment | Tag Format | Example |
|---|---|---|
| Development | `dev-<branch-slug>-<short-sha>` | `dev-feat-auth-a3f2c1d` |
| Staging | `staging-<YYYY-MM-DD>-<short-sha>` | `staging-2026-05-29-a3f2c1d` |
| Production | Semantic version `X.Y.Z` | `1.4.2` |
| Hotfix | `hotfix-X.Y.Z` | `hotfix-1.4.3` |

Tags that do not match the expected pattern for their environment will be rejected by the Harbor policy engine. Pushes to the `base-images` namespace are restricted to the Platform team.

#### 4.2.4 Scanning Images Before Pushing

All images must pass a Trivy scan before being pushed to the registry. The CI pipeline enforces this, but you must also verify locally before opening a pull request:

```bash
# Install Trivy
# macOS
brew install trivy
# Ubuntu
sudo apt install -y wget && wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb generic main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt update && sudo apt install -y trivy

# Scan a locally built image
trivy image --severity HIGH,CRITICAL --exit-code 1 registry.techcorp.io/platform/my-service:1.4.2

# Generate a JSON report for the Security team
trivy image --format json --output trivy-report.json registry.techcorp.io/platform/my-service:1.4.2
```

An exit code of `1` means CRITICAL or HIGH vulnerabilities were found. Do not push the image until they are resolved. Contact the Security team at `security@techcorp.io` if a vulnerability has no available fix and blocking is required.

---

### 4.3 Docker Daemon Resource Limits

By default, Docker Desktop and the Docker daemon may consume unbounded system resources. To prevent build processes from starving other workloads, enforce the following limits on your local machine.

#### 4.3.1 Docker Desktop (macOS / Windows)

In Docker Desktop, navigate to **Settings > Resources** and apply:

| Resource | Limit |
|---|---|
| CPUs | 50% of total cores (e.g., 6 of 12) |
| Memory | 8 GB (or 50% of RAM if < 16 GB) |
| Swap | 2 GB |
| Disk image size | 60 GB |

#### 4.3.2 Linux Daemon Configuration

On Linux, configure the Docker daemon resource defaults in `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "default-shm-size": "128m",
  "storage-driver": "overlay2",
  "insecure-registries": [],
  "registry-mirrors": ["https://registry-mirror.techcorp.io"],
  "dns": ["10.2.0.1", "8.8.8.8"],
  "live-restore": true
}
```

Apply per-container resource limits at runtime for local development:

```bash
# Run a container with CPU and memory limits
docker run -d \
  --name my-service \
  --cpus="2.0" \
  --memory="2g" \
  --memory-swap="2g" \
  --restart=on-failure:3 \
  registry.techcorp.io/platform/my-service:1.4.2

# Inspect resource usage in real time
docker stats my-service
```

#### 4.3.3 Docker Compose Resource Constraints

For local development stacks managed by `docker compose`, add `deploy.resources` limits to prevent a single service from consuming all available memory:

```yaml
# docker-compose.override.yml (local overrides only — do not commit to main)
services:
  postgres:
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1G
  redis:
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M
  backend:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
```

---

## Section 5 — Network Security & Compliance

### 5.1 Network Security Policy Overview

TechCorp operates under **SOC 2 Type II** and **ISO 27001** compliance frameworks. All engineers are responsible for ensuring that services they build and deploy adhere to these standards. The following section covers the network-layer validation steps required before any service is promoted to the staging or production environment.

Violations of network security policies are treated as security incidents and are subject to the incident response process, regardless of intent.

### 5.2 Validating Port Bindings Before Staging Promotion

Before opening a pull request that changes any service's exposed ports or network configuration, you must validate port bindings locally and document the results in the PR description.

#### 5.2.1 Listing Active Port Bindings with `ss` and `ip`

```bash
# List all listening TCP and UDP ports with process names
sudo ss -tulnp

# Example expected output for a standard backend service:
# Netid  State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port  Process
# tcp    LISTEN 0       128     0.0.0.0:5001        0.0.0.0:*          users:(("flask",pid=12345,fd=5))
# tcp    LISTEN 0       128     127.0.0.1:5432      0.0.0.0:*          users:(("postgres",pid=6789,fd=10))

# Confirm your network interfaces and IP assignments
ip addr show
ip -4 addr show   # IPv4 only

# Check routing table (important for services that bridge Docker networks)
ip route show
```

**Critical check**: Verify that database ports (5432 for PostgreSQL, 6379 for Redis) are bound to `127.0.0.1` or a Docker internal network address — never to `0.0.0.0`. An unintentionally world-accessible database port is a P1 security incident.

#### 5.2.2 Port Scanning with nmap for Pre-Staging Validation

Before pushing a service to staging, run a local `nmap` scan to produce a machine-readable port exposure report. Attach this report to your pull request or staging deployment ticket.

```bash
# Install nmap
sudo apt install -y nmap    # Ubuntu
brew install nmap           # macOS

# Scan all ports on localhost to identify what your service is exposing
sudo nmap -sS -sV -p- --open 127.0.0.1 -oN nmap-local-baseline.txt

# Scan the Docker bridge network to confirm no unexpected services are accessible
# First, identify your Docker bridge subnet
docker network inspect bridge | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data[0]['IPAM']['Config'][0]['Subnet'])
"
# Then scan it (replace 172.17.0.0/24 with your actual bridge subnet)
sudo nmap -sn 172.17.0.0/24

# Targeted scan to confirm a specific port is (or is not) listening
nmap -p 5432,6379,9200,27017 127.0.0.1
```

**Acceptable open ports on a developer workstation** (everything else must be closed or firewalled):

| Port | Service | Acceptable Bind Address |
|---|---|---|
| 5001 | Flask dev server | `127.0.0.1` |
| 5432 | PostgreSQL | `127.0.0.1` |
| 6379 | Redis | `127.0.0.1` |
| 9000 | MinIO API | `127.0.0.1` |
| 9090 | Prometheus (if enabled) | `127.0.0.1` |
| 8080 | Generic HTTP proxy | `127.0.0.1` |

Report any port other than the above to `security@techcorp.io` before proceeding.

#### 5.2.3 Verifying TLS Certificate Validity

All internal services must communicate over TLS. Verify certificate validity before deploying to staging:

```bash
# Check TLS certificate details and expiry
echo | openssl s_client -connect internal.techcorp.io:443 -servername internal.techcorp.io 2>/dev/null \
  | openssl x509 -noout -dates -subject -issuer

# Check if a cert is expiring within 30 days (exit code 1 = expiring)
echo | openssl s_client -connect internal.techcorp.io:443 2>/dev/null \
  | openssl x509 -noout -checkend 2592000 \
  || echo "WARNING: Certificate expires within 30 days"

# Validate the full certificate chain
curl --cacert /etc/ssl/certs/ca-certificates.crt \
  -v https://internal.techcorp.io/health 2>&1 | grep -E "SSL|TLS|certificate"
```

### 5.3 Firewall Rules and Service Mesh Policy

TechCorp's production and staging Kubernetes clusters enforce **Cilium NetworkPolicy** objects. The network policies are maintained in `platform/infra/network-policies/`. Engineers must review the relevant NetworkPolicy before deploying a new service to ensure it will be reachable by its intended consumers and isolated from everything else.

```bash
# View active NetworkPolicies in the staging namespace (requires kubectl access)
kubectl get networkpolicy -n staging -o yaml

# Test whether pod-to-pod communication is permitted by the policy
# (run from within the cluster using a debug pod)
kubectl run -it --rm --restart=Never debug-pod \
  --image=registry.techcorp.io/base-images/network-debug:latest \
  --namespace=staging \
  -- curl http://my-service.staging.svc.cluster.local:5001/health
```

---

## Section 6 — Encrypted Traffic & LLM Security

### 6.1 TLS/HTTPS Enforcement Policy

All application-layer traffic at TechCorp — without exception — must be encrypted in transit using TLS 1.2 or higher. TLS 1.0 and 1.1 are disabled at the load balancer layer and will result in a connection reset.

| Minimum TLS Version | TLS 1.2 |
|---|---|
| Approved Cipher Suites | TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256, ECDHE-RSA-AES256-GCM-SHA384 |
| Deprecated (blocked) | RC4, 3DES, MD5-based suites, TLS 1.0, TLS 1.1, SSLv3 |
| Certificate Authority | TechCorp Internal CA (for internal services) + Let's Encrypt (for public endpoints) |

For services that handle sensitive data (authentication tokens, PII, payment data), **mutual TLS (mTLS)** is required. The service mesh (Istio) handles mTLS transparently between registered services; however, you must ensure your service's Kubernetes `Service` resource is correctly labeled for the mesh to apply policy.

### 6.2 Application-Layer Content Inspection Policy

TechCorp operates a **Deep Packet Inspection (DPI)** proxy on all corporate network egress paths. This is a legal requirement under our enterprise security compliance agreements and all employees are informed of it during onboarding.

**What is inspected:**

- HTTP/HTTPS traffic originating from company-managed devices on the corporate network and VPN is subject to TLS inspection via a trusted root certificate pushed to all managed devices.
- Inspection is limited to metadata and headers for personal browsing traffic. Full content inspection applies to traffic destined for cloud services (AWS, GCP, Azure, SaaS tools) from company devices.
- Traffic is **never logged for surveillance purposes**. Inspection is automated and used exclusively for threat detection, DLP (Data Loss Prevention), and malware blocking.

**Developer implications:**

- When making API calls from your local machine over the VPN, responses may include an `X-TechCorp-Inspection: active` header. This is expected and indicates the proxy is functioning.
- If your application performs certificate pinning (e.g., in a mobile app or IoT device), you must explicitly whitelist the TechCorp inspection proxy certificate. The proxy CA certificate is at `software.techcorp.io/certs/techcorp-proxy-ca.crt`.
- Services that need to bypass inspection for a justified reason (e.g., E2E encrypted backup agents) must submit a firewall exception request via ServiceNow with Security team approval.

### 6.3 WebSocket Security for Internal AI Tools

TechCorp's internal AI platform (`ai-platform.techcorp.io`) and several product features use persistent **WebSocket** connections to stream LLM responses to clients. WebSocket connections present a distinct threat surface that HTTP request/response APIs do not. Engineers building features on top of the AI platform must adhere to the following security requirements.

#### 6.3.1 Authentication on WebSocket Upgrade

HTTP cookies and the `Authorization` header are not reliably propagated across WebSocket upgrades in all frameworks. The approved pattern at TechCorp is to pass a short-lived **JWT bearer token** as a query parameter on the initial upgrade request, validated immediately by the server.

```python
# Client-side (JavaScript) — approved pattern
const token = await getShortLivedJWT();  // 60-second TTL
const ws = new WebSocket(`wss://ai-platform.techcorp.io/ws/stream?token=${token}`);

# Server-side (Python / Flask-SocketIO) — mandatory token validation
from flask_socketio import SocketIO, disconnect
import jwt

@socketio.on('connect')
def handle_connect(auth):
    token = request.args.get('token')
    if not token:
        disconnect()
        return False
    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
        # Validate audience, issuer, and expiry
        assert payload['aud'] == 'ai-platform'
        assert payload['iss'] == 'https://idp.techcorp.io'
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, AssertionError):
        disconnect()
        return False
```

JWT tokens for WebSocket use are issued with a **60-second TTL** and a single-use nonce. A token cannot be reused after the initial WebSocket upgrade, even if the connection is still alive.

#### 6.3.2 Message Payload Validation

Every message received over a WebSocket connection must be validated before processing, regardless of the authenticated state of the connection. Treat WebSocket messages with the same skepticism as HTTP request bodies.

```python
from pydantic import BaseModel, validator, Field
import bleach

class LLMPromptMessage(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8192)
    session_id: str = Field(..., pattern=r'^[a-f0-9\-]{36}$')  # UUID only
    stream: bool = True

    @validator('prompt')
    def sanitize_prompt(cls, v):
        # Strip HTML/script tags from user-supplied prompts
        return bleach.clean(v, tags=[], strip=True)

@socketio.on('message')
def handle_message(data):
    try:
        msg = LLMPromptMessage(**data)
    except ValidationError as e:
        emit('error', {'code': 'INVALID_PAYLOAD', 'detail': str(e)})
        return
    # Proceed with validated msg
```

#### 6.3.3 Prompt Injection and LLM-Specific Vulnerabilities

When building features on top of TechCorp's internal LLM APIs, engineers must be aware of the following LLM-specific attack vectors:

**Prompt Injection**: A user-supplied input that attempts to override the system prompt or extract confidential context. Mitigations:

- Always pass user content in the `user` role, never interpolated into the `system` prompt string.
- Use parameterized message structures rather than f-string prompt construction.
- Validate that model responses do not contain canary strings that would indicate system prompt leakage (the AI platform's gateway performs this check automatically, but defensive coding is still required).

**Indirect Prompt Injection via Retrieved Content**: If your feature uses RAG (Retrieval-Augmented Generation) and passes externally retrieved documents to the model, those documents can contain injected instructions. Mitigations:

- Wrap retrieved content in a structured delimiter: `<retrieved_document>...</retrieved_document>`.
- Instruct the model in the system prompt to treat content within those delimiters as untrusted data, not instructions.
- Log all retrieved chunks that are passed to the model for auditability.

**Model Output Rendering (XSS via LLM)**: If model output is rendered as HTML in a frontend, it can contain injected scripts. Mitigations:

- Always sanitize LLM output before rendering. Use `DOMPurify` on the frontend.
- Set `Content-Security-Policy` headers that prohibit inline script execution.
- Never use `innerHTML` or `dangerouslySetInnerHTML` with unsanitized model output.

#### 6.3.4 WebSocket Connection Lifecycle Management

```python
# Enforce maximum message rate (100 messages per minute per session)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(app, key_func=get_remote_address)

@socketio.on('message')
@limiter.limit("100/minute")
def handle_message(data):
    ...

# Enforce maximum session duration (30 minutes)
import time

SESSION_MAX_DURATION = 1800  # 30 minutes

@socketio.on('connect')
def handle_connect(auth):
    session['connected_at'] = time.time()

@socketio.on('message')
def handle_message(data):
    if time.time() - session.get('connected_at', 0) > SESSION_MAX_DURATION:
        emit('error', {'code': 'SESSION_EXPIRED'})
        disconnect()
        return
```

---

## Section 7 — Local Development Environment Quick-Start

### 7.1 Cloning Repositories

```bash
# Configure SSH key for GitHub access
ssh-keygen -t ed25519 -C "yourname@techcorp.io" -f ~/.ssh/id_techcorp_github
ssh-add ~/.ssh/id_techcorp_github
# Add the public key to your GitHub profile at github.com/settings/keys
cat ~/.ssh/id_techcorp_github.pub

# Clone the main platform repository
git clone git@github.com:techcorp/platform.git
cd platform

# Install git-secrets to prevent accidental credential commits
git secrets --install
git secrets --register-aws
```

### 7.2 Environment Variables

```bash
cp .env.example .env
```

Secret values are stored in **1Password** under `Engineering Shared`. The full variable reference is documented in `docs/env-reference.md`. Required variables for local development:

| Variable | Source | Notes |
|---|---|---|
| `DATABASE_URL` | 1Password | Points to local Docker postgres by default |
| `REDIS_URL` | 1Password | Points to local Docker redis by default |
| `TECHCORP_LLM_API_KEY` | 1Password | Required for AI feature development |
| `AWS_ACCESS_KEY_ID` | 1Password | Read-only; for dev S3 bucket only |
| `AWS_SECRET_ACCESS_KEY` | 1Password | Read-only; for dev S3 bucket only |
| `SENTRY_DSN` | `platform/README.md` | Set to `""` to disable locally |

### 7.3 Starting the Full Development Stack

```bash
# Start background services (PostgreSQL, Redis, MinIO, Mailhog)
docker compose up -d

# Run database migrations
poetry run flask db upgrade

# Seed local database with development data
poetry run flask seed-db --env development

# Start the Flask development server
poetry run flask run --port 5001 --debug

# In a separate terminal — start the frontend Vite dev server
cd platform/frontend
npm install
npm run dev
```

Services accessible after startup:

| Service | URL |
|---|---|
| Backend API | `http://localhost:5001` |
| Frontend | `http://localhost:5173` |
| MinIO Console | `http://localhost:9001` |
| Mailhog (email testing) | `http://localhost:8025` |
| Prometheus (metrics) | `http://localhost:9090` |

---

## Section 8 — Password Security & Credential Management

### 8.1 Password Requirements

All TechCorp accounts must comply with this password policy. Enforcement is automated via Okta and service account management tooling.

| Policy | Requirement |
|---|---|
| Minimum length | 14 characters |
| Complexity | 1+ uppercase, 1+ lowercase, 1+ digit, 1+ special character |
| Password reuse | Last 12 passwords prohibited |
| Expiration | 90 days (reminder at 14 days) |
| Account lockout | 10 failed attempts → 30-minute lockout |

### 8.2 1Password Usage

All engineers receive a **1Password Teams** license. Usage is mandatory.

1. Accept the invite from `no-reply@1password.com` sent to your TechCorp email on day 1.
2. Enable biometric unlock on your workstation and mobile device.
3. All work credentials must reside exclusively in 1Password. Do not store credentials in `~/.bashrc`, `.env` files committed to git, Slack messages, Notion, or any other plaintext surface.
4. Use **1Password CLI** (`op`) for injecting secrets into shell sessions:

```bash
# Install 1Password CLI
brew install 1password-cli    # macOS
# or download from software.techcorp.io for Linux

# Sign in
op signin

# Inject secrets into a command without writing them to disk
op run --env-file=".env.op" -- poetry run flask run
```

The `.env.op` file uses `op://` URIs instead of plaintext values:

```dotenv
DATABASE_URL=op://Engineering Shared/PostgreSQL Dev/connection-string
TECHCORP_LLM_API_KEY=op://Engineering Shared/LLM API Keys/techcorp-dev
```

### 8.3 Multi-Factor Authentication

MFA is mandatory for every TechCorp account without exception.

- **Primary**: Duo Security push notification
- **Backup**: TOTP (Duo mobile app)
- **Privileged access** (production systems, admin consoles): Hardware FIDO2 token (YubiKey 5 NFC issued on request)

Lost MFA device: contact `security@techcorp.io` immediately. The Security team will revoke all active sessions and issue a re-enrollment link. This process takes approximately 2 hours and cannot be expedited.

---

## Section 9 — Troubleshooting Matrix

### Common Errors and Resolutions

| Error | Observed Symptom | Likely Cause | Resolution Steps |
|---|---|---|---|
| **VPN: Auth loop** | Browser redirects to Okta repeatedly after login | Stale Tailscale session token | Run `sudo tailscale logout && sudo tailscale up --login-server=https://vpn-idp.techcorp.io` |
| **VPN: IP conflict** | `tailscale: route conflict detected` in daemon log | Another VPN or local subnet using 100.x.x.x range | Disable conflicting VPN, check `ip route show` for overlapping routes, restart Tailscale |
| **VPN: No DNS resolution** | `dig internal.techcorp.io` returns NXDOMAIN | Tailscale MagicDNS not active | Run `tailscale status`, verify `MagicDNS: enabled`. If not, re-authenticate. |
| **Docker: Container OOMKilled** | `docker ps` shows container with status `OOMKilled` / exit code 137 | Container exceeded memory limit | Increase memory limit in `docker-compose.override.yml`, check application for memory leaks with `docker stats` |
| **Docker: Port already in use** | `Error: bind: address already in use` on `docker compose up` | Stale container or host process using the port | Run `sudo ss -tulnp | grep <PORT>` to identify the PID, then `docker rm -f <container>` or `kill <PID>` |
| **Docker: Registry auth failure** | `401 Unauthorized` when pulling from `registry.techcorp.io` | Expired Harbor CLI secret | Re-generate CLI secret at `registry.techcorp.io/harbor/users/profile`, re-run `docker login` |
| **Docker: Image layer cache miss** | Builds take 10+ minutes on every run | BuildKit cache not mounted | Add `--build-arg BUILDKIT_INLINE_CACHE=1` and configure cache mounts in `docker buildx bake` |
| **Jenkins: Pipeline stuck at approval** | Build shows `Waiting for user input` indefinitely | No one with approval rights is watching the build | Use Jenkins CLI `input` command or visit the build URL and click **Approve** |
| **Jenkins: Pipeline fails at image scan** | `CRITICAL: CVE-XXXX-XXXX found in layer` | Base image contains a known CVE | Update base image to the latest patched version in `registry.techcorp.io/base-images`. If no patch exists, file a security exception ticket. |
| **Jenkins: `git checkout` failure** | `Error: authentication failed for 'https://github.com/techcorp'` | Jenkins credential for GitHub has expired | Notify `#platform-sre` in Slack — only the Jenkins admin can rotate the GitHub App credential |
| **Jenkins: Test stage hangs** | Stage does not complete; no output after 10 min | Deadlock in async test fixture | SSH into the Jenkins agent: `java -jar jenkins-cli.jar offline-node <agent>`. Check for zombie pytest processes. |
| **Python: `ModuleNotFoundError`** | Module that exists in `pyproject.toml` is not importable | Running Python outside the Poetry virtualenv | Confirm `poetry shell` is active. Run `which python` — should point to `.venv/bin/python`. |
| **Python: `poetry install` fails on M-series Mac** | `ERROR: Failed building wheel for cryptography` | Native extension build failure | Run `brew install openssl` and `export LDFLAGS="-L/opt/homebrew/opt/openssl/lib"` before `poetry install` |
| **Java: Gradle dependency resolution fails** | `Could not resolve com.techcorp:...` | Artifactory credentials not configured or expired | Re-generate Artifactory API key at `artifacts.techcorp.io`, update `~/.gradle/gradle.properties` |
| **Java: `OutOfMemoryError` during build** | Gradle daemon terminates with heap OOM | Default JVM heap too small for the project | Add `org.gradle.jvmargs=-Xmx8g` to `~/.gradle/gradle.properties` |
| **nmap: No output / all ports closed** | `nmap 127.0.0.1` returns no open ports | Services not started, or running on a different bind address | Confirm services are running: `docker compose ps`. Check bind address with `ss -tulnp`. |
| **TLS: Certificate verification failure** | `SSL: CERTIFICATE_VERIFY_FAILED` in Python requests | TechCorp proxy CA not in system trust store | Install proxy CA: `sudo cp techcorp-proxy-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates` |
| **WebSocket: Immediate disconnect on connect** | Client connects then immediately receives `disconnect` event | JWT token expired or malformed | Verify token TTL (60 seconds). Re-request a token immediately before the WebSocket upgrade. |
| **WebSocket: Rate limit exceeded** | Server emits `{'code': 'RATE_LIMITED'}` | Client sending more than 100 messages/minute | Implement client-side backoff. Check for runaway retry loops in event handlers. |
| **pre-commit: `detect-secrets` blocks commit** | `Potential secret found in <file>` | Credential, API key, or token-like string in staged file | Run `detect-secrets scan > .secrets.baseline` to review, then audit each finding. Remove actual secrets and use `op://` URIs. |
| **CrowdStrike: Sensor not reporting** | IT alerts that device is out of compliance | Sensor process stopped or OOM killed | Run `sudo systemctl restart falcon-sensor`. If it fails to start, reinstall via `software.techcorp.io`. |

---

## Section 10 — Contacts & Escalation Paths

| Role | Contact | When to Engage |
|---|---|---|
| IT Help Desk | it-support@techcorp.io / `#it-help` | Workstation setup, software access, hardware issues |
| Security Team | security@techcorp.io / `#security-incidents` | Suspected compromise, firewall exceptions, CVE triage |
| Platform SRE | `#platform-sre` on Slack | Jenkins failures, Kubernetes issues, registry problems |
| Onboarding Buddy | Assigned on Day 1 | General orientation, team introductions, cultural questions |
| Engineering Manager | Your direct manager | Access escalations, role-specific tooling, project context |

For urgent security incidents (active compromise, data exposure, production breach), page the on-call security engineer directly via **PagerDuty** at `pd.techcorp.io`. Do not wait for email responses.
