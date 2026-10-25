# Transcribe Hub: Multi-User Transcription Portal

**Assessment ID:** AL-FS-02  
**Candidate:** Aditya Kadepure  
**Role:** Full Stack Developer  
**Focus Area:** Speech to Text, Speaker Diarization, Noise Suppression, Multi-tenant Workflow Platform  

---

## 1. Overview

**Transcribe Hub** is a multi-tenant enterprise audio and video AI transcription platform. It enables transcription teams, media studios, clients, and reviewers to upload media, process it through AudicLabs' Speech AI engine (noise suppression, speaker diarization, and speech-to-text), edit transcripts in an interactive player workspace with version control, conduct quality assurance reviews, and export transcripts into TXT, DOCX, and SRT formats.

### Core Capabilities
- **Multi-Tenant Workspaces & RBAC:** Complete isolation across organizations. Enforces 7 discrete roles: Super Admin, Organization Admin (Owner), Project Manager (Editor), Transcriber (Editor), Reviewer (Editor), Client (Viewer), and Billing Manager.
- **Robust Speech AI Pipeline:** Sequential background processing with optional noise reduction (`/v1/noise-suppressor/denoise`), speaker diarization (`/v1/diarization/diarize`), and speech-to-text (`/v1/stt/transcriptions`), with live job progress tracking without page refreshes.
- **Manual Transcription Workspace:** Synchronized audio/video player, keyboard shortcuts (Space play/pause), variable speed control (0.5x–2.0x), one-click timestamp insertion, speaker turn renaming, and draft auto-saving with full revision history.
- **Quality Assurance & Review:** Grammar error checking, accuracy & completion scoring, reviewer notes, and formal approval/revision workflows.
- **Client Portal & Collaboration:** Clients can upload files, monitor status, request revisions, and chat securely with project managers.
- **Usage & Quota Governance:** Automatic tracking of every AudicLabs API call (credits, duration, service, request ID) with a monthly credit quota that blocks new uploads when exceeded.
- **Export & Public Sharing:** Instant download in TXT, SRT, and DOCX formats, plus revocable read-only public sharing links.
- **Billing & Subscriptions:** Tiered plans (Starter, Team, Studio), per-minute / per-project invoice generation with GST tax calculation, and payment processing (UPI, Card, PayPal, NetBanking).

---

## 🎥 Demo & Walkthrough Videos

- **Project Execution Demo Video:** [Watch Project Execution Demo](PASTE_EXECUTION_VIDEO_LINK_HERE)
  - *Shows end-to-end workflow on real audio, error handling, live job updates, interactive transcription editor, and multi-format exports.*
- **Architecture & Codebase Walkthrough Video:** [Watch Codebase Walkthrough](PASTE_EXPLANATION_VIDEO_LINK_HERE)
  - *Detailed explanation of system architecture, multi-tenant RBAC, background job pipeline, and database schema.*

> ℹ️ *Note: Video files are hosted on cloud storage to ensure high streaming quality without exceeding repository size limits. Access is set to public view.*

---

## 2. System Architecture

```text
                     +---------------------------------------+
                     |    Web Client (React 18 + Vite SPA)   |
                     |         http://localhost:8080         |
                     +-------------------+-------------------+
                                         |
                                         | Reverse Proxy / Nginx
                                         v
                     +---------------------------------------+
                     |         Nginx Gateway (Port 8080)     |
                     +---------+-------------------+---------+
                               |                   |
                     /api, /ws |                   | /
                               v                   v
                     +-------------------+   +---------------+
                     | FastAPI Backend   |   | Static Web UI |
                     | (Uvicorn :8000)   |   | (Nginx :80)   |
                     +---------+---------+   +---------------+
                               |
       +-----------------------+-----------------------+
       |                       |                       |
       v                       v                       v
+--------------+        +--------------+        +--------------+
|  PostgreSQL  |        |  Redis Queue |        | MinIO / S3   |
|   Database   |        |  & PubSub    |        | Object Store |
+--------------+        +-------+------+        +--------------+
                                |
                                v
                     +-------------------+
                     | Background Worker |
                     | (Python Worker)   |
                     +---------+---------+
                               |
                               | HTTPS with X-Request-Id & Retry-After
                               v
                     +---------------------------------------+
                     |        AudicLabs Speech AI APIs       |
                     |    - Speech to Text (file)            |
                     |    - Speaker Diarization              |
                     |    - Noise Suppressor                 |
                     |    - Languages & Voices Lookups       |
                     +---------------------------------------+
```

