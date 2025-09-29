import cv2, numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import cv2 as cv
from core.perception.ocr.interface import OCRInterface
from core.utils.date_uma import score_date_like
from core.utils.geometry import xyxy_int

def preprocess_digits(
    pil_img: Image.Image,
    *,
    scale: int = 3,
    drop_top_frac: float = 0.35,   # hide turquoise header line (~top 35%)
    trim_right_frac: float = 0.12, # hide right gutter/badge to avoid spurious digits (e.g., your PWR→2034)
    dilate_iters: int = 1,
    erode_iters: int = 0,
    focus_largest_cc: bool = False # optional: crop to largest connected component in the binarized image
):
    """
    Returns (final_pil, steps_dict) where steps_dict has intermediate arrays for plotting.
    """
    steps = {}
    bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR); steps["orig"] = bgr

    # 1) Nearest-neighbor upscale (pixel fonts like this prefer NN)
    h, w = bgr.shape[:2]
    up = cv2.resize(bgr, (w*scale, h*scale), interpolation=cv2.INTER_NEAREST); steps["upscaled"] = up

    # 2) Gray + gentle sharpening
    gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY); steps["gray"] = gray
    blur = cv2.GaussianBlur(gray, (0,0), 0.8)
    sharp = cv2.addWeighted(gray, 1.6, blur, -0.6, 0); steps["sharp"] = sharp

    # 3) Otsu binarization
    thr, bin_im = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    steps["otsu_thr"] = thr
    steps["bin_raw"] = bin_im.copy()

    # 4) Remove top turquoise strip & right gutter (column trims)
    H, W = bin_im.shape[:2]
    if drop_top_frac > 0:
        bin_im[: int(H*drop_top_frac), :] = 0
    if trim_right_frac > 0:
        bin_im[:, int(W*(1.0-trim_right_frac)) :] = 0
    steps["bin_trimmed"] = bin_im.copy()

    # 5) Thicken strokes a bit for tiny glyphs
    if dilate_iters:
        bin_im = cv2.dilate(bin_im, np.ones((2,2), np.uint8), iterations=dilate_iters)
    if erode_iters:
        bin_im = cv2.erode(bin_im, np.ones((2,2), np.uint8), iterations=erode_iters)
    steps["bin_morph"] = bin_im.copy()

    # 6) Optional: crop to largest CC (keeps digits, drops leftover UI)
    if focus_largest_cc:
        num, lbl, stats, _ = cv2.connectedComponentsWithStats(bin_im, connectivity=8)
        if num > 1:
            idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            x, y, ww, hh = stats[idx, :4]
            # small padding
            pad = max(2, int(min(W,H)*0.02))
            x1 = max(0, x-pad); y1 = max(0, y-pad)
            x2 = min(W, x+ww+pad); y2 = min(H, y+hh+pad)
            cc_crop = bin_im[y1:y2, x1:x2]
            steps["cc_bbox"] = (x1, y1, x2, y2)
            steps["bin_cc"] = cc_crop
            final_bin = cc_crop
        else:
            final_bin = bin_im
    else:
        final_bin = bin_im

    final_pil = Image.fromarray(final_bin)
    steps["final"] = final_bin
    return final_pil, steps

