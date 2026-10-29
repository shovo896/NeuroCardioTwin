# NeuroCardioTwin

NeuroCardioTwin is a secure, AI-native research-support platform for EEG and
ECG time-series workflows. It combines authenticated signal submission,
server-side numerical validation, purpose-specific local ONNX inference,
evidence-grounded RAG explanations, private history metadata, multilingual
interaction, and emergency-safety guidance.

> **Research-use boundary:** This is a prototype for research support. It is
> not a medical device and must not be used for diagnosis, triage, treatment,
> or emergency decision-making.

## Live project links

| Resource | URL | Access |
| --- | --- | --- |
| Web workspace | `https://neurocardiotwin.vercel.app` | Auth0 sign-in required |
| Public technical brief | `https://neurocardiotwin.vercel.app/docs` | Public, no private data |
| Public capability status | `https://neurocardiotwin.vercel.app/api/docs/status` | Public, non-sensitive |
| MCP capability status | `https://neurocardiotwin.vercel.app/mcp/status` | Public, non-sensitive |
| MCP protected-resource metadata | `https://neurocardiotwin.vercel.app/.well-known/oauth-protected-resource/mcp` | Public discovery metadata |
| API reference | `https://neurocardiotwin.vercel.app/api/reference` | Public API contract |

## Public technical documentation

The deployed public project brief is available at `/docs` (for example,
`https://neurocardiotwin.vercel.app/docs`). It documents the signal-to-ONNX
workflow, RAG privacy boundary, Auth0/Supabase access control, protected MCP
services and research-use safety constraints. Its live status card reads only
the public `/api/docs/status` capability endpoint; it never exposes private
profiles, raw waveforms or credentials.

## Architecture at a glance

```text
Authenticated user
      |
      v
CSV/manual signal input --> numerical validation --> fixed-size NumPy tensor
                                                        |
                                                        v
                                              ONNX Runtime inference
                                                        |
                              compact non-identifying model metadata only
                                                        |
                                                        v
Hugging Face embeddings --> Pinecone approved knowledge retrieval --> Qwen explanation
                                                        |
                                                        v
                         safeguarded research support + optional private metadata history
```

The language model never generates the primary biomedical prediction. Local
ONNX checkpoints produce the prediction; retrieval and language generation
only explain its compact result using approved knowledge.

## Model capabilities

| Workflow | Input contract | Output contract | Boundary |
| --- | --- | --- | --- |
| EEG seizure-pattern detection | 512 validated EEG samples | probability, threshold comparison, possible detection windows | Research pattern output only |
| ECG arrhythmia classification | 180 validated ECG samples | class, confidence, markers when supplied by model | Research classification only |
| ECG–EEG forecasting | 256 ECG + 256 EEG samples | 64-sample forecast when a compatible checkpoint is available | Forecast is not a clinical forecast |

Before inference, the server verifies finite numeric values, signal length,
sampling-rate bounds, selected-model compatibility and threshold bounds. An
invalid request returns an error; the frontend never fabricates a model result.

## CPU-first training pipeline

This i5/16 GB RAM-compatible starter downloads a bounded subset (ten MIT-BIH Arrhythmia records and six MIT-BIH Polysomnographic records with simultaneous ECG and EEG). Downloads resume from partial files. It deliberately uses record-level train/validation/test splits, but this remains a local research baseline—not a publishable or clinical validation.

```bash
cd /Users/imac/DIU_compettion/neurocardiotwin
.venv/bin/python scripts/download_starter_data.py
.venv/bin/python scripts/train_seizure.py 12
.venv/bin/python scripts/train_arrhythmia.py 12
.venv/bin/python scripts/train_forecast.py 12
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The server accepts CSV uploads or manual JSON signal samples for trained seizure and arrhythmia models. Forecasting remains unavailable until its paired ECG–EEG checkpoint and held-out evaluation are complete.

## Run locally

```bash
cd /Users/imac/DIU_compettion/neurocardiotwin
python3 -m http.server 5500
```

Open `http://localhost:5500`. A server is necessary because the app loads `data/demo-signals.json` with `fetch`.

## Data and API contract

`data/demo-signals.json` contains an anonymized drawing trace downsampled from the supplied local EEG cache, alongside a browser-generated simulated ECG trace. Both are labelled example/demo data and create no clinical result.

The frontend expects a same-origin FastAPI backend with `GET /api/health`, `GET /api/models/status`, `GET /api/metrics`, and `POST /api/analyze/{seizure,arrhythmia,forecast}`. Uploads use `FormData`; Manual parameters use JSON with `signal_values`, `session_id`, `sampling_rate`, and `threshold`. Unavailable services are shown as disconnected and do not create mock predictions.

