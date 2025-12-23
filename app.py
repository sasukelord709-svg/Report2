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
#          Telegram Auto Reporter v6.9 (Oxeigns)
# ======================================================
BANNER = r"""
╔═════════════════════════════════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v6.9 (Oxeigns)                               ║
║ Crash-Proof | Smart Group Join | Live Telegram Log System              ║
╚═════════════════════════════════════════════════════════════════════════╝
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

LOG_GROUP_LINK = "https://t.me/+bZAKT6wMT_gwZTFl"
LOG_GROUP_ID = -5094423230

SESSIONS: List[str] = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]
if not SESSIONS:
    print("❌ No sessions found! Add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)


# ================= UTILITIES ===================

def normalize_channel_link(link: str):
    if link.startswith("https://t.me/"):
        return link.split("/")[-1]
    return link


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
    colors = {"INFO": "\033[94m", "WARN": "\033[93m", "ERR": "\033[91m", "OK": "\033[92m"}
    color = colors.get(level, "")
    reset = "\033[0m"
    print(f"{color}[{time.strftime('%H:%M:%S')}] {level}: {msg}{reset}", flush=True)


async def safe_send_message(session_str, message):
    """Safely send message to log group (skip if already joined)."""
    try:
        async with Client("safe_logger", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            try:
                await app.join_chat(LOG_GROUP_LINK)
            except errors.UserAlreadyParticipant:
                pass
            await app.send_message(LOG_GROUP_ID, message)
    except Exception:
        pass


async def send_startup_report(session_str):
    """Send startup report safely with valid session."""
    try:
        async with Client("startup_logger", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            try:
                await app.join_chat(LOG_GROUP_LINK)
            except errors.UserAlreadyParticipant:
                pass

            msg = (
                f"🚀 **Auto Reporter Started (v6.9)**\n"
                f"🕒 `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"📡 Channel: {CHANNEL_LINK}\n"
                f"💬 Message: {MESSAGE_LINK}\n"
                f"📊 Reports: {NUMBER_OF_REPORTS}\n"
                f"👥 Sessions Found: {len(SESSIONS)}\n"
            )
            await app.send_message(LOG_GROUP_ID, msg)
    except Exception as e:
        log(f"Startup report failed: {e}", "WARN")


# ================= SESSION VALIDATION ===================

async def validate_session(session_str: str) -> bool:
    try:
        async with Client("check", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            me = await app.get_me()
            log(f"✅ Valid session: {me.first_name} ({me.id})", "OK")
            return True
    except errors.AuthKeyUnregistered:
        log("❌ Invalid session detected — skipping.", "ERR")
        return False
    except Exception:
        return False


# ================= REPORT ===================

async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict, error_log: list):
    try:
        async with Client(f"reporter_{index}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, no_updates=True) as app:
            me = await app.get_me()
            try:
                await app.join_chat(LOG_GROUP_LINK)
            except errors.UserAlreadyParticipant:
                pass

            await app.send_message(LOG_GROUP_ID, f"👤 Session {index} active: {me.first_name}")

            chat = await app.get_chat(channel)
            msg = await app.get_messages(chat.id, message_id)
            peer = await app.resolve_peer(chat.id)

            await asyncio.sleep(random.uniform(1.0, 2.5))
            await app.invoke(functions.messages.Report(peer=peer, id=[msg.id], reason=REASON, message=REPORT_TEXT))

            stats["success"] += 1
            await app.send_message(LOG_GROUP_ID, f"✅ Report sent by {me.first_name} (session {index})")

    except Exception as e:
        stats["failed"] += 1
        err = f"❌ Error in session {index}: {type(e).__name__} - {e}"
        error_log.append(err)
        log(err, "ERR")
        await safe_send_message(session_str, f"**[ERROR]** {err}")


# ================= MAIN ===================

async def main():
    stats = {"success": 0, "failed": 0}
    error_log = []

    # Use the first valid session for logs
    log("🔍 Checking sessions validity...", "INFO")
    valid_sessions = []
    for s in SESSIONS:
        if await validate_session(s):
            valid_sessions.append(s)
        await asyncio.sleep(1)

    if not valid_sessions:
        log("❌ No valid sessions found — exiting.", "ERR")
        return

    await send_startup_report(valid_sessions[0])

    msg_id = int(MESSAGE_LINK.split("/")[-1])
    channel = normalize_channel_link(CHANNEL_LINK)
    total_reports = min(NUMBER_OF_REPORTS, len(valid_sessions))
    log(f"🚀 Starting with {total_reports}/{len(valid_sessions)} valid sessions...\n", "INFO")

    tasks = [
        asyncio.create_task(send_report(session, i + 1, channel, msg_id, stats, error_log))
        for i, session in enumerate(valid_sessions[:total_reports])
    ]

    async def live_progress():
        try:
            async with Client("progress_logger", api_id=API_ID, api_hash=API_HASH, session_string=valid_sessions[0]) as progress_app:
                try:
                    await progress_app.join_chat(LOG_GROUP_LINK)
                except errors.UserAlreadyParticipant:
                    pass

                while any(not t.done() for t in tasks):
                    msg = (
                        f"📡 **Live Report Update**\n"
                        f"✅ Success: {stats['success']}\n"
                        f"❌ Failed: {stats['failed']}\n"
                        f"⚙️ Pending: {len(tasks) - (stats['success'] + stats['failed'])}\n"
                    )
                    if error_log:
                        msg += "\n🚨 Recent Errors:\n" + "\n".join(error_log[-3:])
                    await progress_app.send_message(LOG_GROUP_ID, msg)
                    await asyncio.sleep(10)
        except Exception as e:
            log(f"Live logger crashed: {e}", "WARN")

    asyncio.create_task(live_progress())
    await asyncio.gather(*tasks, return_exceptions=True)

    try:
        async with Client("logger_final", api_id=API_ID, api_hash=API_HASH, session_string=valid_sessions[0]) as app:
            try:
                await app.join_chat(LOG_GROUP_LINK)
            except errors.UserAlreadyParticipant:
                pass
            await app.send_message(
                LOG_GROUP_ID,
                f"📊 **Final Summary**\n✅ Successful: {stats['success']}\n❌ Failed: {stats['failed']}\n📈 Total: {total_reports}"
            )
    except Exception as e:
        log(f"⚠️ Final summary failed: {e}", "WARN")

    log("🏁 Reporting completed. Clean exit.\n", "OK")
    await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log(f"💥 CRASH: {e}", "ERR")
        try:
            session_str = SESSIONS[0]
            crash_text = f"💥 **Critical Crash Detected**\n`{type(e).__name__}`: {e}\n\n```{traceback.format_exc()}```"
            asyncio.run(safe_send_message(session_str, crash_text))
        except Exception:
            pass
