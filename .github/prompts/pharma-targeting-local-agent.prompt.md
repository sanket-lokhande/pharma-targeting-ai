---
mode: agent
description: Run local deciling and segmentation with interactive questions and client-ready output.
tools:
  - run_in_terminal
---
Use this workflow to run deciling and segmentation without hosting any web API.

Steps:
1. Ask user for the path to the current Excel file if not already provided.
2. Ask if previous-period comparison is required.
3. Run local runner from backend folder:
   - Current only:
     `"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "<current.xlsx>"`
   - Current + previous:
     `"C:/Program Files/Python310/python.exe" local_agent_runner.py --current "<current.xlsx>" --previous "<previous.xlsx>"`
4. Let the script ask relevant questions for metrics, weights, normalization, and segmentation settings.
5. Return the generated output path to user.
6. Summarize configuration used:
   - selected metrics
   - metric weights
   - normalization
   - segmentation algorithm
   - cluster count
