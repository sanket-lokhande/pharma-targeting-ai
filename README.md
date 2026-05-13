# Pharma Targeting AI Web App

Complete AI-powered pharma commercial analytics application for targeting and segmentation.

## Tech Stack

- Frontend: React + TypeScript + Tailwind + Plotly
- Backend: FastAPI + pandas + numpy + scikit-learn + scipy
- File Processing: Excel `.xlsx` input/output
- Output: Multi-sheet Excel with scores, segmentation, comparison, and insights

## Folder Structure

```text
pharma-targeting-ai/
  backend/
    app/
      api/routes.py
      services/
        analytics.py
        comparison.py
        exporter.py
        insights.py
        segmentation.py
        storage.py
        validation.py
      schemas.py
      main.py
    requirements.txt
  frontend/
    src/
      components/
      services/api.ts
      types/index.ts
      App.tsx
      main.tsx
      styles.css
    package.json
  README.md
```

## Backend Setup (FastAPI)

1. Open terminal in `pharma-targeting-ai/backend`
2. Create and activate virtual environment
3. Install dependencies
4. Start API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

## Frontend Setup (React)

1. Open second terminal in `pharma-targeting-ai/frontend`
2. Install dependencies
3. Start dev server

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

## Core Workflow Implemented

1. Upload current Excel data and validate IDs + metric quality
2. Select metrics and assign weights (must total 100)
3. Normalize values and generate composite scores
4. Create deciles D1-D10
5. Segment via K-Means, Hierarchical, or Rule-Based tiers
6. Generate correlation, concentration curve, and distributions
7. Auto-generate insights, recommendations, validation notes
8. Optional previous-file upload + comparison metadata
9. Compute movement, new/missing HCPs, lost high-value, and segment shifts
10. Export full workbook with required sheets

## API Endpoints

- `POST /api/upload/current`
- `POST /api/upload/previous`
- `POST /api/analyze`
- `GET /api/export/{analysis_id}`
- `POST /api/configurations`
- `GET /api/configurations`
- `GET /health`

## Output Workbook Sheets

1. Raw Data with Scores
2. Segmentation Results
3. Correlation Matrix
4. Movement Analysis
5. New vs Missing HCPs
6. Summary Insights
7. Recommendations
8. Validation Notes

## Notes

- Backend currently uses in-memory storage for datasets/analyses/configurations.
- For production, replace with persistent storage (S3 + database) and authentication.
- Plotly charts include built-in image download in chart toolbar.
