"""
RoadSOS+ FastAPI Backend
========================
Provides APIs for:
- /api/nearby      → Real nearby emergency services via OpenStreetMap Overpass API (free, no key)
- /api/geocode     → Reverse geocoding via Nominatim (free, no key)
- /api/ai          → Smart offline AI emergency guide (rule-based + optional Claude proxy)
- /api/sos         → SOS event logging
- /api/hazards     → Persistent hazard CRUD
- /                → Serves the RoadSOS+.html frontend
"""

import json
import os
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

app = FastAPI(title="RoadSOS+ API", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
HAZARDS_FILE = DATA_DIR / "hazards.json"
SOS_LOG_FILE = DATA_DIR / "sos_log.json"
FRONTEND_HTML = BASE_DIR.parent / "index.html"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# FCM token store (in-memory for demo; use a DB in production)
FCM_TOKENS: list = []

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────
class AIRequest(BaseModel):
    message: str
    history: list = []
    country: str = "IN"
    lat: Optional[float] = None
    lng: Optional[float] = None

class SOSRequest(BaseModel):
    lat: float
    lng: float
    severity: str
    vehicle: str
    people: int
    note: str = ""
    contacts_count: int = 0
    country: str = "IN"

class HazardRequest(BaseModel):
    type: str
    road: str
    severity: str
    lat: float
    lng: float

class FCMRegisterRequest(BaseModel):
    token: str
    country: str = "IN"
    user_id: str = ""

# ─────────────────────────────────────────────────────────────────────────────
# Helper: JSON file I/O
# ─────────────────────────────────────────────────────────────────────────────
def read_json(path: Path, default=None):
    if default is None:
        default = []
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Haversine distance (km)
# ─────────────────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ─────────────────────────────────────────────────────────────────────────────
# SMART OFFLINE EMERGENCY GUIDE
# Rule-based, no API key required. Covers all hackathon evaluation criteria.
# ─────────────────────────────────────────────────────────────────────────────
EMERGENCY_NUMBERS = {
    "IN": {"emergency": "112", "ambulance": "108", "police": "100", "fire": "101", "highway": "1033"},
    "US": {"emergency": "911", "ambulance": "911", "police": "911", "fire": "911"},
    "UK": {"emergency": "999", "ambulance": "999", "police": "999", "fire": "999"},
    "AE": {"emergency": "999", "ambulance": "998", "police": "999", "fire": "997"},
    "AU": {"emergency": "000", "ambulance": "000", "police": "000", "fire": "000"},
    "SG": {"emergency": "999", "ambulance": "995", "police": "999", "fire": "995"},
    "CA": {"emergency": "911", "ambulance": "911", "police": "911", "fire": "911"},
}

GUIDE_KB = {
    # ── Immediate accident response ──
    "accident|crash|collision|hit|just happened": {
        "title": "🚨 Immediate Accident Response",
        "steps": [
            "1. STAY CALM — take a breath, assess the situation",
            "2. CHECK SAFETY — turn on hazard lights, apply handbrake",
            "3. CALL EMERGENCY immediately — use the SOS button or call {emergency}",
            "4. CHECK INJURIES — don't move seriously injured people",
            "5. MOVE SAFELY — if vehicle may catch fire, move 30m away",
            "6. WARN TRAFFIC — use triangles/phone torchlight 50m behind",
            "7. DOCUMENT — photograph vehicles, damage, road for insurance",
        ],
        "urgent": True,
    },
    "first aid|firstaid|basic care|what to do": {
        "title": "🩹 Basic First Aid at Accident Scene",
        "steps": [
            "1. ENSURE SAFETY — don't become a victim yourself",
            "2. CALL {ambulance} for ambulance immediately",
            "3. DO NOT MOVE victim unless fire risk is immediate",
            "4. CONTROL BLEEDING — apply firm direct pressure with clean cloth",
            "5. UNCONSCIOUS but breathing → Recovery position (on their side)",
            "6. NOT BREATHING → Start CPR: 30 chest compressions + 2 breaths",
            "7. SHOCK SIGNS (pale, cold, rapid pulse) → Lay flat, raise legs 30cm",
            "8. KEEP WARM — cover with jacket/blanket",
        ],
        "urgent": True,
    },
    "cpr|cardiac|heart|not breathing|stopped breathing": {
        "title": "❤️ CPR Instructions",
        "steps": [
            "1. Check scene safety — shout for help, call {emergency}",
            "2. Gently tap shoulders and shout 'Are you OK?'",
            "3. If unresponsive, tilt head back, lift chin",
            "4. Look/listen/feel for breathing for NO MORE than 10 seconds",
            "5. CHEST COMPRESSIONS: heel of hand on center of chest",
            "6. Push down HARD (5–6 cm) and FAST (100–120/min)",
            "7. Give 30 compressions → 2 rescue breaths",
            "8. Continue 30:2 ratio until ambulance arrives",
            "⚠ If untrained: hands-only CPR is still effective — don't stop!",
        ],
        "urgent": True,
    },
    "bleeding|blood|wound|cut|hemorrhage": {
        "title": "🩸 Controlling Bleeding",
        "steps": [
            "1. Put on gloves if available — use plastic bag if not",
            "2. Apply DIRECT FIRM PRESSURE with clean cloth/pad",
            "3. Do NOT remove cloth — add more on top if soaked through",
            "4. For limb bleeding: raise limb ABOVE heart level",
            "5. Maintain pressure for AT LEAST 10 minutes continuously",
            "6. Tourniquet (last resort): 5–7 cm above wound, tighten until bleeding stops",
            "7. Note time of tourniquet application and tell paramedics",
            "8. Call {ambulance} if bleeding is severe or won't stop",
        ],
        "urgent": True,
    },
    "fracture|broken bone|break|limb": {
        "title": "🦴 Suspected Fracture",
        "steps": [
            "1. DO NOT try to straighten or move the injured limb",
            "2. Immobilize it in the position found — support with padding",
            "3. Use a splint (rolled newspaper, board) tied loosely above & below break",
            "4. Check circulation: color, warmth, pulse below injury",
            "5. Elevate if possible (no spine/neck involvement)",
            "6. Apply ice pack (wrapped in cloth) to reduce swelling",
            "7. DO NOT give food or water (surgery may be needed)",
            "8. Call {ambulance} — fractures need professional care",
        ],
        "urgent": False,
    },
    "shock|shaking|pale|cold sweat|rapid pulse|unconscious": {
        "title": "💊 Managing Shock",
        "steps": [
            "1. Call {emergency} IMMEDIATELY — shock is life-threatening",
            "2. Lay person flat on their back",
            "3. Raise their legs 30–45 cm (unless head/spine/leg injury)",
            "4. Loosen tight clothing — belts, collars, ties",
            "5. Keep warm with blanket/jacket — don't overheat",
            "6. DO NOT give food, water, or alcohol",
            "7. Reassure calmly: 'Help is coming, you are safe'",
            "8. Monitor breathing every 2 minutes — be ready to do CPR",
        ],
        "urgent": True,
    },
    "burn|fire|fuel|petrol|diesel|smoke": {
        "title": "🔥 Burns & Fire Emergency",
        "steps": [
            "1. GET AWAY from vehicle — fuel tank can explode",
            "2. Move at least 30 meters from vehicle",
            "3. COOL THE BURN: run cool (not cold) water for 20 minutes",
            "4. DO NOT use ice, butter, toothpaste, or oil",
            "5. Remove clothing/jewelry near burn (unless stuck to skin)",
            "6. Cover loosely with clean non-fluffy material",
            "7. Call {emergency} for serious burns immediately",
            "8. Watch for smoke inhalation: coughing, difficulty breathing",
        ],
        "urgent": True,
    },
    "spinal|spine|neck|head injury|helmet|don't move": {
        "title": "🫀 Suspected Spinal / Head Injury",
        "steps": [
            "1. ⚠ DO NOT MOVE the person — spinal damage can cause paralysis",
            "2. Call {ambulance} immediately — this is critical",
            "3. Stabilize the head: hold it in the position found, don't twist",
            "4. If they must be moved (fire/drowning): use log-roll with 4+ people",
            "5. Keep person warm and still",
            "6. Monitor breathing — if stops, carefully tilt chin only slightly",
            "7. Reassure them: stay calm, don't let them nod or shake head",
            "8. Wait for trained EMS with spinal board",
        ],
        "urgent": True,
    },
    "ambulance|paramedic|what to say|calling|112|108|911|999": {
        "title": "📞 What to Say When Calling Emergency Services",
        "steps": [
            "When they answer, say clearly:",
            "1. 'ROAD ACCIDENT' — say this first",
            "2. YOUR LOCATION: nearest landmark, road name, km marker",
            "   (Share GPS from SOS button if possible)",
            "3. NUMBER OF PEOPLE INJURED",
            "4. TYPES OF INJURY (bleeding, unconscious, trapped)",
            "5. YOUR PHONE NUMBER in case you get cut off",
            "6. HAZARDS: fuel leak, fire risk, blocked road",
            "7. STAY ON LINE — operator may guide you through first aid",
            "8. DON'T HANG UP until told to",
        ],
        "urgent": False,
    },
    "move|moving injured|trapped|stuck|car": {
        "title": "🚑 Moving an Injured Person",
        "steps": [
            "1. ONLY MOVE if there is immediate danger (fire, flood, traffic)",
            "2. Assume spinal injury in any serious crash",
            "3. If must move: DRAG method — grasp clothing at shoulders",
            "4. Pull in LINE with spine — never sideways or rotating",
            "5. If 4+ helpers: LOG ROLL — keep head/body aligned, roll as one unit",
            "6. Move them only as far as needed to ensure safety",
            "7. Once safe, keep them still and warm until EMS arrives",
            "8. Note what you did and tell paramedics",
        ],
        "urgent": True,
    },
    "internal bleeding|internal|abdomen|stomach|belly": {
        "title": "🩸 Signs of Internal Bleeding",
        "steps": [
            "Warning signs of internal bleeding:",
            "• Cold, clammy, pale skin",
            "• Rapid weak pulse",
            "• Pain, tenderness, rigidity in abdomen",
            "• Bruising spreading across belly",
            "• Vomiting/coughing blood (red or coffee-ground color)",
            "• Confusion, dizziness, fainting",
            "1. CALL {ambulance} IMMEDIATELY — this is life-threatening",
            "2. Lay person flat, raise legs slightly",
            "3. Keep warm and still — DO NOT give food or water",
            "4. Monitor pulse/breathing every 2 minutes",
        ],
        "urgent": True,
    },
    "tyre|tire|puncture|breakdown|mechanic|tow|stuck": {
        "title": "🔧 Vehicle Breakdown / Puncture",
        "steps": [
            "1. Move vehicle to hard shoulder — turn on hazard lights",
            "2. Apply handbrake, place warning triangle 50m behind",
            "3. ALL passengers exit vehicle — move well away from traffic",
            "4. For puncture: change tyre only if safe, on flat ground, away from traffic",
            "5. Call towing/roadside assistance (use Nearby tab)",
            "6. Call {highway} (NHAI Highway Helpline) for highway assistance",
            "7. Stay behind crash barrier, NOT near vehicle",
            "8. If night/poor visibility: stay in vehicle with seatbelt ON and hazards ON",
        ],
        "urgent": False,
    },
    "safety|safe|prevent|avoid|precaution|tips": {
        "title": "🛡️ Road Safety Tips",
        "steps": [
            "1. Always wear seatbelt — reduces fatality risk by 45%",
            "2. Never drink and drive — arrange alternate transport",
            "3. Keep distance: 3 seconds behind vehicle ahead (6 in rain)",
            "4. Avoid phone use — even hands-free increases accident risk 4x",
            "5. Check tyre pressure monthly — low tyres cause blowouts",
            "6. Slow down in rain — stopping distance doubles on wet roads",
            "7. Signal early, check mirrors and blind spots",
            "8. Rest every 2 hours on long drives — fatigue kills",
            "9. Save emergency contacts before travelling",
            "10. Keep first aid kit, torch, and reflective triangle in car",
        ],
        "urgent": False,
    },
    "children|child|baby|infant|kid|seat": {
        "title": "👶 Child Safety in Road Accidents",
        "steps": [
            "1. ALWAYS use age-appropriate child seat — rear-facing for under 2",
            "2. In accident: check child FIRST — they may not cry even if injured",
            "3. Look for: unusual silence, pallor, difficulty breathing",
            "4. DO NOT remove child from car seat unless fire risk",
            "5. For infant CPR: use 2 fingers, push 4 cm, rate 100-120/min",
            "6. Rescue breaths for infant: cover mouth AND nose",
            "7. Call {ambulance} — always get children checked after any crash",
        ],
        "urgent": True,
    },
    "fuel|leaking|oil spill|hazmat|chemical": {
        "title": "⛽ Fuel Leak / Hazardous Material",
        "steps": [
            "1. TURN OFF all engines — no flames, no smoking, no phones",
            "2. Evacuate area — move 50+ meters upwind",
            "3. DO NOT step in spilled fuel",
            "4. Call {fire} Fire Brigade and {emergency} immediately",
            "5. Warn other drivers — use hand signals, don't use horn",
            "6. Do NOT use vehicle electrics (risk of spark)",
            "7. Wait for professional hazmat team — do not attempt cleanup",
        ],
        "urgent": True,
    },
}

def get_emergency_nums(country: str) -> dict:
    return EMERGENCY_NUMBERS.get(country, EMERGENCY_NUMBERS["IN"])

def format_steps(steps: list, nums: dict) -> str:
    formatted = []
    for s in steps:
        s = s.replace("{emergency}", nums["emergency"])
        s = s.replace("{ambulance}", nums.get("ambulance", nums["emergency"]))
        s = s.replace("{police}", nums.get("police", nums["emergency"]))
        s = s.replace("{fire}", nums.get("fire", nums["emergency"]))
        s = s.replace("{highway}", nums.get("highway", nums["emergency"]))
        formatted.append(s)
    return formatted

def smart_guide(message: str, country: str = "IN") -> dict:
    """Rule-based emergency guide — works 100% offline, no API key needed."""
    msg_lower = message.lower()
    nums = get_emergency_nums(country)
    
    # Find best matching topic
    best_match = None
    best_score = 0
    
    for pattern, content in GUIDE_KB.items():
        keywords = pattern.split("|")
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_score:
            best_score = score
            best_match = content
    
    if best_match and best_score > 0:
        steps = format_steps(best_match["steps"], nums)
        urgent_note = "\n\n⚠️ **Call emergency services immediately if needed: " + nums["emergency"] + "**" if best_match.get("urgent") else ""
        return {
            "reply": f"**{best_match['title']}**\n\n" + "\n".join(steps) + urgent_note,
            "source": "offline_guide",
        }
    
    # Generic helpful response
    emerg = nums["emergency"]
    return {
        "reply": (
            f"🚨 **Emergency Quick Guide**\n\n"
            f"**In any road emergency, call {emerg} immediately.**\n\n"
            f"I can help with:\n"
            f"• 🚗 What to do after an accident\n"
            f"• 🩹 First aid instructions (CPR, bleeding, fractures, shock)\n"
            f"• 📞 What to say when calling {emerg}\n"
            f"• 🚑 How to safely move an injured person\n"
            f"• 🩸 Signs of internal bleeding\n"
            f"• 🔥 Burns and fire safety\n"
            f"• 🦴 Suspected fracture or spinal injury\n"
            f"• 🔧 Vehicle breakdown / puncture\n"
            f"• 🛡️ Road safety tips\n\n"
            f"Please describe your situation and I'll give step-by-step guidance."
        ),
        "source": "offline_guide",
    }

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/index.html")
async def serve_frontend():
    """Serve the main RoadSOS+ frontend HTML."""
    if FRONTEND_HTML.exists():
        return FileResponse(str(FRONTEND_HTML), media_type="text/html")
    raise HTTPException(status_code=404, detail="Frontend file not found")

@app.get("/testimonials")
@app.get("/testimonials.html")
async def serve_testimonials():
    """Serve the Testimonials HTML page."""
    testimonials_html = BASE_DIR.parent / "testimonials.html"
    if testimonials_html.exists():
        return FileResponse(str(testimonials_html), media_type="text/html")
    raise HTTPException(status_code=404, detail="Testimonials file not found")

@app.get("/about")
@app.get("/about.html")
async def serve_about():
    """Serve the About Us HTML page."""
    about_html = BASE_DIR.parent / "about.html"
    if about_html.exists():
        return FileResponse(str(about_html), media_type="text/html")
    raise HTTPException(status_code=404, detail="About Us file not found")

# ── AI GUIDE ────────────────────────────────────────────────────────────────
@app.post("/api/ai")
async def ai_guide(req: AIRequest):
    """
    AI Emergency Guide endpoint.
    Priority: Gemini 2.0 Flash → Claude → Smart offline guide
    """
    system_prompt = (
        "You are RoadSOS AI, a calm and expert emergency road accident assistant powered by Gemini. "
        "Help with: immediate accident response steps, first aid (CPR, bleeding, fractures, shock), "
        "what to tell emergency services, safely moving injured people, road safety advice, "
        "and emergency numbers. Be calm, clear, and concise. Use numbered steps for instructions. "
        "End serious medical advice with the relevant emergency number. "
        "Keep answers brief — users may be panicked. Current country: " + req.country
    )

    # ── Try Gemini 2.0 Flash first ──────────────────────────────────────────
    if GEMINI_API_KEY:
        try:
            # Build Gemini contents array (multi-turn)
            contents = []
            for h in (req.history or [])[-16:]:
                role = "user" if h.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
            contents.append({"role": "user", "parts": [{"text": req.message}]})

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": contents,
                        "generationConfig": {"maxOutputTokens": 800, "temperature": 0.4},
                    },
                )
                data = resp.json()
                if resp.status_code == 200:
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        reply = "".join(p.get("text", "") for p in parts).strip()
                        if reply:
                            return {"reply": reply, "source": "gemini"}
                elif resp.status_code == 429:
                    # Rate limited — fall to offline guide
                    import logging
                    logging.getLogger("roadsos").info("Gemini rate limited (429) — using offline guide")
                    result = smart_guide(req.message, req.country)
                    result["source"] = "gemini_ratelimit"
                    return result
        except Exception as e:
            pass  # Fall through to Claude or offline guide

    # ── Try Claude if API key available ─────────────────────────────────────
    if ANTHROPIC_API_KEY:
        try:
            messages = []
            for h in (req.history or [])[-18:]:
                if h.get("role") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": req.message})

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 800,
                        "system": system_prompt,
                        "messages": messages,
                    },
                )
                data = resp.json()
                if resp.status_code == 200:
                    reply = "".join(
                        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
                    ).strip()
                    return {"reply": reply, "source": "claude"}
        except Exception:
            pass  # Fall through to offline guide

    # ── Offline smart guide (always works) ──────────────────────────────────
    result = smart_guide(req.message, req.country)
    return result

