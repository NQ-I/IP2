# LAN guide — Laptop 1 = server + proctor, Laptop 2+ = students (Windows)

Status legend used below: **VERIFIED** = actually executed and passed in the audit environment (Linux sandbox, one CPU core,
simulated clients, no browser); **NOT VERIFIED** = could not be tested there and must be confirmed on your hardware.

## 1. What has to be true

| Requirement | Why | Status |
|---|---|---|
| Students open **`https://<server-ip>:5000/exam`** (HTTPS) | Browsers block the camera and microphone on plain `http://<ip>` pages. Only `https://` or `localhost` may use them | HTTPS server VERIFIED; browser behaviour NOT VERIFIED |
| One server process | Live state (workers, SSE bus, detector pool) lives in that process's memory | VERIFIED (design + tests) |
| Student devices need only a browser, camera, microphone and network | All AI (YOLO, MediaPipe, YAMNet) runs on the server; no Python, no project files, no models on students | VERIFIED (by code review + server-side runs) |
| Student and proctor browsers can reach the internet | The pages load Tailwind, Font Awesome, Chart.js and Google Fonts from CDNs | NOT VERIFIED offline |
| One student account per device | A second login of the same account replaces the first session | design |

## 2. Server setup (Laptop 1), step by step

```powershell
cd C:\path\to\exam_proctor_patched_phase6
python --version                       # 3.10 or 3.11 recommended
python -m venv venv
venv\Scripts\activate                   # if blocked:  Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt         # large: TensorFlow + PyTorch/Ultralytics
```

Verify the AI models on YOUR machine (Windows was not available to the audit):

```powershell
python -m pytest tests/test_real_yolo.py tests/test_real_mediapipe.py tests/test_audio_pipeline.py -q
```

* `test_real_yolo.py` loads `models/yolov8m.pt` with Ultralytics and runs real inference on the two sample photos that ship
  inside the `ultralytics` package. It is skipped automatically when `ultralytics`/`torch` are not installed.
* Phone detection on a *real phone photo* is not covered (no such image ships with any package). Evaluate it with your own
  dataset (`datasets/phone_proctoring`, `python benchmark/phone_detection_benchmark.py`).

Create accounts and a room (test passwords - change them for real use):

```powershell
python tools/create_test_users.py --students 30 --room LAN001
```

Network and firewall:

1. Windows Settings → Network → Wi-Fi → your network → set the profile to **Private**.
2. In an **Administrator** PowerShell, once:
   `netsh advfirewall firewall add rule name="ExamProctor" dir=in action=allow protocol=TCP localport=5000`
3. `ipconfig` → note the **IPv4 Address** of the Wi-Fi/Ethernet adapter (for example `192.168.1.10`).
   Reserve this address in the router (DHCP reservation); if it changes, the self-signed certificate is regenerated
   automatically and browsers show the warning again.
4. Some campus/guest Wi-Fi networks block device-to-device traffic ("client isolation"). If a student laptop cannot open
   `https://<ip>:5000/admin/health`, use a phone hotspot or a private router.

Start the server (single process, HTTPS):

```powershell
python run.py --https --port 5000       # or double-click start_lan_https.bat
```

It prints the certificate path, the real LAN URLs, and the firewall command. Keep the window open and do not let the laptop
sleep (Power & sleep → Never). `python run.py` (no `--https`) is fine for a single-computer test on `localhost` (`start.bat`).
`--debug` is refused when the server listens on the network.

## 3. URLs

| Who | URL |
|---|---|
| Proctor (Laptop 1) | `https://localhost:5000` → log in `proctor1 / proctor123` → `/proctor/dashboard` → pick room `LAN001` |
| Student | `https://<server-ip>:5000/exam` → `student1 / student123` → Join Exam |
| Camera/microphone check (no login) | `https://<server-ip>:5000/static/device_test.html` |
| Health | `https://<server-ip>:5000/admin/health` |
| Admin runtime (models, queues) | `https://localhost:5000/admin/runtime` (log in as `admin / admin123`) |

The first visit shows a certificate warning (self-signed): **Advanced → Proceed**. To remove the warning, copy
`instance\certs\server.crt` to the student laptop and import it into *Trusted Root Certification Authorities*
(NOT VERIFIED). Never use `http://<ip>:5000` for students.

## 4. Test plan

### Two devices (proctor + one student)
1. Server running; proctor dashboard open on room `LAN001`.
2. Student laptop: open `https://<ip>:5000/admin/health` → `{"db":"ok","status":"ok",...}` (proves network + firewall + certificate).
3. `https://<ip>:5000/static/device_test.html` → **Start camera & microphone** → you see yourself and the level bar moves.
4. `https://<ip>:5000/exam` → log in → Join Exam → allow camera/microphone.
5. Proctor: the student's card appears with a green **LIVE** badge and a moving picture.

