# JARVIS — Android + LiveKit + Gemini starter

A cloud-first voice assistant starter: the Android app captures and publishes microphone audio through LiveKit/WebRTC; the worker runs a streaming STT → Gemini Flash LLM → streaming Gemini TTS pipeline. FastAPI issues short-lived scoped room tokens, dispatches the worker, persists conversation turns in PostgreSQL, stores semantic memories in pgvector, and brokers in-app confirmations for Home Assistant automations.

> **Honest status:** this is a runnable starter scaffold, not a security-audited commercial release. The Python backend passed syntax and schema tests in this environment, but the Android client has not been Gradle-built against your specific Firebase/LiveKit/Home Assistant accounts here. Build, deploy, and test in a staging environment before connecting real devices. Model names and provider access can change; confirm model availability in your Google AI Studio and LiveKit projects.

## Folder structure

```text
JARVIS/
├── README.md
├── .env.example
├── .gitignore
├── Dockerfile.api
├── Dockerfile.agent
├── docker-compose.yml
├── android/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   ├── gradle.properties
│   ├── local.properties.example
│   └── app/
│       ├── build.gradle.kts
│       └── src/main/
│           ├── AndroidManifest.xml
│           ├── java/com/jarvis/assistant/
│           │   ├── MainActivity.kt
│           │   └── JarvisViewModel.kt
│           └── res/
│               ├── values/styles.xml
│               └── xml/network_security_config.xml
└── backend/
    ├── requirements.txt
    ├── agent.py
    ├── app/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── database.py
    │   ├── embeddings.py
    │   ├── home_assistant.py
    │   ├── main.py
    │   ├── api_schemas.py
    │   ├── security.py
    │   └── schemas/
    │       ├── __init__.py
    │       └── tool_schemas.json
    └── tests/test_tool_schemas.py
```

## Request and voice flow

1. Android asks `POST /api/session` for a room-scoped 10-minute LiveKit token.
2. The API authenticates the Firebase ID token in production, dispatches `jarvis-agent` with the verified user ID, and returns the LiveKit URL/token.
3. Android publishes microphone audio over WebRTC. LiveKit Agents use configurable streaming transcription (default: `speechmatics/linden-1` via LiveKit Inference), Gemini Flash by default, and Gemini TTS for spoken output. Linden-1 lists Bengali (`bn`) and Hindi (`hi`) support; model availability depends on your LiveKit plan. citeturn473561search2turn473561search3 The LiveKit voice pipeline supports interruption while speaking.
4. User and assistant text is stored in PostgreSQL. User turns can also be embedded with `gemini-embedding-001` and recalled through pgvector for long-term memory.
5. Device tools validate every entity against configured allowlists. Calls return the common structure `{ "ok": boolean, "data": ..., "error": ... }`.
6. Light and smart-plug changes execute directly. Automations create a short-lived pending confirmation; the Android app polls and must receive a tap on **Confirm** before the automation service is called.

## 1. Required accounts/configuration

- LiveKit Cloud project (server URL, API key, API secret, named worker `jarvis-agent`).
- LiveKit Cloud with Inference access to `google/gemini-3.6-flash` and `google/gemini-3.1-pro-preview`; a Google AI Studio API key for Gemini TTS and embeddings. The default TTS model is `gemini-3.8-flash-tts`, and embeddings use `gemini-embedding-001`; confirm provider availability before deployment. citeturn384743view0turn473561search0
- PostgreSQL with the **pgvector** extension available.
- Home Assistant reachable from the cloud backend, if device control is enabled.
- Firebase project with **Anonymous sign-in enabled** for the starter client, and a Firebase Admin service account for backend ID-token verification in production.

The worker uses LiveKit Inference for streaming transcription and the Gemini Flash/Pro LLMs, so its LiveKit account must have those models enabled/available. `speechmatics/linden-1` lists Bengali and Hindi support. To change provider, set `STT_MODEL` to another supported streaming STT model ID. The Gemini Flash/Pro LLM models are invoked through LiveKit Inference, while Gemini TTS and embeddings use `GOOGLE_API_KEY`. The current Gemini TTS model name and LiveKit plugin usage are documented here: citeturn473561search0

## 2. Local backend setup

From the repository root:

