# Microsoft Copilot Agent Setup (Windows PC)

This project can be connected as a custom agent action backend for Microsoft Copilot using Copilot Studio.

## What is implemented in this codebase

- Existing upload + analysis + export endpoints
- New guided questionnaire endpoint: `GET /api/agent/questionnaire/{dataset_id}`
- New one-step agent endpoint: `POST /api/agent/analyze-and-export`
- Client-ready formatted Excel export with styled headers, banded rows, filters, freeze panes, and auto-fit columns

## Important platform note

You cannot directly install a local FastAPI app as a plugin inside the consumer Copilot app without a hosted API.
You must expose this backend over HTTPS and connect it through Copilot Studio actions.

## Step 1: Run backend

From `pharma-targeting-ai/backend`:

```powershell
"C:/Program Files/Python310/python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Test:
- Health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/openapi.json`

## Step 2: Expose API publicly (for testing)

Use ngrok or equivalent:

```powershell
ngrok http 8000
```

Copy the generated HTTPS URL, for example:
`https://abc123.ngrok-free.app`

OpenAPI URL becomes:
`https://abc123.ngrok-free.app/openapi.json`

## Step 3: Create agent in Copilot Studio

1. Open Copilot Studio.
2. Create a new agent (or custom copilot).
3. Add an Action from OpenAPI.
4. Use the public OpenAPI URL from Step 2.
5. Import these operations:
   - `upload_current`
   - `upload_previous`
   - `get_agent_questionnaire`
   - `analyze_and_export`
   - `export_analysis`
6. Paste prompt from `copilot-agent/agent-instructions.md` into the agent instructions.

## Step 4: Configure auth and environment

- For local testing with ngrok, no auth can be used in a private test environment.
- For production, add authentication (Azure AD or API key gateway) and persistent storage.

## Step 5: Validate end-to-end behavior

In Copilot chat:
1. Upload current Excel file.
2. Agent should ask relevant questions (metrics, weights, normalization, algorithm, clusters).
3. Agent runs analysis and returns summary.
4. Agent gives export URL for formatted client-ready workbook.

## Recommended production upgrades

- Replace in-memory storage with database + blob storage.
- Add file size limits and stricter schema validation.
- Add tenant/user identity and audit logs.
- Host in Azure App Service or Azure Container Apps.
