# pi-health-monitor

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**pi_health_monitor.py** is a lightweight Raspberry Pi system health monitor that checks CPU usage, CPU temperature, memory, disk space, and Pi firmware throttling status — sending instant Telegram alerts when thresholds are breached, or a full daily metrics report on demand.

Designed for a always-on Raspberry Pi homelab running Home Assistant, k3s, and other self-hosted services — where you want to know immediately if the Pi is struggling before services start failing.

- 🌡️ **CPU temperature and usage** — alert before thermal throttling kicks in
- 💾 **Memory and disk** — catch resource exhaustion before it causes downtime
- ⚡ **Pi firmware throttling** — detect under-voltage, frequency capping, and thermal limits direct from the firmware
- 📊 **Daily metrics report** — scheduled SEND_ANYWAY run gives you a morning health summary every day

No cloud dependency, no subscription — just a Python script in cron, alerting you via Telegram.

---

## 📌 Key Benefit

🔧 **Runs as a cron job** — no daemon, no service, no overhead. Executes every N minutes, checks metrics, sends alert if needed, exits. Zero resource footprint between runs.

⚡ **Pi-native throttle detection** — uses `vcgencmd get_throttled` to read the firmware's throttle register directly, detecting under-voltage and thermal events that standard monitoring tools miss. Automatically skipped on non-Pi hosts.

🎛️ **All thresholds configurable via `.env`** — no code changes needed to tune alert sensitivity per deployment.

---

## 📖 Table of Contents

- [Features](#features)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Cron Setup](#cron-setup)
- [Example Alerts](#example-alerts)
- [Roadmap](#roadmap)
- [License](#license)

---

## 🧩 Features

- CPU usage, temperature, memory and disk threshold alerts
- Raspberry Pi firmware throttle detection (under-voltage, frequency cap, thermal limit)
- Full metrics report mode (`SEND_ANYWAY`) for scheduled daily summaries
- Top processes attached as `system.txt` on every alert
- All thresholds configurable via `.env` — no code changes needed
- Gracefully skips Pi-specific checks on non-Pi Linux hosts
- Lightweight — no daemon, runs as a cron job

---

## 🚀 Quickstart

```bash
git clone https://github.com/mortylabs/pi-health-monitor.git
cd pi-health-monitor
cp .env.example .env
nano .env  # configure Telegram and thresholds
pip install -r requirements.txt
python pi_health_monitor.py SEND_ANYWAY  # test immediately
```

---

## ⚙️ Configuration

Create and customise a `.env` file in the project root:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `WRITE_LOG_TO_DISK` | Write logs to file or stdout | `false` |
| `LOGGING_LEVEL` | Log level (`DEBUG`, `INFO`, `WARN`, `ERROR`) | `INFO` |
| `DIR_LOGS` | Directory for log file output | current dir |
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `false` |
| `TELEGRAM_BOT_KEY` | Telegram bot token from BotFather | — |
| `TELEGRAM_BOT_CHAT_ID` | Telegram chat ID to send alerts to | — |
| `CPU_USAGE_ALERT` | Alert if CPU usage exceeds this % | `90` |
| `CPU_TEMP_ALERT` | Alert if CPU temp exceeds this °C | `80` |
| `MEMORY_FREE_ALERT` | Alert if free memory drops below this % | `10` |
| `DISK_USAGE_ALERT` | Alert if disk usage exceeds this % | `85` |
| `DISK_FREE_GB_ALERT` | Alert if free disk drops below this GB | `1.5` |
| `ENABLE_THROTTLE_CHECK` | Enable Pi firmware throttle detection | `true` |

---

## ⏰ Cron Setup

Add to your crontab (`crontab -e`):

```cron
# Alert if any threshold is breached — runs every 14 minutes
*/14 * * * * /usr/bin/python3 /home/pi/pi-health-monitor/pi_health_monitor.py > /dev/null 2>&1

# Daily full metrics report at 08:00
0 8 * * * /usr/bin/python3 /home/pi/pi-health-monitor/pi_health_monitor.py SEND_ANYWAY > /dev/null 2>&1
```

The `SEND_ANYWAY` argument forces a full metrics report regardless of thresholds — useful for a morning health summary.

---

## 📸 Example Alert

A daily `SEND_ANYWAY` report showing CPU, temperature, memory and disk — with the top processes attached as `system.txt`:

<img width="1949" height="589" alt="image" src="https://github.com/user-attachments/assets/ba0636e2-64fd-4c66-9f11-484052b6263e" />


---

## 📈 Roadmap

- [x] CPU, memory, disk threshold alerting
- [x] Raspberry Pi firmware throttle detection
- [x] Daily full metrics report via SEND_ANYWAY
- [x] Top processes attached as document
- [x] All thresholds configurable via `.env`
- [ ] Network interface monitoring (packet loss, link state)
- [ ] Service health checks (systemctl status per configured service list)
- [ ] Multi-host support via SSH

---

## 📜 License

This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.

---

## 💬 Questions?

Have feedback or need support?

- Open an [issue](https://github.com/mortylabs/pi-health-monitor/issues)
- Start a discussion on the repo
- Suggest features or improvements via pull requests
