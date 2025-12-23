import os
import json
import asyncio
import random
import signal
import sys
import time
import traceback
from typing import List

from pyrogram import Client, errors
from pyrogram.raw import functions, types

# ======================================================
#        Telegram Auto Reporter v5.5 (by Oxeigns)
# ======================================================
BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v5.5 (Oxeigns)                    ║
║  Hardcoded Log Group | Auto Join | Multi-Session Reports   ║
╚══════════════════════════════════════════════════════════════╝
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

# Hardcoded log group
LOG_GROUP_LINK = "https://t.me/+bZAKT6wMT_gwZTFl"
LOG_GROUP_ID = -5094423230

# Collect all session strings
SESSIONS: List[str] = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]

if not SESSIONS:
    print("❌ No sessions found! Add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)

print(f"✅ Loaded {len(SESSIONS)} sessions. Target: {NUMBER_OF_REPORTS} reports.\n")


# ================= UTILITIES ===================

def get_reason():
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
    for key, cls in mapping.items():
        if str(CONFIG.get(key, False)).lower() == "true" or os.getenv(key, "false").lower() == "true":
            return cls()
    return types.InputReportReasonOther()


REASON = get_reason()


def log(msg: str, level: str = "INFO"):
    colors = {
        "INFO": "\033[94m",
        "WARN": "\033[93m",
        "ERR": "\033[91m",
        "OK": "\033[92m",
    }
    color = colors.get(level, "")
    reset = "\033[0m"
    print(f"{color}[{time.strftime('%H:%M:%S')}] {level}: {msg}{reset}", flush=True)


async def async_log(app: Client, msg: str, level: str = "INFO"):
    """Send log to console and Telegram log group."""
    log(msg, level)
    try:
        await app.send_message(LOG_GROUP_ID, f"**[{level}]** {msg}")
    except Exception:
        pass  # ignore minor errors while logging


# ================= GROUP / MESSAGE DATA ===================

async def fetch_target_info(app: Client, chat_link: str, message_id: int):
    chat = await app.get_chat(chat_link)
    msg = await app.get_messages(chat.id, message_id)
    chat_type = chat.type.name.capitalize()
    members = getattr(chat, "members_count", "Unknown")

    await async_log(app, "📡 Target group information:", "INFO")
    await async_log(app, f"🏷️ Name: {chat.title}", "INFO")
    await async_log(app, f"🔗 Username: @{chat.username if chat.username else 'Private / Invite'}", "INFO")
    await async_log(app, f"🆔 ID: {chat.id}", "INFO")
    await async_log(app, f"💬 Type: {chat_type}", "INFO")
    await async_log(app, f"👥 Members: {members}", "INFO")
    await async_log(app, f"📝 Description: {chat.description or 'No description'}", "INFO")

    sender = msg.from_user.first_name if msg.from_user else "Unknown"
    username = f"@{msg.from_user.username}" if msg.from_user and msg.from_user.username else "No username"
    preview = (msg.text or msg.caption or 'No text').replace("\n", " ")[:120]

    await async_log(app, f"🎯 Message ID: {msg.id}", "INFO")
    await async_log(app, f"👤 Sender: {sender} ({username})", "INFO")
    await async_log(app, f"🕒 Date: {msg.date}", "INFO")
    await async_log(app, f"📄 Preview: {preview}", "INFO")


# ================= REPORT LOGIC ===================

async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict):
    """Send report + auto join log group if needed."""
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

            # Ensure session joined log group
            try:
                await app.join_chat(LOG_GROUP_LINK)
                log(f"📡 Session {index} joined log group successfully.", "OK")
            except errors.UserAlreadyParticipant:
                log(f"📡 Session {index} already in log group.", "INFO")
            except Exception as e:
                log(f"⚠️ Could not join log group: {e}", "WARN")

            await async_log(app, f"Session {index} ready to report...", "INFO")

            # First session fetches metadata
            if index == 1:
                await fetch_target_info(app, channel, message_id)

            chat = await app.get_chat(channel)
            peer = await app.resolve_peer(chat.id)
            msg = await app.get_messages(chat.id, message_id)

            await asyncio.sleep(random.uniform(1.0, 2.5))

            await app.invoke(
                functions.messages.Report(
                    peer=peer,
                    id=[msg.id],
                    reason=REASON,
                    message=REPORT_TEXT
                )
            )

            stats["success"] += 1
            await async_log(app, f"✅ Report sent by {me.first_name} (session {index})", "OK")

    except errors.FloodWait as e:
        stats["failed"] += 1
        await async_log(app, f"⚠️ FloodWait {e.value}s for session {index}", "WARN")
        await asyncio.sleep(e.value)

    except Exception as ex:
        stats["failed"] += 1
        log(traceback.format_exc(), "ERR")
        await async_log(app, f"❌ Session {index} failed: {ex}", "ERR")


# ================= MAIN ===================

async def main():
    stop_event = asyncio.Event()
    stats = {"success": 0, "failed": 0}

    def shutdown(*_):
        log("🛑 Shutdown signal received.", "WARN")
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
    except Exception:
        pass

    msg_id = int(MESSAGE_LINK.split("/")[-1])
    total_reports = min(NUMBER_OF_REPORTS, len(SESSIONS))
    log(f"🚀 Starting {total_reports} reports using {len(SESSIONS)} sessions...\n", "INFO")

    used_sessions = random.sample(SESSIONS, total_reports)
    tasks = []

    for i, session in enumerate(used_sessions, start=1):
        tasks.append(send_report(session, i, CHANNEL_LINK, msg_id, stats))
        await asyncio.sleep(random.uniform(1.5, 3.5))

    # Live progress
    async def progress():
        while any(not t.done() for t in tasks):
            log(f"📊 Progress — ✅ {stats['success']} | ❌ {stats['failed']}", "INFO")
            await asyncio.sleep(5)

    asyncio.create_task(progress())
    await asyncio.gather(*tasks, return_exceptions=True)

    log(f"\n📋 FINAL SUMMARY", "INFO")
    log(f"✅ Successful: {stats['success']}", "OK")
    log(f"❌ Failed: {stats['failed']}", "ERR")
    log(f"📈 Total attempted: {total_reports}\n", "INFO")

    # Send final summary to log group
    try:
        async with Client("logger", api_id=API_ID, api_hash=API_HASH, session_string=SESSIONS[0]) as logger_app:
            await logger_app.send_message(
                LOG_GROUP_ID,
                f"📊 **Report Summary**\n✅ Successful: {stats['success']}\n❌ Failed: {stats['failed']}\n📈 Total: {total_reports}"
            )
    except Exception as e:
        log(f"⚠️ Could not send summary to log group: {e}", "WARN")

    log("🏁 Reporting process finished.\n", "OK")
    await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Manual stop requested.", "WARN")
    except Exception as e:
        log(f"Critical error: {e}", "ERR")
        log(traceback.format_exc(), "ERR")