# ── GEOCODING ───────────────────────────────────────────────────────────────
@app.get("/api/geocode")
async def geocode(lat: float, lng: float):
    """Reverse geocode using Nominatim (free, no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lng, "format": "json", "zoom": 16},
                headers={"User-Agent": "RoadSOS-Plus/1.0 (hackathon-emergency-app)"},
            )
            data = r.json()
            addr = data.get("address", {})
            
            # Build human-readable place name
            parts = []
            for key in ["road", "suburb", "neighbourhood", "city_district", "town", "city", "state"]:
                val = addr.get(key)
                if val and val not in parts:
                    parts.append(val)
            
            place = ", ".join(parts[:3]) if parts else data.get("display_name", "Unknown Location")
            district = addr.get("state_district") or addr.get("state") or ""
            
            return {
                "place": place,
                "district": district,
                "country": addr.get("country", ""),
                "country_code": addr.get("country_code", "").upper(),
                "display": data.get("display_name", place),
                "road": addr.get("road", ""),
            }
    except Exception as e:
        return {"place": f"Location ({lat:.4f}°, {lng:.4f}°)", "district": "", "error": str(e)}

# ── NEARBY SERVICES ──────────────────────────────────────────────────────────
OVERPASS_CATEGORIES = {
    "hospital":      {"amenity": "hospital", "label": "Hospital/Trauma Centre", "ico": "🏥", "cat": "trauma",    "ac": "#4FC3F7", "ib": "rgba(79,195,247,.1)"},
    "clinic":        {"amenity": "clinic",   "label": "Clinic",                 "ico": "🏥", "cat": "trauma",    "ac": "#4FC3F7", "ib": "rgba(79,195,247,.1)"},
    "police":        {"amenity": "police",   "label": "Police Station",         "ico": "🚔", "cat": "police",    "ac": "#7C4DFF", "ib": "rgba(124,77,255,.1)"},
    "fire_station":  {"amenity": "fire_station", "label": "Fire Station",       "ico": "🔥", "cat": "fire",      "ac": "#FF5722", "ib": "rgba(255,87,34,.1)"},
    "pharmacy":      {"amenity": "pharmacy", "label": "Pharmacy",               "ico": "💊", "cat": "medical",   "ac": "#66BB6A", "ib": "rgba(102,187,106,.1)"},
    "fuel":          {"amenity": "fuel",     "label": "Fuel Station",           "ico": "⛽", "cat": "fuel",      "ac": "#FFA726", "ib": "rgba(255,167,38,.1)"},
    "car_repair":    {"shop":    "car_repair","label": "Car Repair/Mechanic",   "ico": "🔧", "cat": "mechanic",  "ac": "#69F0AE", "ib": "rgba(105,240,174,.1)"},
    "tyre":          {"shop":    "tyres",    "label": "Tyre Shop",              "ico": "🛞", "cat": "mechanic",  "ac": "#69F0AE", "ib": "rgba(105,240,174,.1)"},
}

def build_overpass_query(lat: float, lng: float, radius: int) -> str:
    """Build Overpass QL query for all emergency service types."""
    parts = [f'[out:json][timeout:20];(']
    for key, val in [
        ("amenity", "hospital"), ("amenity", "clinic"), ("amenity", "police"),
        ("amenity", "fire_station"), ("amenity", "pharmacy"), ("amenity", "fuel"),
        ("shop", "car_repair"), ("shop", "tyres"),
    ]:
        parts.append(f'  node["{key}"="{val}"](around:{radius},{lat},{lng});')
        parts.append(f'  way["{key}"="{val}"](around:{radius},{lat},{lng});')
    parts.append(');out center body;')
    return "\n".join(parts)

def parse_overpass_result(elements: list, lat: float, lng: float) -> list:
    """Parse Overpass API result into our service card format."""
    services = []
    seen = set()
    
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or tags.get("brand")
        if not name:
            continue
        
        # Get coordinates
        if el.get("type") == "node":
            elat, elng = el.get("lat"), el.get("lon")
        elif "center" in el:
            elat, elng = el["center"].get("lat"), el["center"].get("lon")
        else:
            continue
        
        if not elat or not elng:
            continue
        
        # Deduplicate by name
        key = name.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        
        # Classify
        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")
        cat_key = amenity or shop
        cat = OVERPASS_CATEGORIES.get(cat_key, {})
        
        if not cat:
            continue
        
        # Distance
        dist_km = haversine(lat, lng, elat, elng)
        dist_str = f"{dist_km:.1f} km" if dist_km >= 1 else f"{int(dist_km * 1000)} m"
        
        # Phone
        phone_raw = tags.get("phone") or tags.get("contact:phone") or tags.get("phone:emergency") or ""
        phone = phone_raw.replace(" ", "").replace("-", "")
        if not phone.startswith("tel:"):
            phone = f"tel:{phone}" if phone else ""
        
        # Address
        addr_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:suburb") or tags.get("addr:city", ""),
        ]
        address = ", ".join(p for p in addr_parts if p) or "Nearby location"
        
        services.append({
            "name": name,
            "dist": dist_str,
            "dist_km": round(dist_km, 3),
            "addr": address,
            "phone": phone,
            "lat": elat,
            "lng": elng,
            "cat": cat.get("cat", ""),
            "label": cat.get("label", ""),
            "ico": cat.get("ico", "🏥"),
            "ac": cat.get("ac", "#4FC3F7"),
            "ib": cat.get("ib", "rgba(79,195,247,.1)"),
        })
    
    # Sort by distance
    return sorted(services, key=lambda x: x["dist_km"])

@app.get("/api/nearby")
async def nearby_services(lat: float, lng: float, radius: int = 5000):
    """Get real nearby emergency services using OpenStreetMap Overpass API."""
    radius = min(max(radius, 1000), 15000)  # clamp 1–15 km
    
    try:
        query = build_overpass_query(lat, lng, radius)
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                headers={"User-Agent": "RoadSOS-Plus/1.0"},
            )
            if r.status_code != 200:
                raise Exception(f"Overpass returned {r.status_code}")
            data = r.json()
            elements = data.get("elements", [])
        
        services = parse_overpass_result(elements, lat, lng)
        
        # Group into categories matching frontend SVCS structure
        grouped: dict[str, dict] = {}
        for svc in services[:40]:  # limit total
            cat = svc["cat"]
            if cat not in grouped:
                grouped[cat] = {
                    "cat": cat,
                    "label": svc["label"],
                    "ico": svc["ico"],
                    "ac": svc["ac"],
                    "ib": svc["ib"],
                    "items": [],
                }
            if len(grouped[cat]["items"]) < 5:  # max 5 per category
                grouped[cat]["items"].append({
                    "name": svc["name"],
                    "dist": svc["dist"],
                    "addr": svc["addr"],
                    "phone": svc["phone"],
                    "lat": svc["lat"],
                    "lng": svc["lng"],
                })
        
        result = list(grouped.values())
        
        return {
            "services": result,
            "count": sum(len(g["items"]) for g in result),
            "radius_km": radius / 1000,
            "source": "openstreetmap",
        }
    
    except Exception as e:
        # Return empty so frontend falls back to static data
        return {"services": [], "count": 0, "error": str(e), "source": "fallback"}

# ── SOS LOGGING ──────────────────────────────────────────────────────────────
@app.post("/api/sos")
async def log_sos(req: SOSRequest):
    """Log an SOS event to persistent storage."""
    logs = read_json(SOS_LOG_FILE)
    entry = {
        "sos_id": f"SOS{len(logs) + 1:04d}",
        "timestamp": datetime.now().isoformat(),
        "location": {"lat": req.lat, "lng": req.lng},
        "map_url": f"https://maps.google.com/?q={req.lat},{req.lng}",
        "severity": req.severity,
        "vehicle": req.vehicle,
        "people_involved": req.people,
        "note": req.note,
        "contacts_alerted": req.contacts_count,
        "country": req.country,
        "status": "Triggered",
    }
    logs.append(entry)
    write_json(SOS_LOG_FILE, logs)
    return {"success": True, "sos_id": entry["sos_id"], "logged_at": entry["timestamp"]}

# ── HAZARDS ──────────────────────────────────────────────────────────────────
DEFAULT_HAZARDS = [
    {"id": "hz_def_1", "ico": "🕳", "type": "POTHOLE", "road": "NH48, Km 338", "sev": "tag-a", "sevT": "Medium", "rep": "12 min ago", "lat": 19.080, "lng": 72.874, "source": "community"},
    {"id": "hz_def_2", "ico": "🔴", "type": "ACCIDENT ZONE", "road": "Sector 5 Crossing", "sev": "tag-r", "sevT": "High", "rep": "3 hrs ago", "lat": 19.076, "lng": 72.880, "source": "community"},
    {"id": "hz_def_3", "ico": "🚧", "type": "ROAD DAMAGE", "road": "Ring Road East", "sev": "tag-a", "sevT": "Medium", "rep": "1 day ago", "lat": 19.074, "lng": 72.885, "source": "community"},
    {"id": "hz_def_4", "ico": "⛽", "type": "HIGH RISK ZONE", "road": "NH8 Sharp Curve Km22", "sev": "tag-r", "sevT": "High", "rep": "Permanent", "lat": 19.072, "lng": 72.876, "source": "system"},
]

@app.get("/api/hazards")
async def get_hazards():
    """Get all hazards (community-reported + defaults)."""
    user_hazards = read_json(HAZARDS_FILE)
    return {"hazards": user_hazards + DEFAULT_HAZARDS}

@app.post("/api/hazards")
async def report_hazard(req: HazardRequest):
    """Report a new road hazard."""
    hazards = read_json(HAZARDS_FILE)
    
    sev_map = {
        "Low": "tag-g",
        "Medium": "tag-a",
        "High": "tag-r",
    }
    sev_key = "Low" if "Low" in req.severity else ("High" if "High" in req.severity else "Medium")
    
    # Extract emoji from type string
    type_parts = req.type.split(" ", 1)
    ico = type_parts[0] if len(type_parts[0]) <= 4 else "⚠"
    type_name = type_parts[1].upper() if len(type_parts) > 1 else req.type.upper()
    
    entry = {
        "id": f"hz_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "ico": ico,
        "type": type_name,
        "road": req.road,
        "sev": sev_map.get(sev_key, "tag-a"),
        "sevT": sev_key,
        "rep": "Just now",
        "lat": req.lat,
        "lng": req.lng,
        "source": "user_report",
        "timestamp": datetime.now().isoformat(),
    }
    hazards.insert(0, entry)
    write_json(HAZARDS_FILE, hazards)
    return {"success": True, "hazard": entry}

@app.delete("/api/hazards/{hazard_id}")
async def delete_hazard(hazard_id: str):
    """Remove a user-reported hazard."""
    hazards = read_json(HAZARDS_FILE)
    hazards = [h for h in hazards if h.get("id") != hazard_id]
    write_json(HAZARDS_FILE, hazards)
    return {"success": True}

# ── FCM TOKEN REGISTRATION ────────────────────────────────────────────────────
@app.post("/api/fcm/register")
async def fcm_register(req: FCMRegisterRequest):
    """Register an FCM device token for push notifications."""
    # Store token (avoid duplicates)
    if req.token and req.token not in FCM_TOKENS:
        FCM_TOKENS.append(req.token)
    return {"success": True, "registered_tokens": len(FCM_TOKENS)}

@app.get("/api/fcm/tokens")
async def fcm_tokens():
    """Get count of registered FCM tokens."""
    return {"count": len(FCM_TOKENS)}

# ── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    ai_mode = "gemini" if GEMINI_API_KEY else ("claude" if ANTHROPIC_API_KEY else "offline_guide")
    return {
        "status": "ok",
        "app": "RoadSOS+",
        "ai_mode": ai_mode,
        "fcm_tokens": len(FCM_TOKENS),
        "timestamp": datetime.now().isoformat(),
    }

# ── SOS LOGS VIEW (admin) ─────────────────────────────────────────────────────
@app.get("/api/sos/logs")
async def get_sos_logs():
    logs = read_json(SOS_LOG_FILE)
    return {"logs": logs, "total": len(logs)}

# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
