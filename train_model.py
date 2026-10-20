"""
train_model.py — Train and save the Random Forest behavior classifier.

Run once before starting the server:
    python train_model.py

The model is saved to trained_models/rf_classifier.pkl and is loaded
automatically by BehaviorClassifier on startup.

The training pipeline:
  1. Generate train + held-out test sets using realistic synthetic data
     (overlapping class distributions, hard examples, label noise).
  2. Train a Random Forest (200 trees, depth 14) inside a sklearn Pipeline
     with StandardScaler.
  3. Evaluate on the held-out test set (drawn from a DIFFERENT seed with
     more noise — so it represents data the model has not seen).
  4. Report 5-fold cross-validation, confusion matrix, per-class metrics,
     and top feature importances.
"""

import os
import pickle
import sys

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

sys.path.insert(0, os.path.dirname(__file__))

from modules.ml.synthetic_data import (
    generate_train_test_split, FEATURE_NAMES, LABEL_NAMES,
)

SAVE_PATH = os.path.join(os.path.dirname(__file__),
                         "trained_models", "rf_classifier.pkl")


def train(n_per_class_train: int = 1200, n_per_class_test: int = 350):
    print("=" * 64)
    print("  AI Proctoring System — Random Forest Training")
    print("  KFU CS Graduation Project 2026")
    print("=" * 64)

    os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)

    print("\n[1/5] Generating synthetic behavioural dataset")
    print("      (realistic overlap, hard examples, 5% label noise)…")
    df_tr, df_te = generate_train_test_split(
        n_per_class_train=n_per_class_train,
        n_per_class_test =n_per_class_test,
        random_state     =42,
    )
    print(f"      Train: {df_tr.shape[0]:>5} rows  ({df_tr['label'].value_counts().to_dict()})")
    print(f"      Test:  {df_te.shape[0]:>5} rows  ({df_te['label'].value_counts().to_dict()})")
    print(f"      Test set drawn from a DIFFERENT RNG seed with MORE noise"
          f" → represents unseen distribution shift.")

    X_tr, y_tr = df_tr[FEATURE_NAMES].values, df_tr["label"].values
    X_te, y_te = df_te[FEATURE_NAMES].values, df_te["label"].values

    print("\n[2/5] Training Random Forest (200 trees, depth 14)…")
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators       = 200,
            max_depth          = 14,
            min_samples_split  = 4,
            min_samples_leaf   = 2,
            max_features       = "sqrt",
            class_weight       = "balanced",
            random_state       = 42,
            n_jobs             = -1,
        )),
    ])
    pipeline.fit(X_tr, y_tr)
    print("      ✓ Training complete")

    print("\n[3/5] Evaluating on held-out test set…")
    y_pred = pipeline.predict(X_te)
    acc    = accuracy_score(y_te, y_pred)
    print(f"      Test accuracy: {acc:.2%}")

    target_names = [LABEL_NAMES[i] for i in sorted(LABEL_NAMES)]
    print("\n      Classification report:")
    print("      " + classification_report(y_te, y_pred,
            target_names=target_names, digits=3).replace("\n", "\n      "))

    print("      Confusion matrix:")
    cm = confusion_matrix(y_te, y_pred)
    header = f"{'':14}" + "".join(f"{n:>12}" for n in target_names)
    print(f"      {header}")
    for i, row in enumerate(cm):
        print(f"      {target_names[i]:12}" + "".join(f"{v:>12}" for v in row))

    print("\n[4/5] 5-fold cross-validation on training set…")
    cv = cross_val_score(pipeline, X_tr, y_tr, cv=5,
                         scoring="accuracy", n_jobs=-1)
    print(f"      CV accuracy: {cv.mean():.2%} ± {cv.std():.2%}")

    # Feature importances
    rf = pipeline.named_steps["clf"]
    feat_imp = sorted(zip(FEATURE_NAMES, rf.feature_importances_),
                      key=lambda x: x[1], reverse=True)
    print("\n      Top 8 feature importances:")
    for name, imp in feat_imp[:8]:
        bar = "█" * int(imp * 60)
        print(f"        {name:<24} {imp:.4f}  {bar}")

    print("\n[5/5] Saving model…")
    with open(SAVE_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"      ✓ Model saved → {SAVE_PATH}")
    print(f"      ✓ Model size: {os.path.getsize(SAVE_PATH) / 1024:.0f} KB")

    print("\n" + "=" * 64)
    print(f"  Training complete. Run:  python run.py")
    print(f"  Run full evaluation:     python evaluate_model.py")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    train()
