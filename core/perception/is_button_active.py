from __future__ import annotations
from dataclasses import dataclass
import os, glob
import numpy as np
from PIL import Image
import cv2
from sklearn.linear_model import LogisticRegression
import joblib
from typing import List, Tuple
import os, glob
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report

from sklearn.linear_model import LogisticRegression
import joblib

# -----------------
# Feature extraction
# -----------------

def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def _hsv_feats(bgr: np.ndarray) -> np.ndarray:
    """HSV summary + hue histogram with color-mask."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[...,0].astype(np.float32), hsv[...,1].astype(np.float32), hsv[...,2].astype(np.float32)

    # mask: "colored" pixels (ignore gray/white text/border)
    colored = (S >= 60) & (V >= 70)
    total = max(1, int(np.count_nonzero(colored)))

    # hue histogram (on colored)
    h_col = H[colored]
    if h_col.size == 0:
        hue_hist = np.zeros(12, dtype=np.float32)
    else:
        hue_hist, _ = np.histogram(h_col, bins=12, range=(0,180), density=False)
        hue_hist = (hue_hist / float(h_col.size)).astype(np.float32)

    # purple-ish fraction (OpenCV H≈140–165 for “purple” used by ON state)
    purple_mask = colored & (H >= 135) & (H <= 170)
    frac_purple = float(np.count_nonzero(purple_mask)) / float(colored.size)

    # saturation/value stats on colored pixels
    if h_col.size == 0:
        s_mean = s_std = v_mean = v_std = 0.0
    else:
        s_mean, s_std = float(S[colored].mean()), float(S[colored].std())
        v_mean, v_std = float(V[colored].mean()), float(V[colored].std())

    frac_high_sat = float(np.count_nonzero((S >= 100) & colored)) / float(colored.size)
    frac_high_val = float(np.count_nonzero((V >= 120) & colored)) / float(colored.size)

    return np.concatenate([
        hue_hist,                              # 12
        np.array([s_mean, s_std, v_mean, v_std,
                  frac_purple, frac_high_sat, frac_high_val], dtype=np.float32)  # 7
    ])  # total = 19 dims

def _lab_feats(bgr: np.ndarray) -> np.ndarray:
    """LAB mean channels; 'a' tends to be higher for magenta/purple."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L, A, B = lab[...,0].astype(np.float32), lab[...,1].astype(np.float32), lab[...,2].astype(np.float32)
    return np.array([L.mean(), L.std(), A.mean(), A.std(), B.mean(), B.std()], dtype=np.float32)  # 6 dims

def featurize(img: Image.Image) -> np.ndarray:
    bgr = _pil_to_bgr(img)
    # trim a tiny border to reduce background influence
    h, w = bgr.shape[:2]
    pad = max(1, int(0.03 * min(h,w)))
    bgr = bgr[pad:h-pad, pad:w-pad].copy() if h > 2*pad and w > 2*pad else bgr
    return np.concatenate([_hsv_feats(bgr), _lab_feats(bgr)])  # 25 dims


# -----------------
# Model wrapper
# -----------------

@dataclass
class ActiveButtonClassifier:
    model: LogisticRegression

    def predict_proba(self, img: Image.Image) -> float:
        X = featurize(img).reshape(1, -1)
        # proba for class "1" → ON
        return float(self.model.predict_proba(X)[0, 1])

    def predict(self, img: Image.Image, threshold: float = 0.5) -> bool:
        return self.predict_proba(img) >= threshold

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: str) -> "ActiveButtonClassifier":
        model = joblib.load(path)
        return cls(model=model)


def _load_labeled_images(data_dir: str) -> Tuple[List[Image.Image], List[int]]:
    """
    Expects one of the following:
      data_dir/on/*.png, data_dir/off/*.png
      or mixed folder with filenames ending in _on.png / _off.png.
    Returns (images, labels) with label=1 for ON, 0 for OFF.
    """
    imgs, ys = [], []

    on_globs  = glob.glob(os.path.join(data_dir, "on", "*.*"))
    off_globs = glob.glob(os.path.join(data_dir, "off", "*.*"))

    if not on_globs and not off_globs:
        # fallback to suffix-based in a single folder
        files = glob.glob(os.path.join(data_dir, "*.*"))
        for p in files:
            low = os.path.basename(p).lower()
            if low.endswith("_on.png") or low.endswith("_on.jpg") or "_on" in low:
                imgs.append(Image.open(p).convert("RGB")); ys.append(1)
            elif low.endswith("_off.png") or low.endswith("_off.jpg") or "_off" in low:
                imgs.append(Image.open(p).convert("RGB")); ys.append(0)
    else:
        for p in on_globs:
            imgs.append(Image.open(p).convert("RGB")); ys.append(1)
        for p in off_globs:
            imgs.append(Image.open(p).convert("RGB")); ys.append(0)

    return imgs, ys

def train_active_button_model(
    data_dir: str,
    out_path: str = "models/active_button_clf.joblib",
    C: float = 2.0,
    max_iter: int = 200,
    cv_folds: int = 5
) -> ActiveButtonClassifier:
    """
    Trains a tiny logistic regression. With very few samples, CV will be noisy,
    but good enough to sanity-check.
    """
    imgs, ys = _load_labeled_images(data_dir)
    if len(imgs) < 2:
        raise RuntimeError(f"Need at least 2 labeled images in '{data_dir}'")

    X = np.stack([featurize(im) for im in imgs], axis=0)
    y = np.array(ys, dtype=np.int64)

    clf = LogisticRegression(C=C, max_iter=max_iter, solver="liblinear")
    if len(np.unique(y)) == 2 and len(y) >= cv_folds:
        skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
        scores = cross_val_score(clf, X, y, cv=skf, scoring="accuracy")
        print(f"[CV] accuracy: {scores.mean():.3f} ± {scores.std():.3f}")
    else:
        print("[CV] skipped (too few samples)")

    clf.fit(X, y)
    print("[train] finished. Train accuracy:", clf.score(X, y))

    # quick report
    y_hat = clf.predict(X)
    print(classification_report(y, y_hat, target_names=["OFF","ON"]))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    joblib.dump(clf, out_path)
    print(f"[save] model → {out_path}")

    return ActiveButtonClassifier(model=clf)
