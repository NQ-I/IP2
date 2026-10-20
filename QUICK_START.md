# Quick Start

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python setup_demo.py                 # demo accounts + room  (or: python tools/create_test_users.py --students 30 --room LAN001)
python run.py                        # this computer only:  http://localhost:5000
```

`models/yolov8m.pt` and `trained_models/rf_classifier.pkl` are already in the project - nothing to download or train.

## Proctor and student on ONE computer

| Who | Address |
|---|---|
| Proctor / admin | `http://localhost:5000` |
| Student | `http://127.0.0.1:5000/exam` |

A browser keeps one login per address. Logging the student in at `localhost` logs the proctor
out of the dashboard (it then shows "This browser is no longer logged in as the proctor").
`127.0.0.1` is a different address with its own login, and the camera works there over http.
An Incognito window works too. The LAN address (`http://192.168.x.x:5000`) blocks the camera
over http.

Head / gaze detection starts after a short calibration (≤ 15 s with the face in view). A look
away becomes a violation when it is held for 4 s.

## Several laptops on the LAN (students on other devices)

Camera and microphone only work over HTTPS on other devices:

```powershell
python run.py --https --port 5000    # or double-click start_lan_https.bat
```

Students open `https://<server-ip>:5000/exam`. Full steps, firewall rule and tests: **LAN_GUIDE.md**.

| Login      | Password   | Lands on              |
|------------|------------|-----------------------|
| admin      | admin123   | /admin/dashboard      |
| proctor1   | proctor123 | /proctor/dashboard    |
| student1…5 | student123 | /exam                 |

These are TEST passwords - change them before real use.
