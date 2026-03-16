#!/usr/bin/python3
"""
pi_health_monitor.py — Raspberry Pi system health monitor with Telegram alerting.

Checks CPU usage, CPU temperature, memory, disk space, and Pi firmware
throttling status (under-voltage, frequency capping, thermal throttling).
Sends a Telegram alert if any threshold is breached, or a full metrics
report if run with the SEND_ANYWAY argument.

Designed to run as a cron job:
    * * * * * /usr/bin/python3 /home/pi/pi-health-monitor/pi_health_monitor.py
    0 8 * * * /usr/bin/python3 /home/pi/pi-health-monitor/pi_health_monitor.py SEND_ANYWAY

Requirements:
    pip install -r requirements.txt

Usage:
    python pi_health_monitor.py              # alert only if thresholds breached
    python pi_health_monitor.py SEND_ANYWAY  # always send full metrics report
"""

import logging
import socket
import sys
from io import StringIO
from os import environ, getcwd, path
from subprocess import CalledProcessError, TimeoutExpired, check_output
from sys import exc_info

import telepot
from dotenv import load_dotenv
from psutil import cpu_percent, disk_usage, virtual_memory

# ── Load environment variables ────────────────────────────────────────────────

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, '.env'))

APPLICATION_NAME = path.basename(__file__).replace(".py", "")

# ── Logging configuration ─────────────────────────────────────────────────────

DIR_LOGS          = environ.get('DIR_LOGS', getcwd())
WRITE_LOG_TO_DISK = environ.get("WRITE_LOG_TO_DISK", "false").lower() == "true"
LOGGING_LEVEL     = logging.getLevelName(environ.get("LOGGING_LEVEL", "INFO").upper())

# ── Telegram ──────────────────────────────────────────────────────────────────

