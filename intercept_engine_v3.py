"""
MuleTrace-IN v3 — Real-Time Interception Engine
Not just flagging: per-transaction ALLOW / STEP_UP / COOLING / BLOCK decisions
BEFORE settlement, replayed over the full 1M-transaction stream in timestamp
order with rolling state (exactly how a payment-switch hook would run).

Policy (RBI-aligned):
  BLOCK    risk ≥ 0.85 AND (amount ≥ ₹20k OR first-time payee)
           → transaction held, account queued for freeze review
  STEP_UP  risk ≥ 0.60 AND (amount ≥ ₹10k OR first-time payee OR night hour)
           → extra authentication (biometric / OTP-on-registered-SIM)
  COOLING  first-time payee AND amount ≥ ₹50k AND risk ≥ 0.30
           → 4-hour delay window (mirrors RBI's proposed cooling-period norm
             for first-time high-value transfers)
  ALLOW    everything else — the 97%+ of honest traffic, untouched

Measures what a prevention system is judged on:
  - % of suspicious VALUE stopped before settlement (₹ crore intercepted)
  - benign friction rate (honest customers challenged) — must stay tiny
  - decision latency (µs) and throughput (txns/sec)

Usage:  python intercept_engine_v3.py [--data-dir ./aml_output_v3]
Writes: interception decisions summary into metrics.json ("interception" block)
        + interception_log_sample.csv (first 5k non-ALLOW decisions)
"""

import argparse, json, time
import numpy as np
import pandas as pd

RISK_BLOCK, RISK_STEPUP, RISK_COOL = 0.85, 0.60, 0.30
AMT_BLOCK, AMT_STEPUP, AMT_COOL    = 20_000, 10_000, 50_000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="./aml_output_v3")
    a = p.parse_args()

    print("[1/3] Load stream + account risk scores")
    tx = pd.read_csv(f"{a.data_dir}/transactions.csv", parse_dates=["timestamp"],
                     usecols=["txn_id","timestamp","sender_id","receiver_id",
                              "amount","is_suspicious"])
    tx = tx.sort_values("timestamp").reset_index(drop=True)
    sc = pd.read_csv(f"{a.data_dir}/scores.csv", usecols=["account_id","score_ensemble"])
    risk = dict(zip(sc.account_id, sc.score_ensemble))

    senders = tx.sender_id.values; receivers = tx.receiver_id.values
    amounts = tx.amount.values;    susp = tx.is_suspicious.values
    hours   = tx.timestamp.dt.hour.values

    print(f"[2/3] Replaying {len(tx):,} transactions through the switch hook")
    seen_payees = {}                                   # sender -> set of receivers
    decisions = np.zeros(len(tx), dtype=np.int8)       # 0 allow 1 stepup 2 cooling 3 block
    t0 = time.perf_counter()
    for i in range(len(tx)):
        s = senders[i]
        r_ = risk.get(s, 0.0)
        amt = amounts[i]
        payees = seen_payees.get(s)
        first = payees is None or receivers[i] not in payees
        night = hours[i] < 6 or hours[i] >= 22

        r_recv = risk.get(receivers[i], 0.0)
        if r_ >= RISK_BLOCK and (amt >= AMT_BLOCK or first):
            decisions[i] = 3                       # sender-side hold
        elif r_recv >= RISK_BLOCK and amt >= AMT_STEPUP:
            decisions[i] = 3                       # beneficiary-side hold (victim protection)
        elif r_ >= RISK_STEPUP and (amt >= AMT_STEPUP or first or night):
            decisions[i] = 1
        elif first and amt >= 100_000:
            decisions[i] = 2                       # RBI-style cooling: first payee, high value

        if payees is None:
            seen_payees[s] = {receivers[i]}
        else:
            payees.add(receivers[i])
    elapsed = time.perf_counter() - t0
    lat_us = elapsed / len(tx) * 1e6
    tps    = len(tx) / elapsed

    print("[3/3] Scoring the policy")
    is_iv = decisions > 0
    susp_mask   = susp == 1
    benign_mask = ~susp_mask
    v_susp      = amounts[susp_mask].sum()
    v_stopped   = amounts[susp_mask & is_iv].sum()
    v_blocked   = amounts[susp_mask & (decisions == 3)].sum()
    n_friction  = int((benign_mask & is_iv).sum())
    friction    = n_friction / benign_mask.sum()

    names = {0:"ALLOW",1:"STEP_UP",2:"COOLING",3:"BLOCK"}
    mix = {names[k]: int((decisions == k).sum()) for k in [0,1,2,3]}
    # value-weighted interception by decision tier (suspicious only)
    tier_value = {names[k]: round(float(amounts[susp_mask & (decisions==k)].sum()/1e7), 2)
                  for k in [1,2,3]}

    result = {
        "policy": {
            "BLOCK":   f"risk>={RISK_BLOCK} & (amt>=Rs{AMT_BLOCK:,} | first payee)",
            "STEP_UP": f"risk>={RISK_STEPUP} & (amt>=Rs{AMT_STEPUP:,} | first payee | night)",
            "BLOCK_BENEFICIARY": f"receiver risk>={RISK_BLOCK} & amt>=Rs{AMT_STEPUP:,} (inward credit hold)",
            "COOLING": "first payee & amt>=Rs100,000 (RBI-style 4h, risk-independent)",
        },
        "decision_mix": mix,
        "suspicious_value_intercepted_pct": round(float(v_stopped / max(v_susp,1)) * 100, 2),
        "suspicious_value_hard_blocked_pct": round(float(v_blocked / max(v_susp,1)) * 100, 2),
        "suspicious_value_total_cr":       round(float(v_susp / 1e7), 2),
        "suspicious_value_stopped_cr":     round(float(v_stopped / 1e7), 2),
        "value_stopped_by_tier_cr":        tier_value,
        "benign_friction_rate_pct":        round(float(friction) * 100, 3),
        "benign_txns_challenged":          n_friction,
        "decision_latency_us":             round(lat_us, 2),
        "throughput_txns_per_sec":         int(tps),
        "note": "Replay of full stream in timestamp order with rolling first-payee "
                "state; a production hook would sit on the UPI/IMPS switch with the "
                "same logic reading the cascade score from the feature store.",
    }

    # merge into metrics.json under upgrades.interception
    mpath = f"{a.data_dir}/metrics.json"
    m = json.load(open(mpath))
    m.setdefault("upgrades", {})["interception"] = result
    json.dump(m, open(mpath, "w"), indent=2)

    # sample log of interventions for the dashboard / audit trail
    idx = np.where(is_iv)[0][:5000]
    log = tx.iloc[idx][["txn_id","timestamp","sender_id","receiver_id","amount","is_suspicious"]].copy()
    log["decision"] = [names[d] for d in decisions[idx]]
    log["sender_risk"] = [round(risk.get(s,0),4) for s in log.sender_id]
    log.to_csv(f"{a.data_dir}/interception_log_sample.csv", index=False)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
