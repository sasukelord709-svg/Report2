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
#          Telegram Auto Reporter v6.6 (Oxeigns)
# ======================================================
BANNER = r"""
╔═════════════════════════════════════════════════════════════════════════╗
║ 🚨 Telegram Auto Reporter v6.6 (Oxeigns)                               ║
║   Smart Session Filter | Telegram Log Output | Clean Exit Fix          ║
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

# Hardcoded log group
LOG_GROUP_LINK = "https://t.me/+bZAKT6wMT_gwZTFl"
LOG_GROUP_ID = -5094423230

# Collect sessions
SESSIONS: List[str] = [v.strip() for k, v in os.environ.items() if k.startswith("SESSION_") and v.strip()]

if not SESSIONS:
    print("❌ No sessions found! Add SESSION_1, SESSION_2, etc. in Heroku Config Vars.")
    sys.exit(1)


# ================= UTILITIES ===================

def normalize_channel_link(link: str):
    """Extract valid username or invite code from full t.me URL."""
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


async def async_log(app: Client, msg: str, level: str = "INFO"):
    """Send logs to console + Telegram group."""
    log(msg, level)
    try:
        await app.send_message(LOG_GROUP_ID, f"**[{level}]** {msg}")
    except errors.ChatWriteForbidden:
        # try to join the group automatically if missing
        try:
            await app.join_chat(LOG_GROUP_LINK)
            await app.send_message(LOG_GROUP_ID, f"**[{level}]** {msg}")
        except Exception:
            pass
    except Exception:
        pass


# ================= CONFIG SUMMARY ===================

def show_config_summary():
    print("\n🔧 Loaded Configuration Summary:")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🆔 API_ID: {API_ID}")
    print(f"🔑 API_HASH: {'✅ Loaded' if API_HASH else '❌ Missing'}")
    print(f"📡 Channel Link: {CHANNEL_LINK}")
    print(f"💬 Message Link: {MESSAGE_LINK}")
    print(f"🧾 Report Text: {REPORT_TEXT}")
    print(f"📊 Number of Reports: {NUMBER_OF_REPORTS}")
    print(f"👥 Total Sessions Found: {len(SESSIONS)}")
    print(f"🛰️ Log Group: {LOG_GROUP_LINK} (ID: {LOG_GROUP_ID})")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


show_config_summary()


# ================= VALIDATION ===================

async def validate_session(session_str: str) -> bool:
    """Check if session is valid."""
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


# ================= TARGET INFO ===================

async def fetch_target_info(app: Client, chat_link: str, message_id: int):
    """Fetch details about target group/message."""
    chat = await app.get_chat(chat_link)
    msg = await app.get_messages(chat.id, message_id)
    members = getattr(chat, "members_count", "Unknown")

    await async_log(app, f"📡 Target Group: {chat.title}", "INFO")
    await async_log(app, f"👥 Members: {members}", "INFO")
    await async_log(app, f"📝 Description: {chat.description or 'No description'}", "INFO")

    sender = msg.from_user.first_name if msg.from_user else "Unknown"
    username = f"@{msg.from_user.username}" if msg.from_user and msg.from_user.username else "No username"
    preview = (msg.text or msg.caption or 'No text').replace("\n", " ")[:100]
    await async_log(app, f"🎯 Message {msg.id} | Sender: {sender} ({username})", "INFO")
    await async_log(app, f"📄 Preview: {preview}", "INFO")


# ================= REPORT ===================

async def send_report(session_str: str, index: int, channel: str, message_id: int, stats: dict):
    """Send report safely using valid session."""
    try:
        async with Client(f"reporter_{index}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, no_updates=True) as app:
            me = await app.get_me()
            await async_log(app, f"👤 Session {index}: {me.first_name} ({me.id}) active", "INFO")

            try:
                await app.join_chat(LOG_GROUP_LINK)
            except errors.UserAlreadyParticipant:
                pass
            except Exception:
                pass

            if index == 1:
                await fetch_target_info(app, channel, message_id)

            chat = await app.get_chat(channel)
            peer = await app.resolve_peer(chat.id)
            msg = await app.get_messages(chat.id, message_id)

            await asyncio.sleep(random.uniform(1.0, 2.5))
            await app.invoke(functions.messages.Report(peer=peer, id=[msg.id], reason=REASON, message=REPORT_TEXT))

            stats["success"] += 1
            await async_log(app, f"✅ Report sent by {me.first_name} (session {index})", "OK")

    except errors.AuthKeyUnregistered:
        stats["failed"] += 1
        log(f"⚠️ Session {index} invalid, skipping further use.", "WARN")
    except errors.FloodWait as e:
        stats["failed"] += 1
        await async_log(app, f"⏳ FloodWait {e.value}s on session {index}", "WARN")
        await asyncio.sleep(e.value)
    except errors.UsernameInvalid:
        stats["failed"] += 1
        await async_log(app, f"❌ Invalid target link — please check {CHANNEL_LINK}", "ERR")
    except Exception as e:
        stats["failed"] += 1
        log(traceback.format_exc(), "ERR")
        await async_log(app, f"❌ Error in session {index}: {e}", "ERR")


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

    log("🔍 Checking sessions validity...", "INFO")
    valid_sessions = []
    for s in SESSIONS:
        if await validate_session(s):
            valid_sessions.append(s)
        await asyncio.sleep(1)

    if not valid_sessions:
        log("❌ No valid sessions found — exiting.", "ERR")
        return

    msg_id = int(MESSAGE_LINK.split("/")[-1])
    channel = normalize_channel_link(CHANNEL_LINK)
    total_reports = min(NUMBER_OF_REPORTS, len(valid_sessions))
    log(f"🚀 Starting with {total_reports}/{len(valid_sessions)} valid sessions...\n", "INFO")

    tasks = [
        asyncio.create_task(send_report(session, i + 1, channel, msg_id, stats))
        for i, session in enumerate(valid_sessions[:total_reports])
    ]

    async def progress():
        while any(not t.done() for t in tasks):
            log(f"📊 Progress — ✅ {stats['success']} | ❌ {stats['failed']}", "INFO")
            await asyncio.sleep(5)

    asyncio.create_task(progress())
    await asyncio.gather(*tasks, return_exceptions=True)

    log("\n📋 FINAL SUMMARY", "INFO")
    log(f"✅ Successful: {stats['success']}", "OK")
    log(f"❌ Failed: {stats['failed']}", "ERR")
    log(f"📈 Total attempted: {total_reports}\n", "INFO")

    # Send final summary to Telegram log group
    try:
        async with Client("logger", api_id=API_ID, api_hash=API_HASH, session_string=valid_sessions[0]) as logger_app:
            await logger_app.join_chat(LOG_GROUP_LINK)
            await logger_app.send_message(
                LOG_GROUP_ID,
                f"📊 **Final Report Summary**\n✅ Successful: {stats['success']}\n❌ Failed: {stats['failed']}\n📈 Total Attempted: {total_reports}"
            )
    except Exception as e:
        log(f"⚠️ Could not send summary log: {e}", "WARN")

    log("🏁 Reporting completed. Exiting cleanly...\n", "OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Manual stop requested.", "WARN")
    except Exception as e:
        log(f"Critical error: {e}", "ERR")
        log(traceback.format_exc(), "ERR")