```bash
cp .env.example .env
# Edit .env with your actual LiveKit, Google, and (optionally) Home Assistant values.
docker compose up --build
```

`docker-compose.yml` starts PostgreSQL/pgvector, FastAPI on port 8000, and the LiveKit worker. Open `http://localhost:8000/healthz` and `http://localhost:8000/docs`. On first boot the API enables pgvector and creates the starter tables.

Alternatively run Python services directly after starting a pgvector PostgreSQL instance:

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# In another terminal, with the same environment variables:
python agent.py dev
```

Use `AUTH_MODE=development` only on your own machine. It bypasses Firebase authentication and is intentionally rejected whenever `APP_ENV=production`.

## 3. Configure Home Assistant safely

Create a long-lived access token in your Home Assistant profile and put it only in the backend secret store as `HA_LONG_LIVED_TOKEN`. Do not put this token in Android, commit it to Git, or return it from any endpoint. Prefer a private network/VPN or an access-controlled tunnel between the backend and Home Assistant.

Set exact entity allowlists in `.env` as valid JSON arrays, for example:

```dotenv
HA_ALLOWED_LIGHTS=["light.living_room","light.bedside_lamp"]
HA_ALLOWED_SWITCHES=["switch.desk_plug"]
HA_ALLOWED_AUTOMATIONS=["automation.goodnight"]
HA_READONLY_ENTITY_IDS=["sensor.living_room_temperature","binary_sensor.front_door"]
```

An empty list blocks that category. Never allow an automation unless you have reviewed every side effect it can trigger. `automation.trigger` is always confirmed in the app. This starter exposes **no** arbitrary service tool and no unlock, message-send, delete, or payment tool. Do not make the Home Assistant host publicly accessible just for this integration.

All tool input schemas and the common structured result schema are in `backend/app/schemas/tool_schemas.json`.

## 4. Android setup/build

1. Open `android/` in Android Studio (JDK 17; Android SDK 35).
2. Copy `android/local.properties.example` to `android/local.properties` and set `JARVIS_API_BASE_URL` to your backend HTTPS URL. For the Android emulator calling a local API, the default `http://10.0.2.2:8000` is allowed by a narrow development-only network policy. Use HTTPS for real devices and production.
3. For production, create/register an Android app in Firebase. Enable Authentication → Sign-in method → **Anonymous**. Set `FIREBASE_API_KEY`, `FIREBASE_APPLICATION_ID`, and `FIREBASE_PROJECT_ID` in `local.properties`. These are Firebase client configuration values, not backend admin credentials. Never add a Firebase service-account JSON file to the Android project.
4. Run the app on an Android device/emulator, grant microphone permission, and tap **Connect to JARVIS**. Incoming agent audio is played by LiveKit; use **Mute microphone** or **Disconnect** to stop publishing audio.
5. The wake-word area is a labelled placeholder; no background wake-word detection is implemented. Keep the app open for this MVP.

For a public deployment, configure Firebase App Check, usage quotas, and abuse monitoring before allowing anonymous sessions. Consider upgrading from anonymous auth to a provider-based sign-in when you have user accounts.

## 5. Railway deployment (recommended path)

Create a Railway project with **three services**:

### PostgreSQL

Add a PostgreSQL service that supports `CREATE EXTENSION vector`. Confirm `CREATE EXTENSION IF NOT EXISTS vector;` works before deploying. Set the API and worker `DATABASE_URL` to the provider's private connection string, converted to `postgresql+asyncpg://...` if needed.

### API service

- Deploy from this repo, Dockerfile path: `Dockerfile.api`.
- Add all required environment variables from `.env.example` in Railway Variables.
- Set `APP_ENV=production`, `AUTH_MODE=firebase`, and `FIREBASE_PROJECT_ID`.
- Paste the Firebase Admin service account JSON into `FIREBASE_SERVICE_ACCOUNT_JSON` as a single-line secret value.
- Set `DATABASE_URL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME`, `GOOGLE_API_KEY`, and the HA credentials/allowlists as applicable.
- Generate an HTTPS domain. Test `/healthz`, then confirm `/api/session` without a valid Firebase token returns `401`.

### Agent worker service