## Secure profile and MCP configuration

The browser never receives a Supabase server key. Add these only as Vercel server environment variables:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<Supabase Secret key>
AUTH0_DOMAIN=<tenant>.auth0.com
AUTH0_CLIENT_ID=<Auth0 SPA client ID>
AUTH0_AUDIENCE=https://neurocardiotwin.vercel.app/mcp
```

Decision-support values are also server-only:

```text
HF_INFERENCE_TOKEN=<Hugging Face fine-grained inference token>
PINECONE_API_KEY=<Pinecone API key>
PINECONE_INDEX_HOST=<Pinecone index host, not dashboard URL>
PINECONE_NAMESPACE=neurocardiotwin-knowledge-v1
HF_CHAT_MODEL=Qwen/Qwen2.5-7B-Instruct
HF_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

Never commit these values, put them in browser JavaScript, or include them in
screenshots or chat. Rotate any secret shared outside a secure secret manager.

### MCP availability and discovery

The deployed public status endpoint provides safe MCP capability metadata
before a client completes Auth0 authorization:

```bash
curl -fsS https://neurocardiotwin.vercel.app/mcp/status
```

It returns endpoint names, tool counts, transport and authorization
requirements only. It cannot return profile data, history, uploaded files,
raw EEG/ECG values, access tokens or other secrets.

The MCP services are fail-closed: they are available through JSON-RPC 2.0 over
HTTPS POST but require a valid Auth0 RS256 access token with the `mcp:read`
permission before discovery or a tool runs. An unauthenticated `401 Bearer
access token required` response is expected and proves that the private
boundary is working.

| MCP server | Endpoint | Read-only tools | Data boundary |
| --- | --- | --- | --- |
| Workspace | `POST /mcp/workspace` | `get_my_profile`, `get_private_history`, `get_workspace_security` | Caller-owned profile/history only; no waveform arrays |
| Knowledge | `POST /mcp/knowledge` | `get_knowledge_catalog`, `search_approved_knowledge`, `get_rag_status` | Approved local research knowledge only |
| Models | `POST /mcp/models` | `get_model_status`, `get_model_capabilities`, `get_model_metrics` | Safe model status/metrics only; no waveform arrays |

Every server implements JSON-RPC `initialize`, `tools/list`, and `tools/call`.
OAuth protected-resource discovery metadata is available at:

```text
GET /.well-known/oauth-protected-resource/mcp
GET /.well-known/oauth-protected-resource/mcp/workspace
GET /.well-known/oauth-protected-resource/mcp/knowledge
GET /.well-known/oauth-protected-resource/mcp/models
```

No raw EEG, ECG, or uploaded signal values are returned by any MCP tool. The
signed-in browser workspace automatically runs authenticated `initialize` and
`tools/list` discovery through `js/mcp-client.js`. Verify the same contracts
from a local command line with a fresh user token (never commit or print it):

```bash
NCT_MCP_ACCESS_TOKEN='<access token>' .venv/bin/python scripts/check_mcp_servers.py --call-safe-tool
```

Expected successful output lists all three MCP servers plus one safe read-only
tool result for each. If a valid token returns `403 Required permission is
missing`, configure the Auth0 Post-Login Action below, sign out, then sign in
again to receive a newly issued token.

### Public standard-user tier

For self-service sign-up, configure an Auth0 Login / Post Login Action with this
code and add the SPA client ID as the `NCT_WEB_CLIENT_ID` Action secret:

```js
exports.onExecutePostLogin = async (event, api) => {
  if (event.client.client_id === event.secrets.NCT_WEB_CLIENT_ID && event.user.email_verified) {
    api.accessToken.setCustomClaim(
      'https://neurocardiotwin.app/permissions', ['mcp:read']
    );
  }
};
```

The API accepts this only after Auth0 JWT signature, issuer, audience, and
expiry validation. Only verified-email users receive standard MCP access; admin
permissions remain role-only.

### Verification-email delivery

The Auth0 database connection uses the deployed **Send NeuroCardioTwin
verification email** Post User Registration Action.  Its reviewed source is
[`auth0/actions/send-verification-on-registration.js`](auth0/actions/send-verification-on-registration.js).
For a new, unverified database user of the NeuroCardioTwin web client, it
obtains a short-lived Management API token from its Auth0 Action secrets and
creates one verification-email job.  The helper machine client has only the
`update:users` Management API scope; its client secret is stored only in Auth0
Action secrets, never in this repository, the browser, or Vercel.

