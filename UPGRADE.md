# MuleTrace-IN v3 — Upgrade Your Live App (5 minutes)

v3 = 1,000,904 transactions · 27,000 accounts · 32 features ·
calibrated against real 2026 statistics (NPCI ticket size, I4C mule counts,
Nuh/Jamtara hotspots, CFCFRMS bank concentration) · adds behavioural
biometrics, SIM/identity layer, drift monitor, PU-learning, adversarial
stress test, and a two-stage real-time cascade.

## Update your existing Streamlit deployment
1. In your GitHub repo, REPLACE `streamlit_app.py` with this folder's version
   (delete old → Upload files → this streamlit_app.py)
2. Open the repo's `data/` folder → delete `transactions.parquet` →
   upload ALL FIVE files from this folder's `data/`:
   accounts.parquet, graph_edges.parquet, metrics.json,
   transactions_part1.parquet, transactions_part2.parquet
   (each < 25 MB, so GitHub web upload works)
3. Streamlit auto-redeploys in ~2 min. Done.

## What's new in the UI
- Investigate page: 4 new scorecard rows (session length, paste behaviour,
  SIM age, activity shift)
- Model Analytics: "v3 production upgrades" panel — calibration Brier,
  PU hidden-mule capture, adversarial evasion curve with structural floor,
  drift-monitor PSI chart, cascade latency

## Headline numbers (30% held-out test, threshold 0.5)
- Ensemble (calibrated): AUC 1.00 · precision 0.994 · recall 0.994
- Precision at REAL 0.5% prevalence: 0.951  ← quote this to the jury
- Calibration: Brier 0.0113 → 0.0003
- PU test: 100% of hidden mules surface in top-5% ranking
- Adversarial: full behaviour evasion → structural models still catch 90.4%
- Cascade: 0.6 µs/account stage-1, 8% escalation, recall preserved at 0.994
- INTERCEPTION: 97.65% of suspicious value stopped BEFORE settlement
  (₹72.5 Cr of ₹74.3 Cr), benign friction 1.84%, 10.8 µs/decision,
  92,862 txns/sec — includes beneficiary-side inward-credit holds and
  RBI-style cooling for first-time high-value payees
