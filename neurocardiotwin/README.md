# NeuroCardioTwin frontend

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