## Private RAG decision support

The optional decision-support API combines an approved local knowledge base,
Pinecone retrieval and Hugging Face inference. It is deliberately a research
assistant, not a diagnosis, triage or treatment system. The provider boundary
receives only a compact local-model result summary: model type, score/class,
threshold, session label and input-quality counts. Raw EEG/ECG samples,
uploads, email addresses, Auth0 subjects and access tokens stay out of the
prompt, vector index and history table.

Apply [`supabase/migrations/0001_private_analysis_history.sql`](supabase/migrations/0001_private_analysis_history.sql)
in Supabase SQL Editor before enabling history. The API derives the history
owner from the verified Auth0 token and always queries by that server-side
profile id. It never accepts a user id from the browser.

Create a **new** Hugging Face fine-grained token with only `Make calls to
Inference Providers`, and a newly scoped Pinecone key. Do not put either value
in browser JavaScript, Git, `.env` committed to Git, screenshots, or chat.
Add server-only production secrets through the Vercel CLI prompts:

```bash
cd /Users/imac/DIU_compettion/neurocardiotwin
npx vercel env add HF_INFERENCE_TOKEN production
npx vercel env add PINECONE_API_KEY production
npx vercel env add PINECONE_INDEX_HOST production
npx vercel env add PINECONE_NAMESPACE production
npx vercel env add HF_CHAT_MODEL production
npx vercel env add HF_EMBEDDING_MODEL production
```

Use `Qwen/Qwen2.5-7B-Instruct` for `HF_CHAT_MODEL` and
`BAAI/bge-small-en-v1.5` for `HF_EMBEDDING_MODEL`, then create a Pinecone
cosine index with **384 dimensions** for that embedding model and place its
host (not its dashboard URL) in `PINECONE_INDEX_HOST`. After deployment, an
administrator with `admin:read` invokes `POST /api/knowledge/reindex` once to
index only the three reviewed markdown documents in `knowledge/`. Users can
then call `POST /api/decision`; their minimal decision-history records are
available only through `GET /api/history` for the same verified account.

After adding fresh secrets, a secure CLI smoke test is available:

```bash
.venv/bin/python scripts/check_ai_decision_support.py --live --reindex
```

## MCP troubleshooting

| Symptom | Meaning | Resolution |
| --- | --- | --- |
| `401 Bearer access token required` | The server is online but received no bearer token | Sign in and use a fresh Auth0 access token; do not make private tools public |
| `401 Token issuer or audience is invalid` | Token was minted for another API audience | Request a token for `AUTH0_AUDIENCE` exactly matching the deployed `/mcp` resource |
| `403 Required permission is missing` | The token is valid but lacks `mcp:read` | Apply the Post-Login Action, then sign out/in for a fresh token |
| `503 Authentication is not configured` | Required Vercel Auth0 variables are missing | Add `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_AUDIENCE`, then redeploy |
| Workspace tool storage error | Supabase storage or migrations are unavailable | Verify Vercel Supabase secrets and apply migrations `0001`, `0002`, and `0003` |

## Privacy and responsible AI

- Auth0 OAuth 2.0/OpenID Connect verifies authenticated access; the backend
  validates JWT signature, issuer, audience, expiry and required permission.
- Supabase private data is server-filtered by verified identity. Row Level
  Security migrations define ownership boundaries for private records.
- Raw waveform arrays, uploaded files, email addresses, Auth0 subjects and
  access tokens are excluded from RAG prompts, Pinecone vectors, MCP outputs,
  and completed-analysis history.
- The RAG corpus consists only of reviewed Markdown documents in `knowledge/`;
  user data is never indexed as knowledge.
- Chat and RAG output are constrained to research-support explanations. The
  interface surfaces immediate emergency guidance for urgent symptoms; users
  in Bangladesh should call **999** in an emergency.

## Repository map

```text
api/index.py                         Vercel serverless entrypoint
backend/vercel_app.py                FastAPI, ONNX APIs, MCP servers and static hosting
backend/security.py                  Auth0 JWT verification and Supabase persistence boundary
backend/decision_support.py          Privacy-filtered RAG and multilingual explanation service
js/                                  Browser workspace, charts, Auth0 and MCP discovery client
knowledge/                           Reviewed RAG source documents only
models/                              Local checkpoints and published research metrics
scripts/check_mcp_servers.py         Authenticated MCP contract verifier
scripts/check_ai_decision_support.py Safe RAG/provider verification helper
supabase/migrations/                 Private storage and RLS schema migrations
docs/                                Public technical brief
```