### Camera and microphone
Use `device_test.html`. "HTTPS: No" means you opened `http://`. "Permission denied" → lock icon → Allow → reload. "Camera busy" →
close Zoom/Teams/other tabs.

### Live video
The card badge shows LIVE (frame < 3 s old), STALE (< 10 s), OFFLINE. Cut the student's Wi-Fi for 15 s: badge goes STALE → OFFLINE and returns to LIVE
when the network returns (server behaviour VERIFIED; browser behaviour NOT VERIFIED).

### Events
On the student laptop, one action at a time (wait ~5 s between them): leave fullscreen (Esc), switch tab, Ctrl+C/Ctrl+V, cover the camera for 6 s,
show a second person, speak for 5 s (two consecutive audio windows are needed). Each must appear in the proctor's alert list, on the student's card
(event count and "why this risk" chips) and in the student's own notices. A phone in front of the camera depends on YOLO; its accuracy on real phone images
is NOT VERIFIED.

### Student A / Student B isolation
Two students hold up paper signs "A" and "B"; each card must show only its own picture. Trigger a violation on A only: only A's card and event count change.
Automated equivalent (VERIFIED for 2/5/10/20/30 simulated students):

```powershell
python tools/lan_smoke_test.py --url https://<server-ip>:5000 --students 2 --seconds 25 --insecure
```

### 5, 10, 20, 30 students
* Real laptops + simulated students: `python tools/lan_smoke_test.py --url https://<ip>:5000 --students 3 --first 3 --seconds 120 --insecure`
  (uses accounts `student3..student5`, synthetic labelled frames; measures nothing about detection accuracy).
* Real Chrome windows with a fake camera (tests the browser code, not accuracy; NOT VERIFIED):
  ```powershell
  1..5 | % { Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--user-data-dir=C:\temp\fs$_","--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream","--ignore-certificate-errors","--new-window","https://192.168.1.10:5000/auth/login" }
  ```
* Watch Task Manager on the server and `https://localhost:5000/admin/runtime`. Dropped AI frames are normal under load (the AI path keeps only the newest
  frame per student); the live picture must stay LIVE.
* The server lowers each browser's upload rate as students join (`core/pacing.py`: ≤10 → 2 fps preview, 11–20 → 1.4 fps, >20 → 1 fps).
* Recording: the exam video is uploaded on submit; use short exams (5–10 min) in tests. Bitrate is capped at ~0.5 Mbps.

## 5. If the live worker is missing (crash / restart)

The DATABASE row of the open exam session is the fallback: the proctor dashboard lists that student as **RECONNECTING**/**OFFLINE** instead of dropping them,
and when their browser sends the next frame the worker is resumed with the **same session id** (event numbers continue, risk is rebuilt from the stored events).
Sessions with no activity for 5 minutes are closed; ended sessions and ended rooms are never resumed. VERIFIED with a real `kill -9` and restart of
`run.py --https` (cookies stayed valid, same session id, events 1 and 2 present).

## 6. Measured in the audit environment (1 vCPU, simulated clients, real YOLOv8m + MediaPipe + YAMNet on the server)

`tools/lan_smoke_test.py` over real HTTPS with login + CSRF: 2 / 5 / 10 / 20 / 30 students → 18 / 42 / 82 / 162 / 242 checks passed
(each student LIVE, own picture only, own events only, explained risk, database matches). Request latencies from that run are not network
latencies (client and server shared one core) and must not be quoted.

## 7. Privacy

`static/recordings/` and `static/violations/` in the delivered project contain **real captured data of people** (one exam video and several hundred
evidence frames from earlier demo sessions). They were left untouched. Remove them (and the matching rows) before sharing the project;
`scripts/retention_cleanup.py` implements retention. Evidence and recordings are stored unencrypted on the server disk and are served only to the
owning student, the room's proctor and admins.

## 8. Common problems

| Symptom | Fix |
|---|---|
| Student cannot open the URL | `ping <ip>`; firewall rule; network profile Private; client isolation on the access point |
| "Your connection isn't private" | expected (self-signed): Advanced → Proceed |
| Camera does not start | open `device_test.html`; make sure the URL starts with `https://` |
| Card shows STALE/OFFLINE | weak Wi-Fi, hidden tab, sleeping laptop |
| Server IP changed | run `ipconfig` again; restart `run.py --https` (certificate regenerates) |
| Evidence images do not open (old Windows data) | fixed: paths are normalised to `/` at startup |
