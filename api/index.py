from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path
import csv
import statistics

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cors_header(request, call_next):
    """Ensure Access-Control-Allow-Origin is present on all responses.

    FastAPI's CORSMiddleware should handle this, but some serverless routing
    or static responses can miss the header. This middleware guarantees the
    header is present for both normal and preflight responses.
    """
    response = await call_next(request)
    # don't override if set, but ensure wildcard is available
    if "access-control-allow-origin" not in {k.lower() for k in response.headers.keys()}:
        response.headers["Access-Control-Allow-Origin"] = "*"
    # also ensure preflight headers are present when appropriate
    if request.method == "OPTIONS":
        response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        response.headers.setdefault("Access-Control-Allow-Headers", "*")
    return response


class Query(BaseModel):
    regions: List[str]
    threshold_ms: int = 180


def load_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"telemetry file not found at {path}")
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            # normalize and convert numeric fields
            try:
                r["latency_ms"] = float(r.get("latency_ms", "0"))
            except ValueError:
                r["latency_ms"] = 0.0
            # support both uptime_pct and uptime
            uptime_key = "uptime" if "uptime" in r else ("uptime_pct" if "uptime_pct" in r else None)
            if uptime_key:
                try:
                    r["uptime"] = float(r.get(uptime_key, "0"))
                except ValueError:
                    r["uptime"] = 0.0
            else:
                r["uptime"] = None
            rows.append(r)
    return rows


def percentile(values: List[float], percent: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v)-1) * (percent/100.0)
    f = int(k)
    c = min(f+1, len(sorted_v)-1)
    if f == c:
        return float(sorted_v[int(k)])
    d0 = sorted_v[f] * (c - k)
    d1 = sorted_v[c] * (k - f)
    return float(d0 + d1)


@app.get("/")
async def health():
    return {"status": "ok", "note": "POST JSON to this endpoint with 'regions' and optional 'threshold_ms'"}


@app.post("/")
async def metrics(q: Query):
    root = Path(__file__).parent.parent
    csv_path = root / "telemetry_sample.csv"
    try:
        rows = load_csv(csv_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    results = {}
    for region in q.regions:
        region_rows = [r for r in rows if r.get("region") == region]
        if not region_rows:
            results[region] = {"error": "no data for region"}
            continue

        latencies = [r["latency_ms"] for r in region_rows]
        uptimes = [r["uptime"] for r in region_rows if r.get("uptime") is not None]

        avg_latency = statistics.mean(latencies) if latencies else 0.0
        p95_latency = percentile(latencies, 95)
        avg_uptime = statistics.mean(uptimes) if uptimes else None
        breaches = sum(1 for v in latencies if v > q.threshold_ms)

        results[region] = {
            "avg_latency": round(avg_latency, 3),
            "p95_latency": round(p95_latency, 3),
            "avg_uptime": round(avg_uptime, 3) if avg_uptime is not None else None,
            "breaches": breaches,
        }

    return results


# Duplicate routes that some Vercel mounts forward (helps avoid double-prefixing issues)
@app.get("/api")
async def health_api():
    return await health()


@app.post("/api")
async def metrics_api(q: Query):
    return await metrics(q)


# Catch-all: respond to any path under the function mount
@app.get("/{full_path:path}")
async def health_catchall(full_path: str):
    return await health()


@app.post("/{full_path:path}")
async def metrics_catchall(full_path: str, q: Query):
    return await metrics(q)
