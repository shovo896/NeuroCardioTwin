# NeuroCardioTwin frontend

A build-free HTML/CSS/JavaScript research dashboard for EEG/ECG workflows. It is explicitly not a medical device.

## Run locally

```bash
cd /Users/imac/DIU_compettion/neurocardiotwin
python3 -m http.server 5500
```

Open `http://localhost:5500`. A server is necessary because the app loads `data/demo-signals.json` with `fetch`.

## Data and API contract

`data/demo-signals.json` contains an anonymized drawing trace downsampled from the supplied local EEG cache, alongside a browser-generated simulated ECG trace. Both are labelled example/demo data and create no clinical result.

The frontend expects a same-origin FastAPI backend with `GET /api/health`, `GET /api/models/status`, `GET /api/metrics`, and `POST /api/analyze/{seizure,arrhythmia,forecast}`. File uploads use `FormData`; unavailable services are shown as disconnected and do not create mock predictions.

### Text-to-signal API contract

The **Text-to-signal** mode sends JSON to `POST /api/generate-signal`:

```json
{"text":"approved research generation parameter","session_id":"optional-id","sampling_rate":128,"analysis_mode":"seizure"}
```

The backend must return either `{ "analysis_result": { ... } }` for an end-to-end response, or `{ "signal_id": "..." }`. In the latter case the UI sends JSON to the chosen `POST /api/analyze/{mode}` endpoint with the `signal_id`; therefore generation and inference remain backend-owned. Treat this as experimental research functionality only.
