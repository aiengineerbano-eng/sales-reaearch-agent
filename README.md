# Northstar Sales Agent

An AI-powered sales research and proposal generation tool built for Northstar marketing team. Given a contact name and company, it automatically researches the prospect, maps cloud opportunities, drafts personalised 3 outreach emails, and generates a client-ready Statement of Work if required — all in one flow.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Local Development](#local-development)
- [Environment Variables & Credentials](#environment-variables--credentials)
- [AWS Deployment](#aws-deployment)
- [Authentication (Okta SSO)](#authentication-okta-sso)
- [Adding New Users](#adding-new-users)
- [Rotating API Keys](#rotating-api-keys)
- [Common Issues & Troubleshooting](#common-issues--troubleshooting)
- [Key Design Decisions](#key-design-decisions)

---

## Architecture Overview

```
Browser
  │
  ├── CloudFront (frontend) ──► S3 (React/Vite SPA)
  │
  └── CloudFront (API) ──► ALB ──► ECS Fargate (API container)
                                         │
                                    ECS Fargate (Worker container)
                                         │
                                    EFS (SQLite database)
                                         │
                              External APIs (Anthropic, Serper, Proxycurl, Hunter, Wappalyzer, Brave)
```

**Auth flow:**
```
Browser → Cognito Hosted UI → Okta SSO → Azure AD → back to app
```

**Research flow:**
```
POST /research → Worker picks up job → SalesResearchFlow runs:
  1. initialize            (validates input, sets status — entry point)
  2. research_contact      ─┐
  3. research_company      │  all four listen to `initialize` directly
  4. analyse_job_postings  │  and run in parallel — none depends on
  5. gather_news           ─┘  another's output
→ Once all four finish, a worker (outside the Flow class) calls:
  6. run_map_opportunities
  7. run_draft_emails
→ Results stored in SQLite on EFS
→ Frontend polls GET /research/{job_id} every 3s
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, TypeScript |
| Backend | FastAPI (Python 3.12), async SQLite via aiosqlite |
| AI/Agents | CrewAI, Claude Sonnet 4.5 (Anthropic) |
| Database | SQLite on EFS (persistent across ECS restarts) |
| Infrastructure | AWS CDK (TypeScript), ECS Fargate, CloudFront, ALB, EFS, Cognito, SSM |
| Auth | AWS Cognito + Okta OIDC + Azure AD |
| Search | Serper (Google Search API), Brave Search |
| Email Finding | Hunter.io (optional) |
| Contact Enrichment | Proxycurl |
| Tech Stack Detection | Wappalyzer |

---

## Project Structure

```
northstar-sales-agent/
├── agent/
│   ├── flows/
│   │   └── sales_research_flow.py   # SalesResearchFlow — orchestrates everything
│   ├── crews/                       # CrewAI crew definitions
│   │   ├── contact_research_crew.py
│   │   ├── company_intel_crew.py
│   │   ├── job_posting_crew.py
│   │   ├── news_context_crew.py
│   │   ├── opportunity_mapper_crew.py
│   │   └── email_copy_crew.py
│   ├── models/
│   │   └── state.py                 # Pydantic models (SalesResearchState etc.)
│   ├── prompts/
│   │   └── company_context.py       # Business positioning context for prompts
│   └── tools/
│       ├── serper_tool.py           # rate-limited via semaphore — 3 crews share this
│       ├── brave_tool.py
│       ├── hunter_tool.py
│       ├── proxycurl_tool.py
│       ├── scrape_tool.py
│       └── wappalyzer_tool.py
├── api/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py                # Settings via pydantic-settings, reads .env
│   ├── worker.py               # Background job processor
│   ├── routes/
│   │   ├── health.py
│   │   └── research.py         # All research API endpoints
│   └── db/
│       ├── models.py
│       └── queries.py          # SQLite queries
├── ui/
│   ├── src/
│   │   ├── auth.ts             # Cognito/Okta auth utilities
│   │   ├── AuthGuard.tsx       # Route protection component
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   └── NewResearch.tsx
│   │   ├── components/
│   │   │   └── ExpandableCard.tsx
│   │   └── hooks/
│   │       ├── useApi.ts           # API client
│   │       └── useResearch.ts
│   └── .env                    # Frontend env vars — NOT committed, see .gitignore
├── infra/
│   └── lib/
│       ├── sales-agent-stack.ts    # Main CDK stack
│       ├── ecs-constructs.ts       # ECS task definitions
│       ├── frontend-constructs.ts  # S3 + CloudFront
│       ├── secrets-constructs.ts   # Secrets Manager reference
│       ├── storage-constructs.ts   # EFS
│       ├── ssm-constructs.ts       # SSM parameters (Okta)
│       └── auth-construct.ts       # Cognito + Okta IdP
└── docker/
    ├── Dockerfile.api
    └── Dockerfile.worker
```

---

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- `uv` (Python package manager)
- AWS CLI configured

### Setup

```bash
# Clone and install Python deps
git clone <repo>
cd northstar-sales-agent
uv sync

# Install Node deps for DOCX generation
cd scripts && npm install docx && cd ..

# Install frontend deps
cd ui && npm install && cd ..

# Install system deps (Mac)
brew install cairo  # required for cairosvg (Gantt PNG rendering)
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
```

### Environment variables

Create `.env` in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SERPER_API_KEY=...
HUNTER_API_KEY=          # optional
PROXYCURL_API_KEY=       # deprecated, leave empty
WAPPALYZER_API_KEY=      # optional
BRAVE_API_KEY=           # optional
```

Create `ui/.env`:

```bash
VITE_API_URL=http://localhost:8000
VITE_COGNITO_DOMAIN=https://northstar-sales-agent.auth.ap-southeast-2.amazoncognito.com
VITE_COGNITO_CLIENT_ID=5lou91au3u0aedsvgt687kkps7
```

### Running locally

Open 3 terminals:

```bash
# Terminal 1 — API
uv run uvicorn api.main:app --reload --port 8000

# Terminal 2 — Worker
uv run python -m api.worker

# Terminal 3 — Frontend
cd ui && npm run dev
```

Open `http://localhost:5173`

> **Note:** Auth is bypassed locally — `AuthGuard.tsx` checks `import.meta.env.DEV` and skips Okta login in development mode.

---

## Environment Variables & Credentials

### AWS Secrets Manager

All backend secrets are stored in:
**Secret name:** `NorthstarSalesAgentAllSecrets1`
**Region:** `ap-southeast-2`

| Key | Description | Required |
|-----|-------------|----------|
| `ANTHROPIC_API_KEY` | Claude API key — get from console.anthropic.com | ✅ |
| `SERPER_API_KEY` | Google Search API — get from serper.dev | ✅ |
| `OKTA_CLIENT_ID` | Okta app client ID | ✅ |
| `OKTA_CLIENT_SECRET` | Okta app client secret | ✅ |
| `HUNTER_API_KEY` | Email finder — hunter.io (optional) | ⬜ |
| `PROXYCURL_API_KEY` | LinkedIn API (deprecated, leave empty) | ⬜ |
| `WAPPALYZER_API_KEY` | Tech stack detection (optional) | ⬜ |
| `BRAVE_API_KEY` | Brave search (optional) | ⬜ |

**To update secrets:**
```bash
aws secretsmanager put-secret-value \
  --region ap-southeast-2 \
  --secret-id NorthstarSalesAgentAllSecrets1 \
  --secret-string '{
    "ANTHROPIC_API_KEY":    "sk-ant-...",
    "SERPER_API_KEY":       "...",
    "OKTA_CLIENT_ID":       "",
    "OKTA_CLIENT_SECRET":   "...",
    "HUNTER_API_KEY":       "",
    "PROXYCURL_API_KEY":    "",
    "WAPPALYZER_API_KEY":   "",
    "BRAVE_API_KEY":        ""
  }'
```

> ⚠️ **Important:** After updating secrets, force ECS to restart (see [Rotating API Keys](#rotating-api-keys)).

### SSM Parameter Store

Okta credentials used at CDK deploy time:

| Parameter | Description |
|-----------|-------------|
| `/northstar/sales-agent/okta-client-id` | Okta app Client ID |
| `/northstar/sales-agent/okta-client-secret` | Okta app Client Secret |

These are passed via `--context` flags at deploy time (see deployment section).

### Frontend Environment Variables

Stored in `ui/.env` — these are **not secret** (they're public-facing IDs):

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://d2v50noot1tuxy.cloudfront.net` |
| `VITE_COGNITO_DOMAIN` | `https://northstar-sales-agent.auth.ap-southeast-2.amazoncognito.com` |
| `VITE_COGNITO_CLIENT_ID` | `5lou91au3u0aedsvgt687kkps7` |

---

## AWS Deployment

### First-time setup

```bash
# 1. Configure AWS credentials
aws configure
# Region: ap-southeast-2

# 2. Verify account
aws sts get-caller-identity

# 3. Bootstrap CDK
cd infra
npm install
npx cdk bootstrap aws://650880817536/ap-southeast-2
```

### Full deploy (backend + infrastructure)

```bash
cd infra
npx cdk deploy \
  --context okta-client-id=0oa25xlcgyqZrIeHO1d8 \
  --context okta-client-secret=YOUR_OKTA_SECRET \
  --outputs-file outputs.json
```

> Takes ~15 mins on first deploy, ~10 mins on subsequent deploys.

### Frontend deploy

```bash
cd ui && npm run build

aws s3 sync dist/ s3://northstar-sales-agent-frontend-650880817536/ --delete

aws cloudfront create-invalidation \
  --distribution-id $(aws cloudfront list-distributions \
    --query "DistributionList.Items[?DomainName=='d2hnjxvw25adze.cloudfront.net'].Id" \
    --output text) \
  --paths "/*"
```

> Wait 2-3 mins after invalidation, then hard refresh (`Cmd+Shift+R`).

### Backend-only deploy (no frontend changes)

```bash
cd infra
npx cdk deploy \
  --context okta-client-id=0oa25xlcgyqZrIeHO1d8 \
  --context okta-client-secret=YOUR_OKTA_SECRET \
  --outputs-file outputs.json
```

### Key outputs after deploy

| Output | Description |
|--------|-------------|
| `ApiUrl` | API CloudFront URL — use as `VITE_API_URL` |
| `FrontendUrl` | Frontend CloudFront URL |
| `AuthCognitoDomain` | Cognito hosted UI domain |
| `AuthUserPoolClientId` | Cognito app client ID — use as `VITE_COGNITO_CLIENT_ID` |
| `SecretsSecretArn` | Secrets Manager ARN |

---

## Authentication (Okta SSO)

### How it works

```
User visits sales-agent.northstar.com
  → AuthGuard shows Login page
  → User clicks "Login with Okta"
  → Redirects to Cognito hosted UI
  → Cognito redirects to Okta
  → Okta authenticates via Azure AD (Northstar Microsoft 365)
  → Okta returns token to Cognito
  → Cognito issues JWT to frontend
  → JWT stored in sessionStorage
  → JWT attached to all API requests
```

### Okta app details

| Field | Value |
|-------|-------|
| App name | Northstar Sales Agent |
| Okta domain | login.northstar.com |
| Client ID | `0oa25xlcgyqZrIeHO1d8` |
| Sign-in redirect URI | `https://northstar-sales-agent.auth.ap-southeast-2.amazoncognito.com/oauth2/idpresponse` |
| Sign-out redirect URI | `https://sales-agent.northstar.com` |
| Access group | `Sales-Agent-Users` |

### Cognito details

| Field | Value |
|-------|-------|
| User Pool ID | `ap-southeast-2_wISFRfpIn` |
| App Client ID | `5lou91au3u0aedsvgt687kkps7` |
| Domain | `northstar-sales-agent.auth.ap-southeast-2.amazoncognito.com` |

---

## Adding New Users

1. Log into **Okta Admin Console** → `login-northstar-admin.okta.com/admin`
2. Go to **Directory → Groups → Sales-Agent-Users**
3. Click **Manage People → Add Members**
4. Search for the user and add them
5. User can now log in immediately — no redeployment needed

---

## Rotating API Keys

### Anthropic API key

1. Go to `console.anthropic.com` → API Keys → create new key → delete old one
2. Update Secrets Manager (see above)
3. Force ECS restart:

```bash
aws ecs update-service \
  --region ap-southeast-2 \
  --cluster northstar-sales-agent \
  --service northstar-sales-agent-api \
  --force-new-deployment

aws ecs update-service \
  --region ap-southeast-2 \
  --cluster northstar-sales-agent \
  --service northstar-sales-agent-worker \
  --force-new-deployment
```

> ⚠️ ECS reads secrets at container startup only. `force-new-deployment` is required after any secret change to pick up new values.

---

## Common Issues & Troubleshooting

### "Could not resolve authentication method" (Anthropic error)
- **Cause:** `ANTHROPIC_API_KEY` is empty or not injected into the ECS container
- **Fix:** Check Secrets Manager has the key, then force ECS restart

### "Other CLIs currently reading from cdk.out"
```bash
rm -rf infra/cdk.out
npx cdk deploy ...
```

### "Address already in use" (port 8000)
```bash
lsof -ti:8000 | xargs kill -9
```

### Jobs stuck in "queued" state
- **Cause:** Worker process isn't running
- **Fix locally:** `uv run python -m api.worker`
- **Fix in AWS:** Check ECS worker service is running, force new deployment if needed

### CORS errors in browser
- **Cause:** API URL mismatch or wrong `allow_origins` in FastAPI
- **Fix:** Check `VITE_API_URL` in `ui/.env` matches the API CloudFront URL exactly

### Secrets overwritten after deploy
- **Cause:** `generateSecretString` in CDK regenerates values
- **Fix:** `secrets-constructs.ts` now uses `Secret.fromSecretNameV2()` — CDK never touches values

### Login redirects to wrong place / 404 on Okta
- **Cause:** Cognito callback URLs not registered
- **Fix:**
```bash
aws cognito-idp update-user-pool-client \
  --region ap-southeast-2 \
  --user-pool-id ap-southeast-2_wISFRfpIn \
  --client-id 5lou91au3u0aedsvgt687kkps7 \
  --supported-identity-providers "Okta" \
  --allowed-o-auth-flows "code" \
  --allowed-o-auth-scopes "openid" "email" "profile" \
  --allowed-o-auth-flows-user-pool-client \
  --callback-urls "https://sales-agent.northstar.com" "http://localhost:5173" \
  --logout-urls "https://sales-agent.northstar.com" "https://sales-agent.northstar.com/?logged_out=true" "http://localhost:5173"
```

---

## Key Design Decisions

**Why SQLite on EFS instead of RDS?**
Low traffic internal tool — SQLite is simpler, cheaper, and zero-maintenance. EFS provides persistence across ECS task restarts.

**Why does `SalesResearchFlow` run four steps in parallel instead of sequentially?**
None of `research_contact`, `research_company`, `analyse_job_postings`, or `gather_news` read another's output — each only needs the original `contact_name`/`company_name`/`website` inputs. The only step that needs everything joined is `run_map_opportunities`. Since three of the four parallel crews (and the news crew) share the Serper API, `serper_tool.py` caps concurrent Serper calls with a semaphore to avoid self-inflicted rate limiting.

**Why Cognito in front of Okta?**
Cognito provides the OAuth2/PKCE flow the SPA needs. Okta is configured as a federated IdP inside Cognito rather than being called directly, which avoids needing a backend OAuth server and keeps the frontend auth flow simple.

**Why CDK context for Okta credentials?**
CloudFormation cannot resolve AWS Secrets Manager values at deploy time (only runtime). SSM SecureString is also not supported by CloudFormation. CDK context (`--context` flags) is the cleanest way to pass secrets at deploy time without committing them to code.

---

## URLs

| Environment | URL |
|-------------|-----|
| Production frontend | https://sales-agent.northstar.com |
| Production API | https://d2v50noot1tuxy.cloudfront.net |
| Local frontend | http://localhost:5173 |
| Local API | http://localhost:8000 |
| Okta Admin | https://login-northstar-admin.okta.com/admin |
| AWS Console | https://ap-southeast-2.console.aws.amazon.com |