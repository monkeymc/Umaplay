# Umamusume Auto Train

This project is an **AI-powered auto-training bot** for *Umamusume: Pretty Derby* (Steam PC or Android via scrcpy).
It’s based on and improved from:

* [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer)
* [samsulpanjul/umamusume-auto-train](https://github.com/samsulpanjul/umamusume-auto-train)

![Screenshot](assets/doc/screenshot.png)

---

## ⚠️ Disclaimer

Use this bot **at your own risk**.
I take no responsibility for bans, issues, or account losses that may result from using it.

---

## ✨ Features

* **Smart Training**: Chooses the best option using a point system (rainbows, Etsuko, director, hints, etc.), the decision depends on all collected status and state; not most faces only.
* **Status Tracking**: Collects mood, stats, skill points, goals, and energy %.
* **Health & Energy**: Rests or goes to the infirmary automatically when needed.
* **Race Scheduling**: Plan races ahead of time (for fan farming or goals).
* **Skill Management**: Auto-purchases and prioritizes selected skills.
* **Race Selection**: Picks optimal races with smart decision logic.
* **Flexible Style**: Set your starting racing style (front, pace, late, end).
* **Resolution Independent**: Works on almost any screen resolution using a custom YOLO model trained with 1000+ images.
* **Claw Machine Event**: Can trigger the claw mini-game (improvements planned).

---

## 🚀 Getting Started

### Requirements

* [Python 3.10+](https://www.python.org/downloads/)
* (Optional but recommended) [Conda](https://docs.conda.io/en/latest/)

### Installation

```bash
git clone https://github.com/Magody/Umaplay.git
cd Umaplay

# Create and activate environment
conda create -n env_uma python==3.10
conda activate env_uma

# Install dependencies
pip install -r requirements.txt
```

If you face OCR errors, reinstall **paddle** and **paddleocr**:

```bash
pip uninstall -y paddlepaddle paddlepaddle-gpu paddlex paddleocr 
python -m pip install paddlepaddle
python -m pip install "paddleocr[all]"
python -m pip install paddlex
```

---

### Before You Start

Make sure you meet these conditions:

* Disable all in-game confirmation pop-ups in settings.
* Start from the **career lobby screen** (the one with the Tazuna hint icon).

---

### Configuration

Open `main.py` and choose your controller:

* **Steam** (PC):

  ```python
  ctrl = SteamController("Umamusume")
  # ctrl = ScrcpyController(window_title)
  ```

* **Android via scrcpy**:

  ```python
  window_title = "23117RA68G"  # Replace with your scrcpy device ID
  ctrl = ScrcpyController(window_title)
  # ctrl = SteamController("Umamusume")
  ```

Then configure your player setup, including race plan, skills, and style:

```python
self.player = Player(
    ctrl=ctrl,
    ocr=ocr,
    interval_stats_refresh=4,
    minimum_skill_pts=800,
    prioritize_g1=False,
    auto_rest_minimum=26,
    plan_races={
        "Y1-12-1": "Asahi Hai Futurity Stakes",
        "Y2-05-1": "NHK Mile Cup",
        "Y2-05-2": "Japanese Oaks",
        "Y3-03-2": "Osaka Hai",
        "Y3-05-1": "Victoria Mile",
        "Y3-11-2": "Japan Cup",
    },
    skill_list=[
        "Groundwork", "Focus", "Leader's Pride", "Professor of Curvature",
        "Homestretch Haste", "Summer Runner", "Left Handed",
        "Front Runner Corners", "Front Runner Straightaways",
        "Front Runner Savvy", "Sunny Days", "Wet Conditions",
        "Tokyo Racecourse", "Standard Distance"
    ],
    select_style="front"
)
```

---

### Running the Bot

```bash
python main.py
```

* Press **F2** to **start/stop** the bot.

---

## 🧠 AI Behind the Bot

The bot uses multiple AI components to make decisions:

* **YOLO Object Detection**
  Recognizes 40+ in-game objects (buttons, support cards, stats, badges, etc.).
  Trained on 1000+ labeled screenshots.

  ![Yolo](assets/doc/yolo.png)
  ![Yolo example 2](assets/doc/yolo-a.png)

* **Logistic Regression Classifier**
  Detects whether buttons are active or inactive.

* **OCR (PaddleOCR)**
  Reads numbers, goals, and text with fallback logic.

* **Scoring System**
  Evaluates training tiles based on support cards, rainbows, hints, and risk.

  ![Scoring System](assets/doc/scoring.png)

* **Label Studio Dataset**
  All models trained with high-quality labels across multiple resolutions.

  ![Label Studio](assets/doc/label-studio.png)

---

## 🤝 Contributing

* Found a bug? Open an issue.
* Want to improve? Fork the repo, create a branch, and open a Pull Request into the **dev** branch.

All contributions are welcome!

---

## 📌 Notes

* Works best with characters included in the training dataset (Oguri, Daiwa, McQueen, Taiki, Haru Urara, etc.).
* For others, detection accuracy may vary — feel free to report issues.