def show_steps_grid(steps, title=""):
    """Plot the important stages in one row."""
    figs = []
    keys = [("orig","Original"),
            ("upscaled","Upscaled (NN)"),
            ("sharp","Sharpened"),
            ("bin_raw",f"Binarized (Otsu={steps.get('otsu_thr','?')})"),
            ("bin_trimmed","Trimmed"),
            ("bin_morph","Morph"),
            ("bin_cc" if "bin_cc" in steps else "final","Final used")]
    plt.figure(figsize=(18,3))
    for i,(k,lab) in enumerate(keys,1):
        if k not in steps: continue
        ax = plt.subplot(1,len(keys),i)
        im = steps[k]
        if im.ndim==2: ax.imshow(im, cmap="gray")
        else: ax.imshow(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
        ax.set_title(lab, fontsize=10)
        ax.axis("off")
    if title: plt.suptitle(title)
    plt.show()

def tighten_to_pill(banner_img: Image.Image) -> tuple[int, int, int, int]:
    """
    Return a tight (x1,y1,x2,y2) bbox around the rounded date pill inside the banner.
    Works both on PC and mobile; ignores the upper "Training" title.
    Strategy:
      • Convert to HSV.
      • Threshold bright (V) & low-saturation (S) to catch the gray/white pill.
      • Keep components located in the lower 2/3 of the banner (where the pill lives).
      • Pick the widest such component; expand a few pixels.
      • Fallback to bottom 45% if nothing good is found.
    """
    W, H = banner_img.size
    hsv = cv.cvtColor(np.asarray(banner_img.convert("RGB")), cv.COLOR_RGB2HSV)
    Hc, Sc, Vc = cv.split(hsv)

    # Thresholds tuned to the UI palette (gray/white rounded chip)
    mask_v = cv.inRange(Vc, 170, 255)   # bright
    mask_s = cv.inRange(Sc, 0, 90)      # low saturation
    mask = cv.bitwise_and(mask_v, mask_s)

    # Ignore top third (title area)
    bottom_clip = int(H * 0.33)
    mask[:bottom_clip, :] = 0

    # Clean noise
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    n, labels, stats, _ = cv.connectedComponentsWithStats(mask, connectivity=4)
    best_idx, best_w = -1, -1
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if h < 10 or w < 40:
            continue
        # Prefer the widest blob in the bottom half
        if y > H * 0.35 and w > best_w:
            best_w = w
            best_idx = i

    if best_idx != -1:
        x, y, w, h, _ = stats[best_idx]
        pad = max(2, int(0.02 * W))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(W, x + w + pad)
        y2 = min(H, y + h + pad)
        return (x1, y1, x2, y2)

    # Fallback: bottom 45% slice, centered
    y1 = int(H * 0.52)
    y2 = min(H, int(H * 0.97))
    x1 = int(W * 0.02)
    x2 = int(W * 0.98)
    return (x1, y1, x2, y2)

def career_date_crop_box(game_img: Image.Image, turns_xyxy) -> tuple[int, int, int, int]:
    """
    Compute the OCR crop for the career-date pill **above** the Turns widget.
    Handles a variable-height top black band (often present on mobile).
    Returns (x1, y1, x2, y2) in image coordinates.
    """
    W, H = game_img.size
    x1, y1, x2, _ = xyxy_int(turns_xyxy)
    tw = max(1, x2 - x1)

    # Horizontal extent for the banner
    rx1 = x1
    rx2 = min(W, x1 + int(round(2.5 * tw)))
    ry2 = max(0, y1 - 2)

    # Detect any full-width black bar at the top and start below it.
    gray = np.asarray(game_img.convert("L"))
    top_scan_max_y = min(ry2, int(0.35 * H))
    if top_scan_max_y <= 0 or rx2 <= rx1:
        return (rx1, max(0, ry2 - 24), rx2, ry2)

    roi = gray[0:top_scan_max_y, rx1:rx2]
    THRESH = 18  # luminance threshold for 'black'
    _, inv = cv.threshold(roi, THRESH, 255, cv.THRESH_BINARY_INV)
    inv = cv.morphologyEx(inv, cv.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)

    n, labels, stats, _ = cv.connectedComponentsWithStats(inv, connectivity=4)
    black_bottom = 0
    for i in range(1, n):
        if stats[i, cv.CC_STAT_TOP] == 0:  # touches top edge
            black_bottom = max(black_bottom, stats[i, cv.CC_STAT_TOP] + stats[i, cv.CC_STAT_HEIGHT])

    # Nominal pill height ~ proportional to the Turns width
    band_h = max(20, int(0.55 * tw))
    ry1 = max(black_bottom + 2, ry2 - band_h)
    if ry2 - ry1 < 16:  # keep some minimum
        ry1 = max(0, ry2 - 16)

    return (rx1, ry1, rx2, ry2)

# ------------------------------
# Low-res letter OCR helper
# ------------------------------
def read_date_pill_robust(ocr: OCRInterface, pill_img_pil: Image.Image) -> str:
    """
    Try several upscaling/contrast variants and pick the string that looks most
    like a valid date ('Junior Year Early Mar', 'Finale Season', ...).
    """
    import numpy as _np
    import cv2 as _cv

    def _to_cv(img):
        return _cv.cvtColor(_np.asarray(img.convert("RGB")), _cv.COLOR_RGB2BGR)

    def _to_pil(img_cv):
        from PIL import Image as _Image
        return _Image.fromarray(_cv.cvtColor(img_cv, _cv.COLOR_BGR2RGB))

    src = _to_cv(pill_img_pil)

    variants = []
    # x2 and x3 cubic upscales
    for scale in (2.0, 3.0):
        up = _cv.resize(src, dsize=None, fx=scale, fy=scale, interpolation=_cv.INTER_CUBIC)
        # Light denoise + unsharp
        den = _cv.bilateralFilter(up, d=5, sigmaColor=40, sigmaSpace=40)
        gauss = _cv.GaussianBlur(den, (0, 0), 1.2)
        sharp = _cv.addWeighted(den, 1.7, gauss, -0.7, 0)
        # CLAHE on L channel (improves contrast on brown text)
        lab = _cv.cvtColor(sharp, _cv.COLOR_BGR2LAB)
        L, A, B = _cv.split(lab)
        clahe = _cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        L2 = clahe.apply(L)
        lab2 = _cv.merge([L2, A, B])
        out = _cv.cvtColor(lab2, _cv.COLOR_LAB2BGR)
        variants.append(_to_pil(out))

    # Also include the raw pill for completeness
    variants.append(pill_img_pil)

    # OCR all variants and pick the most "date-like" by fuzzy score
    best_txt, best_score = "", -1.0
    for v in variants:
        t = (ocr.text(v, min_conf=0.0) or "").strip()
        s = score_date_like(t)
        if s > best_score:
            best_txt, best_score = t, s

    return best_txt
