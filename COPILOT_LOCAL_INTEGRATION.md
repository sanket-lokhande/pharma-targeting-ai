# Local Copilot Integration (No Hosting)

This option runs entirely on your PC and does **not** require hosting your website or backend publicly.

## Scope and limitation

- Works with GitHub Copilot in VS Code agent mode (local workspace access).
- Microsoft Copilot consumer app does not support directly loading arbitrary local Python plugins without a hosted connector path.

## What was added

- Local runner script: `backend/local_agent_runner.py`
- It asks relevant deciling and segmentation questions, then generates a formatted client-ready output workbook.
- Desktop system application with NLQ: `backend/desktop_copilot_nlq_app.py`
- One-click launcher: `Run_NLQ_Desktop_App.bat`

## How to use with Copilot in VS Code

1. Keep this workspace open in VS Code.
2. In Copilot Chat, attach your current period Excel file and run:

```text
Run the local deciling and segmentation agent using this file.
Use backend/local_agent_runner.py and ask me all required questions.
```

3. Copilot can run this command in terminal:

```powershell
Set-Location backend
"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "<path-to-current-file.xlsx>"
```

4. Answer the prompted questions for:
- selected metrics
- weights (sum = 100)
- normalization
- segmentation algorithm
- cluster count
- optional previous file comparison

5. Script outputs a client-ready workbook:
- default name: `client_ready_targeting_YYYYMMDD_HHMMSS.xlsx`

## System application mode (desktop NLQ)

1. Double-click `Run_NLQ_Desktop_App.bat`.
2. Select current file (and previous file if needed).
3. Enter your NLQ instruction, for example:
	- "Use all metrics, zscore normalization, hierarchical with 4 clusters, compare with previous period."
4. Click **Run NLQ Analysis**.
5. The app generates a formatted client-ready workbook locally.
6. Click **Copy Copilot Prompt** to send result summary into Copilot chat.

This gives a local "system app + Copilot" workflow with NLQ and no hosting.

## Direct command examples

Current only:

```powershell
Set-Location backend
"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "C:/data/current.xlsx"
```

Current + previous:

```powershell
Set-Location backend
"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "C:/data/current.xlsx" --previous "C:/data/previous.xlsx"
```

Custom output:

```powershell
Set-Location backend
"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "C:/data/current.xlsx" --output "C:/data/client_ready_output.xlsx"
```
