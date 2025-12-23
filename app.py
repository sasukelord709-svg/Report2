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
#      Telegram Auto Reporter v8.0 (Oxeigns)
# ======================================================
BANNER = r"""
╔════════════════════════════════════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v8.0 (Oxeigns)                                  ║
║ Live Target Intelligence | Persistent Panel | Crash-Protected | Stable     ║
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
LOG_GROUP_ID = -1003368489757  # fallback

SESSIONS = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]
if not SESSIONS:
    print("❌ No sessions found! Add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)

# ======================================================
# LOGGER SYSTEM
# ======================================================
LOG_SENDER_READY = asyncio.Event()
LIVE_PANEL_MSG_ID = None
TARGET_INFO = {"name": "Unknown", "members": 0, "type": "Unknown", "link": CHANNEL_LINK}

async def telegram_logger(session_str: str):
    """Initialize Telegram logger and create live panel message."""
    global LIVE_PANEL_MSG_ID
    try:
        async with Client("logger", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            try:
                chat = await app.get_chat(LOG_GROUP_LINK)
                if not hasattr(chat, "id"):
                    await app.join_chat(LOG_GROUP_LINK)
                    chat = await app.get_chat(LOG_GROUP_LINK)
                chat_id = getattr(chat, "id", LOG_GROUP_ID)
            except Exception:
                await app.join_chat(LOG_GROUP_LINK)
                chat = await app.get_chat(LOG_GROUP_LINK)
                chat_id = getattr(chat, "id", LOG_GROUP_ID)

            panel_text = (
                f"🎯 **Target Information (Loading...)**\n\n"
                f"📛 Name: {TARGET_INFO['name']}\n"
                f"👥 Members: {TARGET_INFO['members']}\n"
                f"🔗 Type: {TARGET_INFO['type']}\n"
                f"🧾 Link: {TARGET_INFO['link']}\n\n"
                f"📊 **Live Reporting Panel**\n\n"
                f"✅ Success: 0\n❌ Failed: 0\n🎯 Target: {NUMBER_OF_REPORTS}\n⚙️ Progress: 0%\n"
                f"🧾 Reason: {REPORT_TEXT}\n⏰ Updated: `{time.strftime('%H:%M:%S')}`"
            )
            msg = await app.send_message(chat_id, panel_text)
            LIVE_PANEL_MSG_ID = msg.id
            try:
                await app.pin_chat_message(chat_id, msg.id, disable_notification=True)
            except Exception:
                pass
            LOG_SENDER_READY.set()

            while True:
                await asyncio.sleep(30)
    except Exception as e:
        print(f"[LOGGER_FATAL] {e}")

def log_console(msg: str, level="INFO"):
    colors = {"INFO": "\033[94m", "WARN": "\033[93m", "ERR": "\033[91m", "OK": "\033[92m"}
    print(f"{colors.get(level, '')}[{time.strftime('%H:%M:%S')}] {level}: {msg}\033[0m", flush=True)

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
            log_console(f"✅ Valid session: {me.first_name} ({me.id})", "OK")
            return True
    except errors.AuthKeyUnregistered:
        log_console("❌ Invalid session — skipping permanently.", "WARN")
        return False
    except Exception as e:
        log_console(f"⚠️ Validation error: {e}", "WARN")
        return False

# ======================================================
# TARGET ANALYSIS
# ======================================================
async def fetch_target_info(session_str: str):
    """Fetch and store target channel/group details."""
    global TARGET_INFO
    try:
        async with Client("target_info", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            chat = await app.get_chat(CHANNEL_LINK)
            TARGET_INFO["name"] = chat.title or chat.username or "Unknown"
            TARGET_INFO["type"] = "Private Group" if chat.type.name == "PRIVATE" else chat.type.name.title()
            try:
                TARGET_INFO["members"] = await app.get_chat_members_count(CHANNEL_LINK)
            except Exception:
                TARGET_INFO["members"] = getattr(chat, "members_count", 0)
            log_console(f"📊 Target Info Loaded: {TARGET_INFO}", "INFO")
    except Exception as e:
        log_console(f"⚠️ Failed to fetch target info: {e}", "WARN")

# ======================================================
# REPORT FUNCTION
# ======================================================
async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict, error_log: list):
    try:
        async with Client(f"reporter_{index}", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            me = await app.get_me()
            chat = await app.get_chat(channel)
            msg = await app.get_messages(chat.id, message_id)
            peer = await app.resolve_peer(chat.id)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await app.invoke(functions.messages.Report(peer=peer, id=[msg.id], reason=REASON, message=REPORT_TEXT))
            stats["success"] += 1
            log_console(f"✅ Report #{stats['success']} sent by {me.first_name} (Session {index})", "OK")
            return True
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        stats["failed"] += 1
        error_log.append(f"❌ Session {index}: {e}")
        log_console(f"❌ Error in session {index}: {e}", "ERR")
        return False

# ======================================================
# MAIN
# ======================================================
async def main():
    global LIVE_PANEL_MSG_ID
    stats = {"success": 0, "failed": 0}
    error_log = []

    # Logger
    valid_logger = None
    for s in SESSIONS:
        if await validate_session(s):
            valid_logger = s
            break
    if not valid_logger:
        print("❌ No valid sessions for logger.")
        return

    # Fetch target info before starting
    await fetch_target_info(valid_logger)

    asyncio.create_task(telegram_logger(valid_logger))
    await LOG_SENDER_READY.wait()
    log_console("🛰️ Log mirror started successfully.", "OK")

    valid_sessions = [s for s in SESSIONS if await validate_session(s)]
    if not valid_sessions:
        log_console("⚠️ No valid sessions remain.", "WARN")
        return

    msg_id = int(MESSAGE_LINK.split("/")[-1])
    channel = normalize_channel_link(CHANNEL_LINK)
    total_sessions = len(valid_sessions)
    target_reports = NUMBER_OF_REPORTS

    async def live_panel_updater():
        async with Client("panel_updater", api_id=API_ID, api_hash=API_HASH, session_string=valid_logger) as app:
            chat = await app.get_chat(LOG_GROUP_LINK)
            chat_id = getattr(chat, "id", LOG_GROUP_ID)
            while stats["success"] + stats["failed"] < target_reports:
                try:
                    progress = round((stats["success"] / target_reports) * 100, 1)
                    panel_text = (
                        f"🎯 **Target Information**\n"
                        f"📛 Name: {TARGET_INFO['name']}\n"
                        f"👥 Members: {TARGET_INFO['members']}\n"
                        f"🔗 Type: {TARGET_INFO['type']}\n"
                        f"🧾 Link: {TARGET_INFO['link']}\n\n"
                        f"📊 **Live Reporting Panel**\n"
                        f"✅ Success: {stats['success']}\n"
                        f"❌ Failed: {stats['failed']}\n"
                        f"🎯 Target: {target_reports}\n"
                        f"⚙️ Progress: {progress}%\n"
                        f"🧾 Reason: {REPORT_TEXT}\n"
                        f"⏰ Updated: `{time.strftime('%H:%M:%S')}`"
                    )
                    await app.edit_message_text(chat_id, LIVE_PANEL_MSG_ID, panel_text)
                except Exception as e:
                    print(f"[PANEL_EDIT_ERR] {e}")
                await asyncio.sleep(10)

    asyncio.create_task(live_panel_updater())

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
        f"🎯 Target Achieved: {target_reports}\n"
        f"🕒 `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
    )

    async with Client("final_send", api_id=API_ID, api_hash=API_HASH, session_string=valid_logger) as app:
        chat = await app.get_chat(LOG_GROUP_LINK)
        await app.send_message(getattr(chat, "id", LOG_GROUP_ID), summary)

    while True:
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
