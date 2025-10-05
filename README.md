# latency-endpoint

This project exposes a simple FastAPI serverless endpoint intended to be deployed on Vercel.

Endpoints
- GET  /api -> health
- POST /api with JSON {"regions": [...], "threshold_ms": 180} -> returns per-region metrics

Quick local test

1. Create and activate a Python venv, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run locally:

```bash
uvicorn api.index:app --port 8000
```

3. Test:

```bash
curl -i http://localhost:8000/
curl -i -X POST http://localhost:8000/ -H 'Content-Type: application/json' -d '{"regions":["emea","amer"],"threshold_ms":166}'
```

Deploy to Vercel

- Create a GitHub repo and push this project.
- Import the repo into Vercel (connect via GitHub) and deploy.
- The function will be available at: `https://<your-vercel-deployment>/api`

Notes
- The repo includes a small `telemetry_sample.csv` so POST returns sample data.
- CORS is enabled for GET/POST from any origin.
