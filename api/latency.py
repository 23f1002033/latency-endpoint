from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

app = FastAPI()

# Enable CORS for all origins (POST requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Telemetry data cache (loaded lazily)
_DATA: Optional[pd.DataFrame] = None


def get_data() -> pd.DataFrame:
    """Load telemetry CSV lazily and cache the DataFrame.

    This avoids failing at import time (which can make debugging deployments
    harder) and provides a clearer error when the CSV is missing.
    """
    global _DATA
    if _DATA is not None:
        return _DATA

    root = Path(__file__).parent.parent
    csv_path = root / "telemetry_sample.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"telemetry file not found at {csv_path}")

    df = pd.read_csv(csv_path)

    # normalize column names that may differ across sample files
    if "uptime_pct" in df.columns and "uptime" not in df.columns:
        df = df.rename(columns={"uptime_pct": "uptime"})

    _DATA = df
    return _DATA


@app.get("/")
async def latency_health():
    """Simple GET health endpoint for quick verification (returns 200).

    This helps debugging deployments from a browser/GET tool where POST
    would otherwise return 405 or 404 if routing or method is incorrect.
    """
    return {"status": "ok", "note": "POST JSON to this endpoint with 'regions' and optional 'threshold_ms'"}


@app.post("/")
async def latency_metrics(request: Request):
    try:
        data = get_data()
    except FileNotFoundError as e:
        # Return a 500 with a clear message so Vercel logs and responses are helpful
        raise HTTPException(status_code=500, detail=str(e))

    payload = await request.json()
    regions = payload.get("regions", [])
    threshold = payload.get("threshold_ms", 180)

    results = {}
    for region in regions:
        region_data = data[data["region"] == region]
        if len(region_data) == 0:
            # include empty result for region so caller knows it was missing
            results[region] = {"error": "no data for region"}
            continue

        latencies = region_data["latency_ms"]
        # tolerate either 'uptime' or 'uptime_pct' normalized earlier
        uptimes = region_data.get("uptime") if "uptime" in region_data else None

        results[region] = {
            "avg_latency": float(latencies.mean()),
            "p95_latency": float(np.percentile(latencies, 95)),
            "avg_uptime": float(uptimes.mean()) if uptimes is not None else None,
            "breaches": int((latencies > threshold).sum())
        }

    return results