---

## 3. Quick Start & Setup

### Option A: Running with Docker Compose (Recommended)

1. **Clone repository & prepare environment:**
   ```bash
   cp .env.example .env
   # Add your AUDICLABS_API_KEY into .env
   ```

2. **Launch all services:**
   ```bash
   docker compose up --build
   ```

3. **Access the application:**
   - Web Portal: [http://localhost:8080](http://localhost:8080)
   - API Docs: [http://localhost:8080/api/docs](http://localhost:8080/api/docs)
   - Health check: [http://localhost:8080/health](http://localhost:8080/health)

---

### Option B: Running Locally for Development

#### Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
# Set DATABASE_URL to PostgreSQL or SQLite:
# (Defaults to sqlite:///./hub.db for zero-config local run)
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 4. Default Seed Accounts

The platform automatically seeds an initial organization (**Acme Media**) with sample accounts for all 7 RBAC roles. All accounts use password: `DemoPass123!`

| Role | Email | Assessment Role | Permissions Summary |
|---|---|---|---|
| **Super Admin** | `superadmin@transcribehub.local` | Super Admin | Global administration across all tenants |
| **Organization Admin** | `admin@acme.local` | **Owner** | Full workspace management, member invites, quota setting, billing |
| **Project Manager** | `pm@acme.local` | **Editor** | Create projects, assign transcribers, set deadlines, upload media |
| **Transcriber** | `transcriber@acme.local` | **Editor** | Upload media, edit transcripts, insert timestamps, tag speakers |
| **Reviewer / Editor** | `reviewer@acme.local` | **Editor** | Quality assurance, accuracy scoring, approve/request revisions |
| **Client** | `client@acme.local` | **Viewer** | Upload recordings, monitor progress, request revisions, view invoices |
| **Billing Manager** | `billing@acme.local` | **Editor** | Subscription plans, invoice generation, tax & payment processing |

---

## 5. Running the Automated Tests

The test suite covers authentication, role-based access control (RBAC), and the background upload/transcription pipeline:

```bash
cd backend
.\.venv\Scripts\pytest.exe -v
```

Expected output:
```text
tests/test_auth_roles_upload.py::test_register_login_and_me PASSED
tests/test_auth_roles_upload.py::test_roles_viewer_cannot_upload PASSED
tests/test_auth_roles_upload.py::test_upload_pipeline_mocked PASSED
3 passed in 14.6s
```

---

## 6. Sample Inputs & Outputs

The committed `samples/` directory contains real test data and exported results:
- `samples/sample_interview.wav`: Valid 16-bit 16kHz PCM audio with dual-speaker speech dialogue.
- `samples/output_transcript.txt`: Plaintext transcript with speaker turns and timestamps.
- `samples/output_transcript.srt`: Formatted SubRip subtitles with precise millisecond sync.
- `samples/output_transcript.docx`: Word document with formatted headings and bold speaker turns.
- `samples/output_diarization.json`: Raw diarization segments and speaker mappings.
- `samples/output_api_response.json`: Full AudicLabs STT engine payload including processing stats.

---

## 7. Assumptions & Design Decisions

1. **AudicLabs API Credentials & Graceful Emulation:**
   The `AUDICLABS_API_KEY` is kept strictly server-side and is never exposed to browser client code. When no API key is configured or during local development/offline reviews, the system automatically engages an intelligent emulation fallback (`audiclabs_demo_fallback=True`) that simulates realistic diarization, noise reduction, and timestamps so that all 17 platform modules can be explored without consuming third-party API credits.
2. **Local Storage Fallback:**
   If MinIO / AWS S3 or Redis are not reachable during local workstation development, the application transparently falls back to local filesystem storage (`data/uploads`) and inline asynchronous task execution, ensuring 100% functionality without requiring external cloud infrastructure.
3. **Password Security:**
   Standard native `bcrypt` is used directly for salted password hashing, completely bypassing legacy `passlib` version incompatibilities.
4. **Timezone Standardization:**
   All timestamp records across projects, reviews, audits, and SLA deadlines are normalized to UTC to prevent offset-naive/offset-aware datetime errors across database dialects.

---

## 8. Known Limitations

- Real-time live audio streaming (WebSocket `/v1/stt/stream`) is represented in the editor via batch uploads and live peer synchronization.
- Foreign language translation relies on client-side localization or external translation providers as specified in the AudicLabs API reference.