TELEGRAM_ENABLED     = environ.get("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_KEY     = environ.get("TELEGRAM_BOT_KEY")
TELEGRAM_BOT_CHAT_ID = environ.get("TELEGRAM_BOT_CHAT_ID")
bot = telepot.Bot(TELEGRAM_BOT_KEY) if (TELEGRAM_ENABLED and TELEGRAM_BOT_KEY) else None

# ── Alert thresholds (configurable via .env) ──────────────────────────────────

CPU_USAGE_ALERT    = float(environ.get("CPU_USAGE_ALERT",    "90"))
CPU_TEMP_ALERT     = float(environ.get("CPU_TEMP_ALERT",     "80"))
MEMORY_FREE_ALERT  = float(environ.get("MEMORY_FREE_ALERT",  "10"))   # % free
DISK_USAGE_ALERT   = float(environ.get("DISK_USAGE_ALERT",   "85"))   # % used
DISK_FREE_GB_ALERT = float(environ.get("DISK_FREE_GB_ALERT", "1.5"))  # GB free

# ── Feature flags ─────────────────────────────────────────────────────────────

ENABLE_THROTTLE_CHECK = environ.get("ENABLE_THROTTLE_CHECK", "true").lower() == "true"

# ── Logging setup ─────────────────────────────────────────────────────────────

def _get_log_filename():
    log_dir = DIR_LOGS
    if not log_dir or not path.isdir(log_dir):
        logging.warning(
            "DIR_LOGS (%s) is invalid or missing, using current working directory (%s)",
            log_dir, getcwd()
        )
        log_dir = getcwd()
    if not log_dir.endswith("/"):
        log_dir += "/"
    return path.join(log_dir, f"{APPLICATION_NAME}.log")


def configure_logging():
    fmt     = '%(asctime)s %(funcName)-20s [%(lineno)s]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    if WRITE_LOG_TO_DISK:
        log_file = _get_log_filename()
        logging.basicConfig(
            format=fmt, datefmt=datefmt,
            filename=log_file, filemode="a",
            level=LOGGING_LEVEL
        )
        print("Logging to", log_file)
    else:
        logging.basicConfig(format=fmt, datefmt=datefmt, level=LOGGING_LEVEL)
    logging.info("Logger initialised.")


# ── Telegram wrappers ─────────────────────────────────────────────────────────

def _bot_send(fn, *args, **kwargs):
    """Safe Telegram wrapper — swallows send errors."""
    if not (TELEGRAM_ENABLED and bot):
        return
    try:
        fn(*args, **kwargs)
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")


def send_message(msg, parse_mode="Markdown"):
    _bot_send(bot.sendMessage, TELEGRAM_BOT_CHAT_ID, msg, parse_mode=parse_mode)


def bot_sendDocument(file, caption=None):
    _bot_send(
        bot.sendDocument, TELEGRAM_BOT_CHAT_ID,
        file, caption=caption or '', parse_mode="Markdown"
    )


def log_error_and_send_telegram(msg):
    logging.exception(msg) if exc_info()[0] else logging.error(msg)
    _bot_send(
        bot.sendMessage, TELEGRAM_BOT_CHAT_ID,
        f"*{APPLICATION_NAME}* _{msg}_",
        parse_mode="Markdown"
    )


# ── System metrics ────────────────────────────────────────────────────────────

def get_cpu_temp():
    """Read CPU temperature from Pi thermal zone. Returns float or None."""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return float(f.readline().strip()) / 1000
    except Exception as e:
        logging.error(f"Failed to read CPU temperature: {e}")
        return None


def get_throttle_status():
    """
    Check Raspberry Pi firmware throttling status via vcgencmd.
    Returns list of warning strings, or empty list if all OK.
    Returns None if vcgencmd is not available (non-Pi host).
    """
    try:
        raw = check_output(['vcgencmd', 'get_throttled'], timeout=5).decode().strip()
        # Output format: "throttled=0x0"
        status = int(raw.split('=')[1], 16)
    except FileNotFoundError:
        logging.info("vcgencmd not found — throttle check skipped (non-Pi host)")
        return None
    except (CalledProcessError, TimeoutExpired, ValueError) as e:
        logging.error(f"vcgencmd failed: {e}")
        return None

    THROTTLE_FLAGS = [
        (0x1, "⚠️ Power supply is currently under-voltage.",      "⚠️ Power supply has previously been under-voltage."),
        (0x2, "⚠️ ARM frequency is currently capped.",            "⚠️ ARM frequency has previously been capped."),
        (0x4, "⚠️ CPU is currently throttled.",                   "⚠️ CPU has previously been throttled."),
        (0x8, "⚠️ CPU is currently at soft temperature limit.",   "⚠️ CPU has previously been at soft temperature limit."),
    ]

    warnings = []
    for bit, current_msg, past_msg in THROTTLE_FLAGS:
        if status & bit:
            warnings.append(current_msg)
        elif status & (bit << 16):
            warnings.append(past_msg)

    return warnings


def get_top_processes(limit=10):
    """Return top processes sorted by memory usage as a string."""
    try:
        processes = check_output(['ps', 'aux', '--sort=-rss']).decode().splitlines()
        return "\n".join(processes[:limit])
    except Exception as e:
        logging.error(f"Failed to get top processes: {e}")
        return "Unable to retrieve process list."


# ── Health check ──────────────────────────────────────────────────────────────

def check_resources(send_anyway=False):
    """
    Gather system metrics, check against thresholds, and send Telegram alerts.

    Args:
        send_anyway: If True, always send a full metrics report regardless
                     of threshold breaches.
    """
    cpu_usage = cpu_percent(interval=1)
    cpu_temp  = get_cpu_temp()
    disk      = disk_usage('/')
    mem       = virtual_memory()
    mem_free  = 100 - mem.percent

    logging.info(f"CPU Usage : {cpu_usage}%")
    logging.info(f"CPU Temp  : {cpu_temp:.1f}°C" if cpu_temp else "CPU Temp: N/A")
    logging.info(f"Memory    : {mem.available // (1024**2)}MB free ({mem_free:.1f}%)")
    logging.info(f"Disk      : {disk.free // (1024**3)}GB free ({disk.percent}% used)")

    # ── Threshold checks ──────────────────────────────────────────────────────
    alerts = []

    if cpu_usage >= CPU_USAGE_ALERT:
        alerts.append(f"High CPU usage: {cpu_usage}%")

    if cpu_temp and cpu_temp >= CPU_TEMP_ALERT:
        alerts.append(f"High CPU temperature: {cpu_temp:.1f}°C")

    if mem_free <= MEMORY_FREE_ALERT:
        alerts.append(f"Low memory: {mem_free:.1f}% free ({mem.available // (1024**2)}MB)")

    if disk.percent >= DISK_USAGE_ALERT or disk.free <= (DISK_FREE_GB_ALERT * (1024**3)):
        alerts.append(f"Disk space low: {disk.free // (1024**3)}GB free ({100 - disk.percent:.1f}% remaining)")

    if ENABLE_THROTTLE_CHECK:
        throttle_warnings = get_throttle_status()
        if throttle_warnings:
            alerts.extend(throttle_warnings)
            logging.warning(f"Throttle warnings: {throttle_warnings}")
        elif throttle_warnings is not None:
            logging.info("Throttle status: OK")

    # ── Send alert or report ──────────────────────────────────────────────────
    if not alerts and not send_anyway:
        logging.info("All checks passed — no alert sent.")
        return

    hostname = socket.gethostname()
    top_procs = get_top_processes()

    if send_anyway:
        # Full metrics report
        temp_str = f"{cpu_temp:.1f}°C" if cpu_temp else "N/A"
        body = (
            f"\n"
            f"CPU Usage  : {cpu_usage}%\n"
            f"CPU Temp   : {temp_str}\n"
            f"Memory Free: {mem.available // (1024**2)} MB ({mem_free:.1f}%)\n"
            f"Disk Free  : {disk.free // (1024**3)} GB ({100 - disk.percent:.1f}%)\n"
        )
        if alerts:
            body += "\n*Alerts:*\n" + "\n".join(f"- {a}" for a in alerts)
    else:
        # Alert-only report
        body = "\n".join(f"- {a}" for a in alerts)

    msg = f"*System Report ({hostname}):*\n`{body}`"
    send_message(msg)
    bot_sendDocument(('system.txt', StringIO(top_procs)))


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    configure_logging()
    try:
        send_anyway = len(sys.argv) > 1 and sys.argv[1].upper() == "SEND_ANYWAY"
        check_resources(send_anyway)
    except Exception as e:
        logging.exception(f"Unhandled exception: {e}")
        log_error_and_send_telegram(str(e))
