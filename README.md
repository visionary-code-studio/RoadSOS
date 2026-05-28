# 🚑 RoadSOS+

### **Intelligent Emergency Road Assistance & Rescue Platform**
*IIT Madras Road Safety Hackathon — Project Submission*

---

## ✨ Overview

**RoadSOS+** is an advanced, location-aware emergency assistance and rescue coordination web application designed to save lives during the critical **"Golden Hour"** following road accidents. It helps victims, bystanders, and responders instantly locate and contact nearby essential rescue services, trigger emergency alerts, and receive immediate life-saving medical guidance—even in areas with low network connectivity or complete offline conditions.

This repository contains:
1. **Interactive Frontend Dashboard (`index.html` / `RoadSOS+.html`)**: A responsive UI utilizing advanced CSS/JS, modern animations, real-time geolocation, and Leaflet.js-based OSM mapping.
2. **FastAPI Backend Services (`backend/`)**: A high-performance Python-based server implementing OSM Overpass discovery, geocoding, persistent SOS logging, custom road hazard reporting, and emergency AI triage.

---

## 🎯 Key Hackathon Requirements Met

| Core Requirement | RoadSOS+ Feature |
| :--- | :--- |
| **Trauma Centres & Hospitals** | Fully integrated using high-accuracy OSM Overpass API to query nearby emergency medical clinics. |
| **Ambulance Services** | Actionable dialers for local ambulance services and nearby medical providers. |
| **Police Stations** | Direct location queries for nearest local police, highway patrol, and fire stations. |
| **Vehicle Rescue & Towing** | Integrated recovery services including towing support, car mechanics, and puncture repair. |
| **Offline Functionality** | Local-first design: cached state, country-level emergency helpline databases, SMS simulation fallbacks, and local rules-based AI medical triage. |
| **Global Applicability** | Auto-detects user country (ISO 3166) using lat/lng geocoding to dynamically configure national emergency helpline numbers (supporting over 30 countries globally). |
| **Additional Innovation** | Simulated visual/audio alarm system, interactive custom hazard reporter (to flag potholes/accidents), and interactive SOS console. |

---

## 🚀 Key Features

### 📍 1. Dynamic Geolocation & OSM Mapping
- Automatically resolves GPS coordinates to retrieve physical addresses via reverse geocoding.
- Dynamically queries nearby hospitals, police stations, towing services, and mechanics within a custom radius.
- Plots results on an interactive map showing physical routes, distances, and contact details.

### 📶 2. Smart Offline Emergency Fallback
- **Offline Triage**: The built-in AI Guide features a client-side and server-side rules-based emergency responder that provides immediate first-aid advice (for CPR, fractures, heavy bleeding, burns, etc.) when the LLM API is unavailable.
- **Helpline Database**: Embedded database of emergency numbers (Police, Ambulance, Fire) for over 30 countries.
- **SMS Simulation**: One-click SOS dispatch that simulates SMS alerts with precise coordinates when internet connectivity is down.

### 🤖 3. AI First-Aid & Emergency Assistant
- Conversational chat interface specifically tuned for emergency first-aid instruction.
- Dual-mode operation:
  - **Online Mode**: Integrates with LLMs for nuanced, conversational answers.
  - **Offline Fallback Mode**: Instantly switches to high-speed, local rule-based classification to guarantee instant, medically accurate instructions without any network latency.

### ⚠️ 4. Road Safety & Hazard Crowdsourcing
- Users can flag new road hazards (potholes, severe waterlogging, recent accidents, structural damage) in real time.
- The reported hazards are instantly cataloged, saved in a backend database (`hazards.json`), and visually plotted as warning markers on the map for all passing vehicles.

---

## 👤 User Personas

### 1. Accident Victim
A driver or passenger involved in an accident who needs immediate help and first-aid triage guidance under stressful conditions.

### 2. Bystander / Helper
A citizen responder assisting the victim and trying to contact emergency services and discover nearby trauma centers quickly.

### 3. Frequent Road User
Daily commuters, delivery riders, cab drivers, or long-distance travelers who need roadside rescue support, breakdown assistance, and towing.

### 4. Emergency Responder
Ambulance operators, highway patrols, volunteers, or rescue teams who need quick access to accident locations and structural hazard reports.

---

## 🎯 Product Objectives & Success Metrics

- **Reduce Emergency Response Time**: Minimize the search and coordinate dispatch times down to seconds during the "Golden Hour".
- **Ensure Offline Reliability**: Guarantee critical emergency contacts and medical first-aid information remain accessible even in zero-signal environments.
- **Actionable Service Discovery**: Go beyond simple mapping to provide direct one-click dial buttons, real-time route navigation links, and distance metrics.
- **Active Crowdsourcing**: Create a safer driving ecosystem by allowing real-time hazard flagging (potholes, accidents) that instantly alerts subsequent users.

