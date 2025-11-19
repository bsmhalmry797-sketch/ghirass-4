# main99.py  --- FastAPI backend for Ghirass Smart Irrigation

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

app = FastAPI(title="Ghirass Smart Irrigation API")

# ---- CORS (Ø¹Ø´Ø§Ù† Ø§Ù„ÙØ±ÙˆÙ†Øª Ø¥Ù†Ø¯ ÙŠÙ‚Ø¯Ø± ÙŠØªØµÙ„ Ù…Ù† Ø§Ù„Ù…ØªØµÙØ­) ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Ù„Ù„Ù…Ø´Ø±ÙˆØ¹ØŒ Ø¹Ø§Ø¯ÙŠ Ù†Ø®Ù„ÙŠÙ‡Ø§ Ù…ÙØªÙˆØ­Ø©
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Ø´ÙƒÙ„ Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„ØªÙŠ ÙŠØ±Ø³Ù„Ù‡Ø§ Ø§Ù„Ø±Ø§Ø²Ø¨ÙŠØ±ÙŠ ----
class SensorPayload(BaseModel):
    timestamp: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    soil_pct: float
    proba: float
    pump_on: bool
    reason: str
    run_sec_this_hour: int
    delta_soil: float

# ---- Ù†Ø®Ø²Ù‘Ù† Ø¢Ø®Ø± Ø­Ø§Ù„Ø© Ù‡Ù†Ø§ ----
latest_status: Dict[str, Any] = {
    "timestamp": "N/A",
    "temperature": None,
    "humidity": None,
    "soil_pct": 0.0,
    "proba": 0.0,
    "pump_on": False,
    "reason": "Waiting for data",
    "run_sec_this_hour": 0,
    "delta_soil": 0.0,
}

@app.get("/")
def root():
    return {"status": "ok", "message": "Ghirass FastAPI backend is running"}

# Ø§Ù„Ø±Ø§Ø²Ø¨ÙŠØ±ÙŠ ÙŠØ±Ø³Ù„ Ù„Ù‡Ù†Ø§ ÙƒÙ„ 1â€“2 Ø«Ø§Ù†ÙŠØ©
@app.post("/update_sensor")
def update_sensor(payload: SensorPayload):
    global latest_status
    latest_status = payload.dict()
    return {"status": "updated"}

# Ø§Ù„ÙØ±ÙˆÙ†Øª Ø¥Ù†Ø¯ Ø¹Ù†Ø¯ ØµØ¯ÙŠÙ‚ØªÙƒ ØªÙ‚Ø±Ø£ Ù…Ù† Ù‡Ù†Ø§ ÙˆØªØ¹Ø±Ø¶ Ø§Ù„Ù‚ÙŠÙ…
@app.get("/latest_status")
def get_latest_status():
    return latest_status
