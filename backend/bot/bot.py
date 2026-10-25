"""
Dory Telegram bot (family side).

  /join CODE YourName   register as family or caregiver
  /pending              open questions
  /summary              today's summary and alerts
  /briefing             what Dory will say to Mum this morning
  /gave Metformin 9am   caregiver logs medicine

The ask-the-family loop: Dory can't answer -> the bot messages everyone
registered -> someone REPLIES to that message -> the bot asks "Save this?" ->
Yes saves it through POST /family/answer, with who answered.

Run:  pip install -r requirements.txt
      export $(grep -v '^#' .env | xargs) && python bot.py
Each person must open the bot and press Start once, or Telegram blocks it from messaging them.
"""
import json
import logging
import os
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = os.getenv("DORY_API", "http://localhost:8000")
PERSON_ID = os.getenv("DORY_PERSON_ID", "mum-demo")
FAMILY_CODE = os.getenv("FAMILY_CODE", "dory-family")
CAREGIVER_CODE = os.getenv("CAREGIVER_CODE", "dory-caregiver")
TZ = ZoneInfo(os.getenv("DORY_TZ", "Asia/Dubai"))
REMIND_AFTER = timedelta(minutes=int(os.getenv("REMIND_AFTER_MIN", "30")))
REGISTRY = Path(__file__).with_name("registry.json")  # who has joined; delete to reset

logging.basicConfig(level=logging.INFO)


# ---------- registry (saved to disk so restarts don't lose members) ----------
def load() -> dict:
    base = {"members": {}, "sent": [], "reminded": [], "alerted": [], "last_med_alert": None}
    if REGISTRY.exists():
        base.update(json.loads(REGISTRY.read_text()))
    return base


def save(reg: dict) -> None:
    REGISTRY.write_text(json.dumps(reg, indent=2))


def api_name(member: dict) -> str:
    """The backend knows caregivers as 'Name (caregiver)'."""
    return f"{member['name']} (caregiver)" if member["role"] == "caregiver" else member["name"]


async def call(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.request(method, f"{API}{path}", **kwargs)
        res.raise_for_status()
        return res.json()


def member_of(chat_id) -> dict | None:
    return load()["members"].get(str(chat_id))


# ---------- commands ----------
async def start(update: Update, _):
    await update.message.reply_text(
        "Hi, I'm Dory's family bot.\nJoin with: /join CODE YourName\n"
        "Then I'll message you when Mum asks something Dory can't answer."
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2 or args[0] not in (FAMILY_CODE, CAREGIVER_CODE):
        return await update.message.reply_text("Use: /join CODE YourName (ask the family for the code).")
    role = "caregiver" if args[0] == CAREGIVER_CODE else "family"
    reg = load()
    reg["members"][str(update.effective_chat.id)] = {"name": " ".join(args[1:]), "role": role}
    save(reg)
    await update.message.reply_text(f"Welcome, {' '.join(args[1:])}. You are registered as {role}.")


async def pending(update: Update, _):
    if not member_of(update.effective_chat.id):
        return
    data = await call("GET", f"/dashboard/{PERSON_ID}")
    open_q = [q for q in data["questions"] if q["status"] == "pending"]
    if not open_q:
        return await update.message.reply_text("No open questions.")
    await update.message.reply_text("\n".join(f"#{q['id']}: {q['text']}" for q in open_q))


async def summary_cmd(update: Update, _):
    if not member_of(update.effective_chat.id):
        return
    await update.message.reply_text(await summary_text())


async def briefing_cmd(update: Update, _):
    if not member_of(update.effective_chat.id):
        return
    await update.message.reply_text((await call("GET", f"/briefing/morning?person_id={PERSON_ID}"))["text"])


async def gave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = member_of(update.effective_chat.id)
    if not member or member["role"] != "caregiver":
        return await update.message.reply_text("Only caregivers can log medicine.")
    if not context.args:
        return await update.message.reply_text("Use: /gave Metformin 9am")
    medicine = " ".join(context.args[:-1]) or context.args[0]
    when = context.args[-1] if len(context.args) > 1 else datetime.now(TZ).strftime("%H:%M")
    try:
        await call("POST", "/med/log", json={"medicine": medicine, "time": when, "confirmed_by": api_name(member)})
        await update.message.reply_text(f"Logged: {medicine} at {when}.")
    except httpx.HTTPError:
        await update.message.reply_text("Could not log that. Try again.")


# ---------- the ask-the-family loop ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    member = member_of(msg.chat_id)
    if not member:  # strangers: nothing is saved
        return await msg.reply_text("Please join first: /join CODE YourName")
    original = msg.reply_to_message.text if msg.reply_to_message else ""
    match = re.search(r"#(\d+)", original or "")
    if not match:
        return await msg.reply_text("To answer, reply directly to Dory's question message.")
    qid = int(match.group(1))
    context.bot_data.setdefault("drafts", {})[(msg.chat_id, qid)] = msg.text.strip()
    await msg.reply_text(
        f"Save this answer?\n\n{msg.text.strip()}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes, save", callback_data=f"save:{qid}"),
            InlineKeyboardButton("No", callback_data=f"drop:{qid}"),
        ]]),
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, qid = query.data.split(":")
    qid = int(qid)
    chat_id = query.message.chat_id
    draft = context.bot_data.get("drafts", {}).pop((chat_id, qid), None)
    member = member_of(chat_id)
    if action == "drop" or not draft or not member:
        return await query.edit_message_text("Okay, not saved.")
    try:
        await call("POST", "/family/answer",
                   json={"question_id": qid, "answer": draft, "answered_by": api_name(member)})
        await query.edit_message_text(f"Saved: {draft}\nDory will tell Mum, and say it came from you.")
    except httpx.HTTPStatusError as e:
        why = {403: "You are not registered.", 409: "Someone already answered this."}.get(
            e.response.status_code, "Could not save. Try again.")
        await query.edit_message_text(why)


