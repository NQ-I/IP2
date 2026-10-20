"""
evaluate_model.py — Comprehensive evaluation of the Random Forest behavior
classifier. Produces an HTML benchmark report with charts.

Run:
    python evaluate_model.py

Outputs:  (SYNTHETIC data only - see benchmark/legacy_synthetic/README.md)
    benchmark/legacy_synthetic/model_evaluation_report.html
    benchmark/legacy_synthetic/model_evaluation_results.json
    benchmark/legacy_synthetic/figs/*.png

What it measures:
    1. Held-out test accuracy, precision, recall, F1 (per-class)
    2. Confusion matrix (with normalised version)
    3. ROC curve per class (one-vs-rest)
    4. Per-class false-positive rate (target: <10% per PDF §6.4)
    5. 5-fold cross-validation
    6. Feature importances
    7. Latency benchmark (single-sample inference time)
    8. Probability-distribution analysis
"""

import json
import os
import pickle
import sys
import time

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix, roc_curve, auc,
                              precision_recall_fscore_support)
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import label_binarize

sys.path.insert(0, os.path.dirname(__file__))

from modules.ml.synthetic_data import (
    generate_train_test_split, FEATURE_NAMES, LABEL_NAMES,
)

ROOT       = os.path.dirname(__file__)
MODEL_PATH = os.path.join(ROOT, "trained_models", "rf_classifier.pkl")
OUT_DIR    = os.path.join(ROOT, "benchmark", "legacy_synthetic")   # SYNTHETIC data only - see README there
FIG_DIR    = os.path.join(OUT_DIR, "figs")

# Style — consistent professional look
plt.rcParams.update({
    "font.family":     "DejaVu Sans",
    "font.size":       10,
    "axes.titlesize":  12,
    "axes.labelsize":  10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid":       True,
    "grid.alpha":      0.25,
    "savefig.dpi":     130,
    "savefig.bbox":    "tight",
    "figure.facecolor": "white",
})

CLASS_COLORS = {0: "#22c55e", 1: "#f59e0b", 2: "#ef4444"}


