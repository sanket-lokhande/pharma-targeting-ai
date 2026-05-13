# Deploying to Streamlit Community Cloud (Free)

## 1. Local test
```
"C:\Program Files\Python310\python.exe" -m pip install streamlit==1.39.0
Run_Streamlit_App.bat
```
App opens at http://localhost:8501

## 2. Push to GitHub
The Streamlit deploy needs to see `streamlit_app.py` and `requirements.txt` in the same folder.

Recommended repo layout (from project root):
```
pharma-targeting-ai/
  backend/
    streamlit_app.py
    requirements.txt
    app/
      ...
    .streamlit/config.toml
```

```
cd pharma-targeting-ai
git init
git add .
git commit -m "Initial Streamlit app"
git branch -M main
git remote add origin https://github.com/<your-username>/pharma-targeting-ai.git
git push -u origin main
```

## 3. Deploy
1. Go to https://share.streamlit.io
2. Sign in with GitHub
3. Click **New app**
4. Pick the repo, branch `main`
5. **Main file path:** `backend/streamlit_app.py`
6. Click **Deploy**

Free tier gives you a public URL like `https://<app-name>.streamlit.app`, 1 GB RAM, no credit card.

## Notes
- Public repos = free. Private repos need a paid Streamlit plan; use Hugging Face Spaces instead if you need private free hosting.
- Uploaded Excel files stay in the user's session (not persisted on disk).
- For larger workloads, switch to Hugging Face Spaces (16 GB RAM free).