- Deploy the same repo as a second service, Dockerfile path: `Dockerfile.agent`.
- Set the **same** `DATABASE_URL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME=jarvis-agent`, `GOOGLE_API_KEY`, Gemini model values, and HA secrets/allowlists.
- Deploy the worker and ensure it registers under the name `jarvis-agent`. The API explicitly dispatches this agent name. Do not expose any worker port publicly.

Set `JARVIS_API_BASE_URL` in Android `local.properties` to the API HTTPS domain. Firebase client config is compiled into the Android app; backend admin credentials never are.

## 6. Fly.io deployment alternative

Use the same Dockerfiles as separate Fly apps: `Dockerfile.api` for the HTTPS API and `Dockerfile.agent` as a private worker. Provision a PostgreSQL cluster that supports pgvector (or use a supported managed pgvector database), configure secrets with `fly secrets set KEY=value`, and expose only the API service. Run a single worker instance for the starter. Verify WebRTC networking/LiveKit connectivity from the worker and use managed secret storage; don't publish the worker or database ports publicly.

## 7. Environment variable template

All expected settings are documented in `.env.example`. Key groups:

- **Runtime/auth:** `APP_ENV`, `AUTH_MODE`, `APP_ALLOWED_ORIGINS`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`
- **Storage:** `DATABASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`
- **Voice/agent:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME`, `GOOGLE_API_KEY`, `STT_MODEL`, `GEMINI_FLASH_MODEL`, `GEMINI_COMPLEX_MODEL`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`
- **Home Assistant:** `HA_URL`, `HA_LONG_LIVED_TOKEN`, the four `HA_*` allowlists, `CONFIRMATION_TTL_SECONDS`

Never place `LIVEKIT_API_SECRET`, the HA token, Firebase Admin JSON, or Google API key in mobile code or Git history.

## 8. Security checklist before real use

- [ ] `APP_ENV=production` and `AUTH_MODE=firebase`; test that unauthenticated requests fail.
- [ ] Firebase ID token verification and App Check are enabled; add user identity, rate limits, quotas, and audit logs.
- [ ] API is HTTPS only; database and worker are private; CORS contains only expected web origins.
- [ ] LiveKit tokens are room-scoped and short-lived; API secret is server-side only.
- [ ] Home Assistant token is server-side only; use least-privilege Home Assistant setup and a private route.
- [ ] All entity/automation allowlists are reviewed. Never add arbitrary service/domain execution to the model tool interface.
- [ ] Every automation request requires a fresh, expiring, user-bound in-app approval. Rejections/timeouts execute nothing.
- [ ] No exposed tools for door unlocks, message sending, deletion, or payments. Add separate, explicit, auditable confirmation workflows before ever implementing such actions.
- [ ] Add retention/deletion controls for transcripts and vectors, log redaction, database backups, and a privacy notice before general release.
- [ ] Test timeout, disconnect, duplicate confirmation, invalid entity, HA offline, expired Firebase token, and model-provider outage paths.
- [ ] Add automated dependency/security scanning and end-to-end tests; test with fake/sandbox Home Assistant entities first.

## 9. Seven-day MVP roadmap

| Day | Target |
|---|---|
| 1 | Create LiveKit/Google/Firebase projects; start pgvector; verify `/healthz` and authenticated token issuance. |
| 2 | Build Android UI; microphone permissions; connect/disconnect and two-way audio. |
| 3 | Tune streaming transcription, Flash response latency, TTS voice, and barge-in interruptions. |
| 4 | Add transcript persistence and per-user pgvector recall; test isolation across two test accounts. |
| 5 | Connect Home Assistant with one test light and one sensor; validate every allowlist/error path. |
| 6 | Add app confirmation for automations; run negative tests for expired/replayed approvals. |
| 7 | Deploy API + worker, run security checklist, monitor latency/costs, and record a demo. |

## 10. Tests and known limits

Run the included Python syntax and schema tests from the repository root:

```bash
python -m pip install pytest
pytest backend/tests
```

The Android wake-word feature is intentionally a placeholder. There is no offline LLM, background hotword service, arbitrary device control, full account-management UI, distributed rate limiter, App Check verification, or production-grade billing/quota dashboard. The first backend release provides API authentication hooks, allowlists, memory, and explicit confirmation; production review and real-account integration testing remain necessary.