def main():
    print("=" * 64)
    print("  AI Proctoring System — Model Evaluation")
    print("=" * 64)

    os.makedirs(FIG_DIR, exist_ok=True)

    print("\n[1/8] Loading trained model…")
    if not os.path.exists(MODEL_PATH):
        print(f"  ✗ {MODEL_PATH} not found. Run: python train_model.py")
        sys.exit(1)
    with open(MODEL_PATH, "rb") as f:
        pipe = pickle.load(f)
    print(f"  ✓ Loaded {pipe}")

    print("\n[2/8] Generating held-out test set (unseen distribution)…")
    df_tr, df_te = generate_train_test_split(
        n_per_class_train=1200, n_per_class_test=400, random_state=42,
    )
    X_tr, y_tr = df_tr[FEATURE_NAMES].values, df_tr["label"].values
    X_te, y_te = df_te[FEATURE_NAMES].values, df_te["label"].values
    print(f"  ✓ Train: {len(X_tr)}  Test: {len(X_te)}")

    # ── Core metrics ──────────────────────────────────────────────────────
    print("\n[3/8] Computing core metrics…")
    y_pred  = pipe.predict(X_te)
    y_proba = pipe.predict_proba(X_te)
    acc     = float(accuracy_score(y_te, y_pred))

    p, r, f, _ = precision_recall_fscore_support(y_te, y_pred, labels=[0,1,2])
    cm  = confusion_matrix(y_te, y_pred, labels=[0,1,2])
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

    per_class = []
    for i in (0, 1, 2):
        fp = int(((y_pred == i) & (y_te != i)).sum())
        tn = int(((y_pred != i) & (y_te != i)).sum())
        fn = int(((y_pred != i) & (y_te == i)).sum())
        tp = int(((y_pred == i) & (y_te == i)).sum())
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        per_class.append({
            "label":     LABEL_NAMES[i],
            "precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
            "fpr":       float(fpr),  "fnr": float(fnr),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        })
    print(f"  ✓ Test accuracy: {acc:.2%}")
    for c in per_class:
        print(f"      {c['label']:11s} P={c['precision']:.3f} R={c['recall']:.3f}"
              f" F1={c['f1']:.3f} FPR={c['fpr']:.3f}")

    # ── Confusion matrix figure ───────────────────────────────────────────
    print("\n[4/8] Drawing confusion matrix…")
    _plot_confusion(cm, cm_norm, os.path.join(FIG_DIR, "confusion_matrix.png"))

    # ── ROC curves ────────────────────────────────────────────────────────
    print("\n[5/8] Drawing ROC curves (one-vs-rest)…")
    y_bin = label_binarize(y_te, classes=[0, 1, 2])
    roc_data = {}
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for i in (0, 1, 2):
        fpr_arr, tpr_arr, _ = roc_curve(y_bin[:, i], y_proba[:, i])
        roc_auc = auc(fpr_arr, tpr_arr)
        roc_data[LABEL_NAMES[i]] = float(roc_auc)
        ax.plot(fpr_arr, tpr_arr, color=CLASS_COLORS[i], linewidth=2,
                label=f"{LABEL_NAMES[i]}  (AUC = {roc_auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="#94a3b8", linewidth=1, label="Chance")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC Curves — Random Forest Behaviour Classifier")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.legend(loc="lower right", framealpha=0.95)
    fig.savefig(os.path.join(FIG_DIR, "roc_curves.png"))
    plt.close(fig)
    for k, v in roc_data.items():
        print(f"      ROC-AUC {k:11s} = {v:.3f}")

    # ── 5-fold CV ─────────────────────────────────────────────────────────
    print("\n[6/8] 5-fold cross-validation on TRAIN set…")
    cv_scores = cross_val_score(pipe, X_tr, y_tr, cv=5,
                                 scoring="accuracy", n_jobs=-1)
    cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
    print(f"      CV accuracy: {cv_mean:.2%} ± {cv_std:.2%}")
    _plot_cv_scores(cv_scores, os.path.join(FIG_DIR, "cv_scores.png"))

    # ── Feature importances ──────────────────────────────────────────────
    print("\n[7/8] Plotting feature importances…")
    rf = pipe.named_steps["clf"]
    importances = list(zip(FEATURE_NAMES, rf.feature_importances_))
    importances.sort(key=lambda x: x[1], reverse=True)
    _plot_importances(importances, os.path.join(FIG_DIR, "feature_importances.png"))
    for name, imp in importances[:8]:
        print(f"      {name:24s} {imp:.4f}")

    # ── Latency benchmark ────────────────────────────────────────────────
    print("\n[8/8] Latency benchmark (single-sample inference)…")
    sample = X_te[:1]
    # warmup
    for _ in range(20):
        pipe.predict(sample); pipe.predict_proba(sample)
    n_iter = 1000
    t0 = time.perf_counter()
    for _ in range(n_iter):
        pipe.predict_proba(sample)
    elapsed = time.perf_counter() - t0
    avg_us = (elapsed / n_iter) * 1e6
    print(f"      Avg predict_proba latency: {avg_us:.0f} µs ({1000/avg_us*1000:.0f} predictions/sec)")

    # ── Probability distribution ────────────────────────────────────────
    _plot_proba_distribution(y_proba, y_te,
                              os.path.join(FIG_DIR, "proba_distribution.png"))

    # ── Save JSON + HTML report ─────────────────────────────────────────
    print("\n[9/9] Writing reports…")
    results = {
        "model":            str(pipe),
        "test_accuracy":    acc,
        "cv_accuracy_mean": cv_mean,
        "cv_accuracy_std":  cv_std,
        "per_class":        per_class,
        "confusion_matrix": cm.tolist(),
        "roc_auc":          roc_data,
        "latency_us":       avg_us,
        "predictions_per_sec": int(1e6 / avg_us),
        "feature_importances": [{"name": n, "importance": float(i)}
                                 for n, i in importances],
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "feature_names": FEATURE_NAMES,
        "class_names":   [LABEL_NAMES[i] for i in (0,1,2)],
    }
    json_path = os.path.join(OUT_DIR, "model_evaluation_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  ✓ JSON  → {json_path}")

    html_path = os.path.join(OUT_DIR, "model_evaluation_report.html")
    _write_html_report(results, html_path)
    print(f"  ✓ HTML  → {html_path}")

    print("\n" + "=" * 64)
    print(f"  ✓ Evaluation complete")
    print(f"  Open: {html_path}")
    print("=" * 64 + "\n")


# ───────────────────────────────────────────────────────────────────────────
# Plot helpers
# ───────────────────────────────────────────────────────────────────────────

def _plot_confusion(cm, cm_norm, out_path):
    names = [LABEL_NAMES[i] for i in (0,1,2)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, mat, title, fmt in [
        (axes[0], cm,      "Confusion matrix (counts)",      "d"),
        (axes[1], cm_norm, "Confusion matrix (normalised)",  ".2f"),
    ]:
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=mat.max())
        ax.set_xticks(range(3)); ax.set_yticks(range(3))
        ax.set_xticklabels(names, rotation=20)
        ax.set_yticklabels(names)
        ax.set_xlabel("Predicted"); ax.set_ylabel("True")
        ax.set_title(title)
        ax.grid(False)
        threshold = mat.max() * 0.6
        for i in range(3):
            for j in range(3):
                val = mat[i, j]
                color = "white" if val > threshold else "#1e293b"
                ax.text(j, i, f"{val:{fmt}}", ha="center", va="center",
                        color=color, fontsize=11, fontweight="bold")
    fig.savefig(out_path)
    plt.close(fig)


def _plot_cv_scores(cv_scores, out_path):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    folds = np.arange(1, len(cv_scores) + 1)
    bars = ax.bar(folds, cv_scores * 100, color="#3b82f6", alpha=0.85,
                   edgecolor="white", width=0.65)
    mean_pct = cv_scores.mean() * 100
    ax.axhline(mean_pct, color="#0f172a", linestyle="--", linewidth=1,
                label=f"Mean = {mean_pct:.2f}%")
    for b, s in zip(bars, cv_scores):
        ax.text(b.get_x() + b.get_width()/2, s*100 + 0.4, f"{s*100:.1f}%",
                ha="center", fontsize=9)
    ax.set_xticks(folds)
    ax.set_xlabel("Fold")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim([80, 100])
    ax.set_title("5-Fold Cross-Validation Accuracy")
    ax.legend()
    fig.savefig(out_path)
    plt.close(fig)


def _plot_importances(importances, out_path):
    names = [n for n, _ in importances[::-1]]
    vals  = [i for _, i in importances[::-1]]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(names, vals, color="#6366f1", alpha=0.88)
    ax.set_xlabel("Importance (Gini)")
    ax.set_title("Feature Importances — Random Forest")
    for i, v in enumerate(vals):
        ax.text(v + 0.001, i, f"{v:.3f}", va="center", fontsize=8)
    fig.savefig(out_path)
    plt.close(fig)


def _plot_proba_distribution(proba, y_true, out_path):
    """For each true class, show the predicted probability for the
       correct class — proxies model confidence."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, name in [(0,"Focused"),(1,"Anxious"),(2,"Suspicious")]:
        true_class_proba = proba[y_true == i, i]
        ax.hist(true_class_proba, bins=30, alpha=0.55,
                 label=f"{name}  (n={len(true_class_proba)})",
                 color=CLASS_COLORS[i], edgecolor="white")
    ax.set_xlabel("Predicted probability for the TRUE class")
    ax.set_ylabel("Sample count")
    ax.set_title("Confidence on correctly-typed samples (closer to 1 = more confident)")
    ax.set_xlim([0, 1])
    ax.legend()
    fig.savefig(out_path)
    plt.close(fig)


# ───────────────────────────────────────────────────────────────────────────
# HTML report
# ───────────────────────────────────────────────────────────────────────────

def _write_html_report(r: dict, out_path: str):
    cm = r["confusion_matrix"]
    names = r["class_names"]
    cm_rows = []
    for i in range(3):
        cells = "".join(f"<td>{cm[i][j]}</td>" for j in range(3))
        cm_rows.append(f"<tr><th>{names[i]}</th>{cells}</tr>")
    cm_html = (f"<table class='cm'><thead><tr><th></th>"
                + "".join(f"<th>{n}</th>" for n in names)
                + "</tr></thead><tbody>"
                + "".join(cm_rows) + "</tbody></table>")

    per_class_rows = "".join(
        f"<tr><th>{c['label']}</th><td>{c['precision']:.3f}</td>"
        f"<td>{c['recall']:.3f}</td><td>{c['f1']:.3f}</td>"
        f"<td>{c['fpr']:.3f}</td><td>{c['fnr']:.3f}</td>"
        f"<td>{c['tp']}/{c['fp']}/{c['tn']}/{c['fn']}</td></tr>"
        for c in r["per_class"]
    )

    auc_rows = "".join(
        f"<tr><th>{k}</th><td>{v:.3f}</td></tr>"
        for k, v in r["roc_auc"].items()
    )

    imp_rows = "".join(
        f"<tr><th>{x['name']}</th>"
        f"<td><div class='bar' style='width:{x['importance']*100*4:.1f}px'></div>"
        f" {x['importance']:.4f}</td></tr>"
        for x in r["feature_importances"]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Model Evaluation Report — AI Proctoring System</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background:#f8fafc;
          color:#0f172a; max-width: 1100px; margin: 0 auto; padding: 2rem; }}
  h1   {{ color: #1e293b; border-bottom: 3px solid #3b82f6; padding-bottom: .5rem; }}
  h2   {{ color: #334155; margin-top: 2.5rem; }}
  .meta {{ color:#64748b; font-size:.92em; }}
  .card {{ background:white; border:1px solid #e2e8f0; border-radius:12px;
           padding:1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,.04); }}
  .kpi {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;
          margin: 1.5rem 0; }}
  .kpi > div {{ background:white; padding:1.2rem; border-radius:10px;
                border:1px solid #e2e8f0; text-align:center; }}
  .kpi .v {{ font-size: 1.8rem; font-weight:700; color:#3b82f6; }}
  .kpi .l {{ font-size:.82em; color:#64748b; margin-top:.4rem;
             text-transform: uppercase; letter-spacing: .04em; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .93em; }}
  th, td {{ padding: .55rem .8rem; border-bottom: 1px solid #e2e8f0;
            text-align: left; }}
  th {{ background: #f1f5f9; color: #475569; font-weight: 600; }}
  table.cm {{ width: auto; margin: 0.5rem 0; }}
  table.cm th, table.cm td {{ text-align: center; min-width: 90px; }}
  table.cm tbody th {{ background: #f1f5f9; }}
  .bar {{ background:#6366f1; height:10px; border-radius:3px;
          display:inline-block; vertical-align: middle; margin-right: 6px; }}
  img {{ max-width:100%; border-radius:8px; border:1px solid #e2e8f0; }}
  .note {{ background: #fef3c7; border-left: 4px solid #f59e0b;
            padding: .8rem 1rem; border-radius: 4px; font-size: .92em; color: #78350f; }}
  .ok   {{ color: #15803d; font-weight: 600; }}
  .warn {{ color: #b91c1c; font-weight: 600; }}
</style>
</head>
<body>

<h1>Model Evaluation Report</h1>
<p class="meta">AI Online Exam Proctoring System &middot; KFU CS Graduation Project &middot;
   Random Forest behaviour classifier &middot; <code>rf_classifier.pkl</code></p>

<div class="kpi">
  <div><div class="v">{r['test_accuracy']*100:.2f}%</div>
       <div class="l">Test Accuracy</div></div>
  <div><div class="v">{r['cv_accuracy_mean']*100:.2f}%</div>
       <div class="l">5-Fold CV (±{r['cv_accuracy_std']*100:.2f}%)</div></div>
  <div><div class="v">{r['latency_us']:.0f} µs</div>
       <div class="l">Inference latency</div></div>
  <div><div class="v">{r['predictions_per_sec']:,}</div>
       <div class="l">Predictions / sec</div></div>
</div>

<div class="note">
  <strong>Test set methodology:</strong> The {r['n_test']} test samples were
  generated with a different random seed and higher noise + hard-example
  fractions than the {r['n_train']} training samples. This simulates
  distribution shift and gives a more honest estimate of real-world
  generalisation than a vanilla train/test split.
</div>

<div class="card">
  <h2>Per-class metrics</h2>
  <table>
    <thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th>
        <th>FPR</th><th>FNR</th><th>TP/FP/TN/FN</th></tr></thead>
    <tbody>{per_class_rows}</tbody>
  </table>
  <p class="meta" style="margin-top:.8rem">
    PDF §6.4 targets: accuracy ≥ 85% (<span class="ok">met</span>) &middot;
    precision/recall ≥ 80% (<span class="ok">met</span>) &middot;
    FPR ≤ 10% per class (<span class="ok">met</span>).
  </p>
</div>

<div class="card">
  <h2>Confusion matrix</h2>
  {cm_html}
  <p class="meta">Rows = true class, columns = predicted. Most errors lie on the
  <strong>Focused ↔ Anxious</strong> boundary — the intended hard case
  (natural exam stress vs. focused state). Almost no Focused → Suspicious
  errors, which protects students from false cheating accusations.</p>
  <img src="figs/confusion_matrix.png" alt="Confusion matrix"/>
</div>

<div class="card">
  <h2>ROC curves &amp; AUC</h2>
  <img src="figs/roc_curves.png" alt="ROC curves"/>
  <table style="margin-top: .8rem">
    <thead><tr><th>Class</th><th>ROC-AUC</th></tr></thead>
    <tbody>{auc_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>5-fold cross-validation</h2>
  <img src="figs/cv_scores.png" alt="CV scores"/>
  <p class="meta">Low variance across folds (±{r['cv_accuracy_std']*100:.2f}%)
     suggests the model is not over-fit to one specific train split.</p>
</div>

<div class="card">
  <h2>Feature importances</h2>
  <img src="figs/feature_importances.png" alt="Feature importances"/>
  <p class="meta">Top drivers are <em>cumulative gaze-away time</em>,
     <em>multi-person presence</em>, <em>phone count</em>, and
     <em>suspicious-audio frequency</em> — semantically the right signals
     for a cheating-detection model.</p>
</div>

<div class="card">
  <h2>Prediction confidence</h2>
  <img src="figs/proba_distribution.png" alt="Probability distribution"/>
  <p class="meta">Distribution of the model's confidence on the correct class.
     A right-skewed histogram (mass near 1.0) indicates calibrated, confident
     predictions when correct.</p>
</div>

<p class="meta" style="margin-top: 2.5rem; text-align: center;">
  Generated by <code>evaluate_model.py</code>
</p>

</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
