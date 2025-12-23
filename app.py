import os
import json
import asyncio
import random
import sys
import time
import traceback
from typing import List
from pyrogram import Client, errors
from pyrogram.raw import functions, types

# ======================================================
#         Telegram Auto Reporter v7.8 (Oxeigns)
# ======================================================
BANNER = r"""
╔════════════════════════════════════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v7.8 (Oxeigns)                                  ║
║ Continuous Reports | Full Log Mirror | Crash Reporter | Heroku Safe Exit  ║
╚════════════════════════════════════════════════════════════════════════════╝
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
LOG_GROUP_ID = -1003368489757  # fallback only

SESSIONS: List[str] = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]
if not SESSIONS:
    print("❌ No sessions found! Add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)

# ======================================================
# GLOBAL LOGGER SYSTEM
# ======================================================
LOG_QUEUE = asyncio.Queue()
LOG_SENDER_READY = asyncio.Event()

async def telegram_logger(session_str: str):
    """Background task to send logs safely to Telegram log group."""
    try:
        async with Client("logger", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            chat_id = LOG_GROUP_ID
            try:
                chat = await app.get_chat(LOG_GROUP_LINK)

                # ✅ Handle ChatPreview (private group)
                if not hasattr(chat, "id"):
                    print("⚠️ Logger has preview only — joining log group...")
                    try:
                        await app.join_chat(LOG_GROUP_LINK)
                        chat = await app.get_chat(LOG_GROUP_LINK)
                    except errors.UserAlreadyParticipant:
                        chat = await app.get_chat(LOG_GROUP_LINK)
                    except Exception as e:
                        print(f"[LOGGER_JOIN_ERR] {e}")

                chat_id = getattr(chat, "id", LOG_GROUP_ID)
                print(f"✅ Logger connected to group ID: {chat_id}")

            except errors.FloodWait as e:
                await asyncio.sleep(e.value)
                await app.join_chat(LOG_GROUP_LINK)
                chat = await app.get_chat(LOG_GROUP_LINK)
                chat_id = getattr(chat, "id", LOG_GROUP_ID)
            except errors.UserAlreadyParticipant:
                chat = await app.get_chat(LOG_GROUP_LINK)
                chat_id = getattr(chat, "id", LOG_GROUP_ID)
            except Exception as e:
                print(f"[LOGGER_INIT_ERR] {e}")
                chat_id = LOG_GROUP_ID

            LOG_SENDER_READY.set()

            while True:
                msg = await LOG_QUEUE.get()
                try:
                    await app.send_message(chat_id, msg)
                except errors.FloodWait as e:
                    await asyncio.sleep(e.value)
                    await app.send_message(chat_id, msg)
                except errors.PeerIdInvalid:
                    print("⚠️ Re-resolving log group due to PeerIdInvalid...")
                    try:
                        chat = await app.get_chat(LOG_GROUP_LINK)
                        chat_id = getattr(chat, "id", LOG_GROUP_ID)
                        await app.send_message(chat_id, msg)
                    except Exception as ex:
                        print(f"[LOGGER_RECOVER_ERR] {ex}")
                except Exception as e:
                    print(f"[LOGGER_ERR] {e}")
                LOG_QUEUE.task_done()
    except Exception as e:
        print(f"[LOGGER_FATAL] {e}")

def log(msg: str, level="INFO"):
    """Unified logger for both console and Telegram."""
    colors = {"INFO": "\033[94m", "WARN": "\033[93m", "ERR": "\033[91m", "OK": "\033[92m"}
    print(f"{colors.get(level, '')}[{time.strftime('%H:%M:%S')}] {level}: {msg}\033[0m", flush=True)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(LOG_QUEUE.put(f"**[{level}]** {msg}"))
    except RuntimeError:
        pass

# ======================================================
# HELPERS
# ======================================================

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

# ======================================================
# VALIDATION
# ======================================================

async def validate_session(session_str: str) -> bool:
    try:
        async with Client("check", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            me = await app.get_me()
            log(f"✅ Valid session: {me.first_name} ({me.id})", "OK")
            return True
    except errors.AuthKeyUnregistered:
        log("❌ Invalid session detected — permanently skipped.", "WARN")
        return False
    except Exception as e:
        log(f"⚠️ Validation error: {e}", "WARN")
        return False

# ======================================================
# REPORT FUNCTION (CONTINUOUS MODE)
# ======================================================

async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict, error_log: list):
    """Handles one single report attempt per session."""
    try:
        async with Client(f"reporter_{index}", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            me = await app.get_me()
            chat = await app.get_chat(channel)
            msg = await app.get_messages(chat.id, message_id)
            peer = await app.resolve_peer(chat.id)

            await asyncio.sleep(random.uniform(0.5, 1.5))
            await app.invoke(functions.messages.Report(peer=peer, id=[msg.id], reason=REASON, message=REPORT_TEXT))

            stats["success"] += 1
            log(f"✅ Report #{stats['success']} sent by {me.first_name} (Session {index})", "OK")
            return True
    except errors.FloodWait as e:
        log(f"⚠️ FloodWait {e.value}s in session {index}, waiting...", "WARN")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        stats["failed"] += 1
        err = f"❌ Error in session {index}: {type(e).__name__} - {e}"
        error_log.append(err)
        log(err, "ERR")
        return False

# ======================================================
# MAIN (MULTI-SESSION LOOPED REPORTING)
# ======================================================

async def main():
    stats = {"success": 0, "failed": 0}
    error_log = []

    valid_logger = None
    for s in SESSIONS:
        if await validate_session(s):
            valid_logger = s
            break
    if not valid_logger:
        print("❌ No valid sessions available for Telegram logger.")
        return

    asyncio.create_task(telegram_logger(valid_logger))
    await LOG_SENDER_READY.wait()
    log("🛰️ Log mirror started successfully.", "OK")
    log("🚀 Starting Auto Reporter v7.8", "INFO")

    valid_sessions = [s for s in SESSIONS if await validate_session(s)]
    if not valid_sessions:
        log("⚠️ No valid sessions remain — aborting.", "WARN")
        return

    msg_id = int(MESSAGE_LINK.split("/")[-1])
    channel = normalize_channel_link(CHANNEL_LINK)
    total_sessions = len(valid_sessions)
    target_reports = NUMBER_OF_REPORTS

    log(f"📡 Channel: {CHANNEL_LINK}", "INFO")
    log(f"💬 Message: {MESSAGE_LINK}", "INFO")
    log(f"👥 Valid Sessions: {total_sessions} | Target Reports: {target_reports}", "INFO")

    async def live_logs():
        while stats["success"] + stats["failed"] < target_reports:
            msg = (
                f"📊 **Live Status Update**\n"
                f"✅ Success: {stats['success']}\n"
                f"❌ Failed: {stats['failed']}\n"
                f"🎯 Target: {target_reports}\n"
                f"⚙️ Progress: {round((stats['success'] / target_reports) * 100, 1)}%\n"
            )
            if error_log:
                msg += "\n🚨 Recent Errors:\n" + "\n".join(error_log[-3:])
            log(msg, "INFO")
            await asyncio.sleep(10)

    asyncio.create_task(live_logs())

    report_index = 0
    while stats["success"] < target_reports:
        current_session = valid_sessions[report_index % total_sessions]
        report_index += 1
        await send_report(current_session, report_index, channel, msg_id, stats, error_log)
        await asyncio.sleep(random.uniform(1.0, 2.0))

    summary = (
        f"📊 **Final Summary**\n"
        f"✅ Successful: {stats['success']}\n"
        f"❌ Failed: {stats['failed']}\n"
        f"📈 Sessions Used: {len(valid_sessions)}\n"
        f"🎯 Target Achieved: {target_reports}\n"
        f"🕒 `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
    )
    log(summary, "OK")

    log("🏁 All reports sent successfully. Staying alive for Heroku stability...", "INFO")
    while True:
        log("💤 Idle heartbeat — app alive.", "INFO")
        await asyncio.sleep(60)

# ======================================================
# CRASH REPORTER
# ======================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        crash_trace = traceback.format_exc()
        crash_msg = f"💥 **Crash Detected!**\nType: `{type(e).__name__}`\nReason: `{e}`\n\n```{crash_trace}```"
        print(crash_msg)
        try:
            if SESSIONS:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                async def crash_send():
                    async with Client("crash_log", api_id=API_ID, api_hash=API_HASH, session_string=SESSIONS[0]) as app:
                        await app.join_chat(LOG_GROUP_LINK)
                        await app.send_message(LOG_GROUP_ID, crash_msg)
                loop.run_until_complete(crash_send())
        except Exception as ex:
            print(f"[CRASH_REPORT_ERR] {ex}")
