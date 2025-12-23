import os
import json
import asyncio
import random
import signal
import sys
import time
import traceback
from typing import List, Tuple

from pyrogram import Client, errors
from pyrogram.raw import functions, types


# ======================================================
#             Telegram Multi-Session Reporter
# ======================================================

BANNER = r"""
╔═══════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v3.0 (by Oxeigns)  ║
║    Multi-Session | Live Logs | Safe & Smart  ║
╚═══════════════════════════════════════════════╝
"""
print(BANNER)


# ================= CONFIG ===================

CONFIG_PATH = "config.json"
if not os.path.exists(CONFIG_PATH):
    print("❌ Missing config.json file.")
    sys.exit(1)

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

API_ID = int(os.getenv("API_ID", CONFIG["API_ID"]))
API_HASH = os.getenv("API_HASH", CONFIG["API_HASH"])
CHANNEL_LINK = os.getenv("CHANNEL_LINK", CONFIG["CHANNEL_LINK"])
MESSAGE_LINK = os.getenv("MESSAGE_LINK", CONFIG["MESSAGE_LINK"])
REPORT_TEXT = os.getenv("REPORT_TEXT", CONFIG["REPORT_TEXT"])
NUMBER_OF_REPORTS = int(os.getenv("NUMBER_OF_REPORTS", CONFIG["NUMBER_OF_REPORTS"]))

# Load session strings dynamically (SESSION_1, SESSION_2, ...)
SESSIONS: List[str] = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]

if not SESSIONS:
    print("❌ No sessions found! Please add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)

print(f"✅ Loaded {len(SESSIONS)} sessions. Target: {NUMBER_OF_REPORTS} reports.\n")


# ================= UTILITIES ===================

def get_reason():
    """Select the active reporting reason from config/env."""
    mapping = {
        "REPORT_REASON_CHILD_ABUSE": types.InputReportReasonChildAbuse,
        "REPORT_REASON_VIOLENCE": types.InputReportReasonViolence,
        "REPORT_REASON_ILLEGAL_GOODS": types.InputReportReasonIllegalDrugs,
        "REPORT_REASON_ILLEGAL_ADULT": types.InputReportReasonPornography,
        "REPORT_REASON_PERSONAL_DATA": types.InputReportReasonPersonalDetails,
        "REPORT_REASON_SCAM": types.InputReportReasonSpam,
        "REPORT_REASON_COPYRIGHT": types.InputReportReasonCopyright,
        "REPORT_REASON_SPAM": types.InputReportReasonSpam,
        "REPORT_REASON_OTHER": types.InputReportReasonOther,
    }
    for key, reason_cls in mapping.items():
        if str(CONFIG.get(key, False)).lower() == "true" or os.getenv(key, "false").lower() == "true":
            return reason_cls()
    return types.InputReportReasonOther()


REASON = get_reason()


def log(msg: str, level: str = "INFO"):
    """Color-coded timestamped logs."""
    colors = {
        "INFO": "\033[94m",
        "WARN": "\033[93m",
        "ERR": "\033[91m",
        "OK": "\033[92m",
    }
    color = colors.get(level, "")
    reset = "\033[0m"
    print(f"{color}[{time.strftime('%H:%M:%S')}] {level}: {msg}{reset}", flush=True)


# ================= CORE ===================

async def fetch_target_info(app: Client, chat_link: str, message_id: int) -> Tuple[str, str, str]:
    """Fetch info about the message being reported."""
    chat = await app.get_chat(chat_link)
    msg = await app.get_messages(chat.id, message_id)
    sender = msg.from_user.first_name if msg.from_user else "Unknown"
    username = f"@{msg.from_user.username}" if msg.from_user and msg.from_user.username else "No username"
    preview = (msg.text or msg.caption or "No text").replace("\n", " ")[:80]
    log(f"🎯 Target Message: ID={msg.id} | Sender={sender} ({username}) | Preview='{preview}'", "INFO")
    return sender, username, preview


async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict):
    """Send one report via one session with full error handling."""
    try:
        async with Client(
            f"reporter_{index}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_str,
            no_updates=True
        ) as app:
            me = await app.get_me()
            log(f"👤 Session {index} logged in as {me.first_name} ({me.id})", "INFO")

            if index == 1:
                # Only first session fetches target info
                await fetch_target_info(app, channel, message_id)

            try:
                chat = await app.get_chat(channel)
                peer = await app.resolve_peer(chat.id)
                msg = await app.get_messages(chat.id, message_id)

                await asyncio.sleep(random.uniform(1.0, 2.5))  # natural delay

                await app.invoke(
                    functions.messages.Report(
                        peer=peer,
                        id=[msg.id],
                        reason=REASON,
                        message=REPORT_TEXT
                    )
                )

                stats["success"] += 1
                log(f"✅ Report sent successfully by {me.first_name} for message {msg.id}", "OK")

            except errors.FloodWait as e:
                stats["failed"] += 1
                log(f"⚠️ FloodWait ({e.value}s) for session {index} | {me.first_name}", "WARN")
                await asyncio.sleep(e.value)

            except Exception as ex:
                stats["failed"] += 1
                log(f"❌ Error in session {index}: {ex}", "ERR")
                log(traceback.format_exc(), "ERR")

    except Exception as ex:
        stats["failed"] += 1
        log(f"❌ Failed to initialize session {index}: {ex}", "ERR")
        log(traceback.format_exc(), "ERR")


# ================= MAIN ===================

async def main():
    stop_event = asyncio.Event()
    stats = {"success": 0, "failed": 0}

    def shutdown(*_):
        log("🛑 Shutdown signal received. Stopping gracefully...", "WARN")
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
    except Exception:
        pass

    message_id = int(MESSAGE_LINK.split("/")[-1])
    total_reports = min(NUMBER_OF_REPORTS, len(SESSIONS))

    log(f"🚀 Starting {total_reports} reports using {len(SESSIONS)} sessions...\n", "INFO")

    used_sessions = random.sample(SESSIONS, total_reports)
    tasks = []

    for i, session in enumerate(used_sessions, start=1):
        tasks.append(send_report(session, i, CHANNEL_LINK, message_id, stats))
        await asyncio.sleep(random.uniform(1.5, 3.5))

    # Live progress display
    while not stop_event.is_set() and any(not t.done() for t in tasks):
        log(f"📊 Progress — Success: {stats['success']} | Failed: {stats['failed']}", "INFO")
        await asyncio.sleep(5)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = stats["success"]
    fail_count = stats["failed"]

    log(f"\n📋 FINAL SUMMARY", "INFO")
    log(f"✅ Successful reports: {success_count}", "OK")
    log(f"❌ Failed reports: {fail_count}", "ERR")
    log(f"📈 Total attempted: {total_reports}\n", "INFO")

    log("🏁 Process complete. All sessions finished.\n", "OK")
    await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Manual stop requested. Exiting...", "WARN")
    except Exception as e:
        log(f"Critical error: {e}", "ERR")
        log(traceback.format_exc(), "ERR")
