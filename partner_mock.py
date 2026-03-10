import random
import uuid

from fastapi import FastAPI

app = FastAPI(title="Partner Bank Mock")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/authorize")
async def authorize(payload: dict):
    """
    Simulates partner bank authorization.
    Returns a transaction_id 90% of the time; raises 500 10% of the time.
    """
    if random.random() < 0.10:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Simulated partner failure")

    return {
        "transaction_id": str(uuid.uuid4()),
        "status": "approved",
        "external_id": payload.get("external_id"),
    }
