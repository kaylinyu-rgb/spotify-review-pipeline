#!/usr/bin/env python3
"""Compare human golden labels with saved model predictions (no model calls).

    python evals/golden_eval.py --labels evals/golden_labels.csv --run runs/full
    python evals/golden_eval.py --labels evals/golden_labels.csv --run runs/golden50   # dedicated golden run

Predictions are read from the run's saved enriched.jsonl.gz. Human labels are never model inputs:
the golden run/full run only ever sends review_text. Missing/quarantined predictions count as incorrect.
Sentiment tolerance is predeclared: |pred - human| <= 0.5 counts as agreement; MAE is also reported.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.config import TOPICS, INTENTS  # noqa: E402
from pipeline.records import read_jsonl  # noqa: E402

SENT_TOL = 0.5


def f1_table(pairs, labels):
    out = {}
    for lab in labels:
        tp = sum(a == lab and p == lab for a, p in pairs)
        sup = sum(a == lab for a, _ in pairs)
        pred = sum(p == lab for _, p in pairs)
        if sup or pred:
            out[lab] = {"support": sup, "predicted": pred, "precision": round(tp / pred, 3) if pred else None,
                        "recall": round(tp / sup, 3) if sup else None, "f1": round(2 * tp / (sup + pred), 3) if sup + pred else None}
    f1s = [v["f1"] for v in out.values() if v["support"]]
    return out, round(sum(f1s) / len(f1s), 3) if f1s else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(ROOT / "evals" / "golden_labels.csv"))
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=str(ROOT / "evals"))
    a = ap.parse_args()
    run = Path(a.run) if Path(a.run).is_absolute() else ROOT / a.run
    gold = list(csv.DictReader(open(a.labels, encoding="utf-8")))
    missing_labels = [g["review_id"] for g in gold if not (g["topic"] and g["intent"] and g["severity"])]
    if missing_labels:
        raise SystemExit(f"{len(missing_labels)} golden rows are not labeled yet (e.g. {missing_labels[:3]}). Finish labeling first.")
    ids = {g["review_id"] for g in gold}
    pred = {r["review_id"]: r for r in read_jsonl(run / "enriched.jsonl") if r["review_id"] in ids}
    cases, tot = [], Counter()
    pairs = defaultdict(list)
    conf = Counter()
    for g in gold:
        rid, text = g["review_id"], g["review_text"]
        p = pred.get(rid)
        ok = p is not None and p["status"] == "completed"
        alt = {x.strip() for x in (g.get("alt_topics") or "").split(",") if x.strip()}
        hs, hsent = int(g["severity"]), float(g["sentiment"])
        c = {"review_id": rid, "text": text[:200], "human_topic": g["topic"], "human_alt_topics": "|".join(sorted(alt)),
             "human_intent": g["intent"], "human_severity": hs, "human_sentiment": hsent, "human_needs_review": g.get("needs_review") == "true",
             "ambiguous": g.get("ambiguous") == "true", "pred_status": p["status"] if p else "missing"}
        if ok:
            c.update(pred_topic=p["topic"], pred_subtopic=p.get("x_subtopic"), pred_intent=p["intent"], pred_severity=p["severity"],
                     pred_sentiment=p["sentiment"], pred_quote=p["evidence_quote"], pred_needs_review=p["needs_review"],
                     pred_entities="|".join(p["entities"]))
            c["topic_ok"] = p["topic"] == g["topic"] or p["topic"] in alt
            c["topic_exact"] = p["topic"] == g["topic"]
            c["intent_ok"] = p["intent"] == g["intent"]
            c["severity_ok"] = p["severity"] == hs
            c["severity_abs_err"] = abs(p["severity"] - hs)
            c["sentiment_abs_err"] = round(abs(p["sentiment"] - hsent), 3)
            c["sentiment_ok"] = c["sentiment_abs_err"] <= SENT_TOL
            c["quote_is_substring"] = p["evidence_quote"] in text
            hum_ent = {x.strip().lower() for x in (g.get("entities") or "").split("|") if x.strip()}
            c["entities_not_in_text"] = "|".join(e for e in p["entities"] if e.lower() not in text.lower() and e.lower() not in hum_ent)
            c["needs_review_match"] = p["needs_review"] == c["human_needs_review"]
            pairs["topic"].append((g["topic"], p["topic"])); pairs["intent"].append((g["intent"], p["intent"]))
            pairs["severity"].append((str(hs), str(p["severity"])))
            conf[(g["topic"], p["topic"])] += 1
        else:
            for k in ("topic_ok", "topic_exact", "intent_ok", "severity_ok", "sentiment_ok", "quote_is_substring", "needs_review_match"):
                c[k] = False
            for f, h in (("topic", g["topic"]), ("intent", g["intent"]), ("severity", str(hs))):
                pairs[f].append((h, "<missing>"))
        c["all_three_ok"] = c["topic_ok"] and c["intent_ok"] and c["severity_ok"]
        for k in ("topic_ok", "topic_exact", "intent_ok", "severity_ok", "sentiment_ok", "quote_is_substring", "needs_review_match", "all_three_ok"):
            tot[k] += bool(c[k])
        if ok:
            tot["sev_err"] += c["severity_abs_err"]; tot["sent_err"] += c["sentiment_abs_err"]; tot["valid"] += 1
        tot["ambiguous"] += c["ambiguous"]
        cases.append(c)
    n = len(gold)
    topic_f1, topic_macro = f1_table(pairs["topic"], TOPICS)
    intent_f1, intent_macro = f1_table(pairs["intent"], INTENTS)
    res = {"n": n, "valid_predictions": tot["valid"], "ambiguous_cases": tot["ambiguous"], "run": run.name,
           "label_config": next((p["label_config"] for p in pred.values() if p.get("label_config")), None),
           "agreement": {"topic_accepting_alternatives": round(tot["topic_ok"] / n, 3), "topic_exact": round(tot["topic_exact"] / n, 3),
                         "intent": round(tot["intent_ok"] / n, 3), "severity_exact": round(tot["severity_ok"] / n, 3),
                         f"sentiment_within_{SENT_TOL}": round(tot["sentiment_ok"] / n, 3), "all_three": round(tot["all_three_ok"] / n, 3),
                         "needs_review_match": round(tot["needs_review_match"] / n, 3)},
           "severity_mae": round(tot["sev_err"] / tot["valid"], 3) if tot["valid"] else None,
           "sentiment_mae": round(tot["sent_err"] / tot["valid"], 3) if tot["valid"] else None,
           "quote_exact_substring_rate": round(tot["quote_is_substring"] / n, 3),
           "macro_f1": {"topic": topic_macro, "intent": intent_macro}, "per_topic": topic_f1, "per_intent": intent_f1,
           "topic_confusion": [{"human": h, "pred": p, "n": k} for (h, p), k in sorted(conf.items())],
           "note": "50 cases are a small diagnostic sample, not a population accuracy estimate. Missing predictions count as incorrect."}
    out = Path(a.out)
    (out / "golden_results.json").write_text(json.dumps(res, indent=2) + "\n")
    with (out / "golden_cases.csv").open("w", newline="", encoding="utf-8") as f:
        cols = sorted({k for c in cases for k in c}, key=lambda k: list(cases[0].keys()).index(k) if k in cases[0] else 99)
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(cases)
    dis = [c for c in cases if not c["all_three_ok"]]
    md = ["# Golden-set evaluation (50 human labels vs saved predictions)", "",
          f"Run `{run.name}`, label_config `{res['label_config']}`. Valid predictions {tot['valid']}/{n}; ambiguous (human-marked) {tot['ambiguous']}.", "",
          "| metric | value |", "|---|---|"] + [f"| {k} agreement | {v} |" for k, v in res["agreement"].items()] + [
          f"| severity MAE | {res['severity_mae']} |", f"| sentiment MAE | {res['sentiment_mae']} |",
          f"| evidence quote exact-substring rate | {res['quote_exact_substring_rate']} |",
          f"| topic macro-F1 | {topic_macro} |", f"| intent macro-F1 | {intent_macro} |", "",
          "## Topic confusion (human → predicted)", "", "| human | predicted | n |", "|---|---|---|"] + \
         [f"| {x['human']} | {x['pred']} | {x['n']} |" for x in res["topic_confusion"]] + \
         ["", f"## Disagreements ({len(dis)})", "", "| review_id | text | human t/i/s | model t/i/s | fields |", "|---|---|---|---|---|"] + \
         [f"| `{c['review_id'][:8]}` | {c['text'][:90].replace('|', '/')} | {c['human_topic']}/{c['human_intent']}/{c['human_severity']} | "
          f"{c.get('pred_topic', '-')}/{c.get('pred_intent', '-')}/{c.get('pred_severity', '-')} | "
          f"{','.join(k[:-3] for k in ('topic_ok', 'intent_ok', 'severity_ok') if not c[k])} |" for c in dis] + \
         ["", "## Error analysis (write by hand after reading the table)", "", "_TODO: group the disagreements by cause "
          "(rubric ambiguity, model error, human error, non-English text) and say what you changed or why you did not._", ""]
    (out / "golden_report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(res["agreement"], indent=1), "severity MAE", res["severity_mae"])
    print(f"wrote {out}/golden_results.json, golden_cases.csv, golden_report.md")


if __name__ == "__main__":
    main()
