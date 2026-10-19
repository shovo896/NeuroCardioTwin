# NeuroCardioTwin

A build-free HTML/CSS/JavaScript research dashboard for EEG/ECG workflows. It is explicitly not a medical device.

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

`/mcp` is fail-closed: it is unavailable until both Supabase and Auth0 configuration are present, and it requires a valid Auth0 RS256 access token with the `mcp:read` permission. The protected-resource metadata endpoint is `/.well-known/oauth-protected-resource/mcp`. No raw EEG, ECG, or uploaded signal values are persisted by these profile/audit helpers.

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