---

## 📂 Project Directory Structure

```
RoadSOS+/
│
├── index.html                           # Beautiful main frontend dashboard (HTML, CSS, JS)
├── RoadSOS+.html                        # Duplicate of index.html for compatibility
├── README.md                            # Comprehensive project guide (this file)
├── RoadSOS_AI_IITM_Hackathon.md         # Original hackathon project brief
├── RoadSOS+ Product Requirement Document.pdf  # Project PRD
├── RoadSOS+ Technical Architecture.pdf   # Technical Architecture Document
│
└── backend/
    ├── main.py                          # FastAPI application containing 14 REST endpoints
    ├── requirements.txt                 # Backend Python package requirements
    ├── .env.example                     # Environment configuration template
    ├── .env                             # Secret environment variables (GIT IGNORED)
    └── data/
        ├── hazards.json                 # Persistent storage for crowdsourced hazard alerts
        └── sos_log.json                 # Persistent logs for simulated SOS triggers
```

---

## 🛠️ Technology Stack

- **Frontend**: Standard HTML5, CSS3 (Modern dark-mode glassmorphism, responsive grids, transitions), Vanilla JavaScript.
- **Mapping**: Leaflet.js with OpenStreetMap.
- **Backend**: Python 3.9+ with FastAPI & Uvicorn.
- **Database**: File-based persistent JSON layers for hackathon ease-of-deployment.

---

## ⚙️ Running Locally

### 1. Prerequisites
- **Python**: Make sure Python 3.9 or higher is installed.
- **Modern Browser**: Chrome, Edge, Safari, or Firefox.

### 2. Set Up the Backend
Navigate to the `backend` directory, install the required packages, and start the server:

```bash
# Go to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The backend server will spin up on `http://localhost:8000`. You can explore the interactive API documentation at `http://localhost:8000/docs`.

### 3. Set Up the Environment (Optional)
A `.env.example` file is provided in the `backend/` directory. If you want to enable online LLM features for the AI Assistant, you can create a `.env` file in the `backend/` directory:

```bash
ANTHROPIC_API_KEY=your_key_here
```
*Note: If no API key is specified, the application seamlessly and gracefully falls back to the **local rules-based Emergency Guide**.*

### 4. Launch the Frontend
Simply open `index.html` directly in your browser, or serve it using any local static web server (such as VS Code Live Server or python's `http.server`):

```bash
# From the project root
python -m http.server 3000
```
Then visit `http://localhost:3000` in your web browser.

---

## 🚑 How to Test the Hackathon Prototype

1. **Start the Frontend & Backend**: Ensure both are running.
2. **Grant Location Access**: Click "Allow Location" on your browser. The app will auto-detect your location and pull local emergency numbers (e.g., `112` / `100` / `102` for India).
3. **Simulate Offline Mode**: Check the "Simulate Offline Mode" toggle at the top of the interface. Watch the UI immediately adapt to local fallbacks.
4. **Trigger SOS**: Click the pulsing red **SOS Emergency Alert** button. Input severity details, then click "Simulate Dispatch". Watch the live mock console log SMS transmissions, trigger local audio alarm warnings, and write to `backend/data/sos_log.json`.
5. **Search Services**: Search for nearby "Hospitals", "Police", or "Towing". The dynamic card display will populate with distances, contact links, and map markers.
6. **Ask the AI Assistant**: Try typing *"How to do CPR?"* or *"What to do for a bleeding head wound?"* into the AI Chatbot to see instantaneous triage answers.
7. **Report a Hazard**: Scroll to the "Road Safety Reporter" panel, select "Pothole" or "Accident", add a description, and report. You will see it register instantly on the map!

---

## 🗺️ Roadmap & Future Scope

### Phase 1 — MVP (Completed)
- Geolocation & dynamic Overpass API search integration.
- Offline status simulation, helpline database, and local chatbot rules engine.
- Persistent hazard reporting and simulated SOS console.

### Phase 2 — Production Reliability
- Verified emergency contact database syncing from government registries.
- Advanced routing routing algorithms optimized for sirens & ambulances.
- Automatic local DB replication to offline-ready Service Workers.

### Phase 3 — Active Road Safety Intelligence
- Computer vision pothole and damage detection using mobile dashcams.
- Real-time auditory warning alerts when entering high-accident zones.
- Embedded CAN-bus vehicle health anomaly detection (engine heat, brake pad wear).

---

## 🙏 Acknowledgments
- **IIT Madras Road Safety Hackathon** for the inspiring and critical theme.
- **OpenStreetMap** and the open GIS ecosystem for democratizing geographical search data.