# ---------- background jobs ----------
async def send_to(context, members, text):
    for chat_id in members:
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=text)
        except Exception:
            logging.exception("could not message %s", chat_id)


async def poll(context: ContextTypes.DEFAULT_TYPE):
    reg = load()
    if not reg["members"]:
        return
    try:
        data = await call("GET", f"/dashboard/{PERSON_ID}")
    except httpx.HTTPError:
        return
    name = data["person"]["name"]
    caregivers = [c for c, m in reg["members"].items() if m["role"] == "caregiver"]
    now = datetime.now(TZ)

    for q in data["questions"]:
        if q["status"] != "pending":
            continue
        if q["id"] not in reg["sent"]:  # one message per question, never repeated
            await send_to(context, reg["members"],
                          f"{name} asked (question #{q['id']}):\n\"{q['text']}\"\n\nReply to this message with the answer.")
            reg["sent"].append(q["id"])
        elif q["id"] not in reg["reminded"]:
            asked = datetime.fromisoformat(q["asked_at"]).replace(tzinfo=None)
            if now.replace(tzinfo=None) - asked > REMIND_AFTER:  # one reminder only
                await send_to(context, reg["members"], f"Still waiting: question #{q['id']} \"{q['text']}\".")
                reg["reminded"].append(q["id"])

    for entry in reversed(data["answers_log"]):  # oldest first
        if entry["id"] in reg["alerted"] or entry["status"] not in ("emergency", "refused"):
            continue
        reg["alerted"].append(entry["id"])
        if entry["status"] == "emergency":
            await send_to(context, caregivers, f"URGENT: {name} said \"{entry['question']}\". Please check in now.")
        else:  # medicine question: at most one alert per 10 minutes
            last = reg["last_med_alert"]
            if last and now - datetime.fromisoformat(last) < timedelta(minutes=10):
                continue
            reg["last_med_alert"] = now.isoformat()
            await send_to(context, caregivers,
                          f"{name} asked about medicine: \"{entry['question']}\". Dory told her not to take more "
                          "and to check with you. Log doses with /gave.")
    save(reg)


async def summary_text() -> str:
    data = await call("GET", f"/dashboard/{PERSON_ID}")
    lines = [data["summary"]] + [f"- {a['text']}" for a in data["alerts"]]
    return "\n".join(lines)


async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    reg = load()
    try:
        await send_to(context, reg["members"], "Evening summary\n" + await summary_text())
    except httpx.HTTPError:
        pass


async def morning_brief(context: ContextTypes.DEFAULT_TYPE):
    reg = load()
    caregivers = [c for c, m in reg["members"].items() if m["role"] == "caregiver"]
    try:
        text = (await call("GET", f"/briefing/morning?person_id={PERSON_ID}"))["text"]
        await send_to(context, caregivers, f"This is what Dory will tell {PERSON_ID.split('-')[0].title()} today:\n{text}")
    except httpx.HTTPError:
        pass


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("briefing", briefing_cmd))
    app.add_handler(CommandHandler("gave", gave))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(poll, interval=15, first=5)
    app.job_queue.run_daily(morning_brief, time(8, 0, tzinfo=TZ))
    app.job_queue.run_daily(daily_summary, time(20, 0, tzinfo=TZ))
    app.run_polling()


if __name__ == "__main__":
    main()
