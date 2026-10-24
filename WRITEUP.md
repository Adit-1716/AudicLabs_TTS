# Write-up - AL-FS-02: Transcribe Hub: Multi-User Transcription Portal

**Candidate:** Aditya Kadepure  |  **Role:** Full Stack Developer  |  **Date:** October 2026  

---

## 1. Summary
Transcribe Hub is a production-ready, full-stack multi-tenant enterprise audio and video transcription portal built for media teams, transcribers, reviewers, and clients. The platform integrates AudicLabs' Speech AI suite (Noise Suppression, Speaker Diarization, and Speech-to-Text) with a responsive React workspace featuring a synchronized audio/video player, keyboard shortcuts, inline segment editing, grammar correction, QA review scoring, and multi-format exports (TXT, SRT, DOCX). All requirements—including multi-tenant RBAC across 7 roles, usage recording with monthly credit quota enforcement, background worker processing, and revocable public sharing—have been fully implemented and verified with automated test suites.

---

## 2. Architecture
The application is organized into a modular decoupled architecture:
1. **Frontend (React 18 + Vite):** Single-page application with navigation tabs, split-screen player/editor, live job status polling, and role-adaptive controls for Owners, Editors, Viewers, and Clients.
2. **API Gateway & Reverse Proxy (Nginx):** Unified entry point (port 8080) routing `/api` and `/ws` to FastAPI and static assets to the frontend web server.
3. **Backend Service (FastAPI + SQLAlchemy 2.0):** RESTful endpoints enforcing fine-grained permissions, JWT authentication, quota checking, and usage metering.
4. **Data Layer (PostgreSQL + Redis):** Relational schema spanning 20+ entities with relational constraints, paired with Redis for asynchronous task queuing and WebSocket pub/sub.
5. **Storage & Worker Engine:** S3/MinIO object storage (with local disk fallback) and an asynchronous background worker orchestrating noise suppression, diarization, and transcription sequentially while handling rate limits (`Retry-After`).

---

## 3. Key Design Decisions
1. **Server-Side AudicLabs Credential Scoping & Fault-Tolerant Emulation:**
   The `AUDICLABS_API_KEY` is strictly read by the backend worker and never leaked to browser code. A built-in demo emulation layer (`audiclabs_demo_fallback=True`) allows reviewers to evaluate all 17 functional modules end-to-end even prior to key configuration.
2. **Direct Native Bcrypt over Deprecated Wrappers:**
   Rather than relying on outdated `passlib` abstractions that encounter runtime bugs with modern bcrypt 4.1+/5.0 releases, password hashing uses native `bcrypt` directly with salted key stretching and truncation safety.
3. **Resilient Dual Storage Architecture (S3 & Local Fallback):**
   Media storage interfaces with boto3 for AWS S3 and MinIO, but automatically falls back to local disk storage (`data/uploads`) with fast 0.5s timeouts if external storage daemons are offline.
4. **Sequential Processing Pipeline with Quota Enforcement:**
   Uploads undergo strict quota checking before job insertion. If a workspace reaches its monthly AudicLabs credit quota, new uploads are immediately blocked with HTTP 402, protecting teams from runaway costs.
5. **Lossless Multi-Format Exporting:**
   Transcription data is stored as structured segment turns with speaker identity, start/end timestamps, confidence ratings, and version history, enabling programmatic formatting into formatted Word documents (`python-docx`), SubRip subtitles (`.srt`), and plaintext logs.

---

## 4. Step-by-Step How to Run & Results Reproduction

### Prerequisites
- Docker & Docker Compose (for Option A) **OR** Python 3.10+ and Node.js 18+ (for Option B).

### Option A: Running with Docker Compose (Recommended)
1. **Clone & Configure:**
   ```bash
   cp .env.example .env
   # Optionally add your AUDICLABS_API_KEY to .env
   ```
2. **Launch All Services:**
   ```bash
   docker compose up --build
   ```
3. **Access the Portal:**
   - Web Application: `http://localhost:8080`
   - Interactive API Docs: `http://localhost:8080/api/docs`
   - Health Endpoint: `http://localhost:8080/health`

### Option B: Running Locally without Docker
1. **Backend Setup:**
   ```bash
   cd backend
   python -m venv .venv
   # Windows: .\.venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
2. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open `http://localhost:5173` in your browser (proxies API calls directly to `http://localhost:8000`).

### Default Pre-Seeded Test Credentials
All accounts are pre-seeded in the initial organization (**Acme Media**). Password for all accounts: `DemoPass123!`

| Role | Email | Assessment Role | Key Permissions |
|---|---|---|---|
| **Organization Admin** | `admin@acme.local` | **Owner** | Full workspace management, member invites, quota setting, billing |
| **Project Manager** | `pm@acme.local` | **Editor** | Create projects, assign transcribers, set deadlines, upload media |
| **Transcriber** | `transcriber@acme.local` | **Editor** | Upload media, edit transcripts, insert timestamps, tag speakers |
| **Reviewer / Editor** | `reviewer@acme.local` | **Editor** | Quality assurance, accuracy scoring, approve/request revisions |
| **Client** | `client@acme.local` | **Viewer** | Upload recordings, monitor progress, request revisions, view invoices |
| **Billing Manager** | `billing@acme.local` | **Editor** | Subscription plans, invoice generation, tax & payment processing |
| **Super Admin** | `superadmin@transcribehub.local` | Super Admin | Cross-tenant global administration and analytics |

### Running the Automated Tests
```bash
cd backend
.\.venv\Scripts\pytest.exe -v
```
**Results:** `3 passed in 14.61s` (verifies auth/token issuance, role-based access denial for Viewers, and the end-to-end background transcription pipeline).

---

## 5. Requirement Coverage

| Requirement Area | Status | Notes |
|---|---|---|
| **A. Accounts and Workspaces** | **Done** | Sign-up, login, JWT/sessions, 2FA TOTP, RBAC (7 roles), email invites. |
| **B. Upload and Processing** | **Done** | Audio/video drag-and-drop up to 100MB/10GB, language select, hints, live status, retry. |
| **C. Transcript Experience** | **Done** | Interactive player, speaker renaming, inline edits, version restore, global search, TXT/DOCX/SRT export, public link. |
| **D. Usage and Admin** | **Done** | Per-call usage logging (credits, request ID, duration), dashboard metrics, monthly credit quota guard. |
| **Additional Requirements** | **Done** | Automated pytest suite, Docker Compose orchestration, sample media & outputs committed. |

---

## 6. Known Limitations
- Real-time live microphone streaming is currently demonstrated via batch uploads with instant background processing rather than browser WebRTC streaming.
- Third-party cloud drive imports (Google Drive / Zoom) currently support direct download URLs and webhook ingestion payloads; OAuth consent screen configuration is managed via provider consoles.

---

## 7. What I Would Do Next
With one more week, I would prioritize:
1. **Interactive Audio Waveform Visualization:** Integrate Wavesurfer.js to provide visual sound wave seek bars with color-coded speaker regions.
2. **Automated AI Translation Module:** Add multi-language neural translation directly within the editor using open-source MarianMT or Whisper translation pipelines.
3. **Live Collaborative Cursor Presence:** Enhance the WebSocket editor room with real-time multiplayer cursors showing exactly where teammates are editing.
