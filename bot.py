"""
Bot Telegram: Giao nhiệm vụ & Bàn giao vật chất cho nhóm 4 người
(Quý - người giao cố định, Tân, Hương, Thịnh).

Biến môi trường cần thiết (xem .env.example):
  BOT_TOKEN, QUY_ID, TAN_ID, HUONG_ID, THINH_ID,
  GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID,
  WEBHOOK_URL (khi deploy), PORT (Render tự cấp)
"""

import os
import logging
import uuid
import asyncio
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

import sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
QUY_ID = int(os.environ["QUY_ID"])
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
MEMBERS = {
    "Quý": QUY_ID,
    "Tân": int(os.environ["TAN_ID"]),
    "Hương": int(os.environ["HUONG_ID"]),
    "Thịnh": int(os.environ["THINH_ID"]),
}
MEMBER_ORDER = ["Quý", "Tân", "Hương", "Thịnh"]
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Những người được phép tạo mục "Giao nhiệm vụ" và "Bàn giao vật chất"
ASSIGNER_IDS = {MEMBERS["Quý"], MEMBERS["Tân"]}
ASSIGNER_NAMES = "đ/c Quý hoặc đ/c Tân"
ID_TO_NAME = {v: k for k, v in MEMBERS.items()}


def _run_in_background(func, *args):
    """Chạy một lệnh Google Sheets (vốn đồng bộ, chậm) ở luồng riêng,
    để không làm bot bị đứng/chậm phản hồi Telegram trong lúc chờ."""

    async def _wrapper():
        try:
            await asyncio.to_thread(func, *args)
        except Exception as e:
            logger.error("Lỗi ghi Google Sheets (%s): %s", func.__name__, e)

    asyncio.create_task(_wrapper())

TASK_NAME, SELECT_MEMBERS, TASK_DEADLINE = range(3)
ITEM_NAME = 3


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup(
        [["📋 Giao nhiệm vụ", "📦 Bàn giao vật chất"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        f"Xin chào! Bot theo dõi giao việc & bàn giao của nhóm.\n"
        f"• 📋 Giao nhiệm vụ — chỉ {ASSIGNER_NAMES} dùng được. Có hạn hoàn thành, "
        f"bot sẽ tag người thực hiện để yêu cầu xác nhận đã nhận việc.\n"
        f"• 📦 Bàn giao vật chất — chỉ {ASSIGNER_NAMES} tạo, cả 4 người xác nhận\n\n"
        f"Chọn chức năng bên dưới:",
        reply_markup=kb,
    )


# ---------------------------------------------------------------------------
# Mục 1: Giao nhiệm vụ
# ---------------------------------------------------------------------------

def _build_member_kb(selected: set) -> InlineKeyboardMarkup:
    rows = []
    for name in MEMBER_ORDER:
        mark = "✅" if name in selected else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {name}", callback_data=f"tm|{name}")])
    rows.append([InlineKeyboardButton("✅ Xong", callback_data="tm_done")])
    return InlineKeyboardMarkup(rows)


async def giaonhiemvu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ASSIGNER_IDS:
        await update.message.reply_text(f"Chỉ {ASSIGNER_NAMES} mới có quyền giao nhiệm vụ.")
        return ConversationHandler.END
    await update.message.reply_text("Nhập tên nhiệm vụ:")
    return TASK_NAME


async def giaonhiemvu_gotname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task_name"] = update.message.text.strip()
    context.user_data["selected"] = set()
    await update.message.reply_text(
        "Chọn người thực hiện (bấm để chọn/bỏ chọn), xong bấm ✅ Xong:",
        reply_markup=_build_member_kb(context.user_data["selected"]),
    )
    return SELECT_MEMBERS


async def toggle_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.split("|")[1]
    selected = context.user_data.get("selected", set())
    selected.symmetric_difference_update({name})
    context.user_data["selected"] = selected
    await query.edit_message_reply_markup(reply_markup=_build_member_kb(selected))
    return SELECT_MEMBERS


async def finish_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected = context.user_data.get("selected", set())
    if not selected:
        await query.answer("Vui lòng chọn ít nhất 1 người!", show_alert=True)
        return SELECT_MEMBERS
    await query.answer()

    members_str = ", ".join(sorted(selected, key=MEMBER_ORDER.index))
    await query.edit_message_text(f"Người thực hiện: {members_str}")
    await query.message.reply_text(
        "Nhập hạn hoàn thành theo định dạng dd/mm/yyyy (VD: 20/08/2026), "
        "hoặc gõ 'không' nếu không có hạn:"
    )
    return TASK_DEADLINE


def _build_task_confirm_kb(task_id: str, assigned: list, confirmed: dict) -> InlineKeyboardMarkup:
    rows = []
    for name in assigned:
        mark = "✅" if name in confirmed else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {name}", callback_data=f"tc|{task_id}|{name}")])
    return InlineKeyboardMarkup(rows)


def _render_task_message(info: dict, confirmed: dict) -> str:
    assigned = info["assigned"]
    if all(n in confirmed for n in assigned):
        tail = "✅ TẤT CẢ ĐÃ XÁC NHẬN NHẬN VIỆC"
    else:
        tail = f"{info['mentions_html']} vui lòng bấm nút của mình để xác nhận đã nhận nhiệm vụ:"
    return info["header_text"] + "\n\n" + tail


async def giaonhiemvu_gotdeadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if raw.lower() in ("không", "khong", "k"):
        deadline_text = "Không có hạn"
        deadline_date = None
    else:
        try:
            deadline_date = datetime.strptime(raw, "%d/%m/%Y").date()
            deadline_text = raw
        except ValueError:
            await update.message.reply_text(
                "Định dạng chưa đúng. Nhập theo dd/mm/yyyy (VD: 20/08/2026), "
                "hoặc gõ 'không' nếu không có hạn:"
            )
            return TASK_DEADLINE

    task_name = context.user_data["task_name"]
    selected = context.user_data.get("selected", set())
    assigned = sorted(selected, key=MEMBER_ORDER.index)
    members_str = ", ".join(assigned)
    creator_name = ID_TO_NAME.get(update.effective_user.id, "Không rõ")
    task_id = str(uuid.uuid4())[:8]

    mentions_html = " ".join(
        f'<a href="tg://user?id={MEMBERS[name]}">{name}</a>' for name in assigned
    )
    header_text = (
        f"📋 NHIỆM VỤ MỚI\n"
        f"Tên: {task_name}\n"
        f"Người thực hiện: {members_str}\n"
        f"Giao bởi: {creator_name}\n"
        f"Hạn hoàn thành: {deadline_text}\n"
        f"Thời gian giao: {datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M')}"
    )
    info = {
        "assigned": assigned,
        "header_text": header_text,
        "mentions_html": mentions_html,
        "task_name": task_name,
        "deadline_text": deadline_text,
        "deadline_date": deadline_date,
        "chat_id": update.effective_chat.id,
        "reminded": False,
    }
    context.bot_data.setdefault("task_info", {})[task_id] = info
    context.bot_data.setdefault("task_state", {})[task_id] = {}

    await update.message.reply_text(
        _render_task_message(info, {}),
        parse_mode="HTML",
        reply_markup=_build_task_confirm_kb(task_id, assigned, {}),
    )
    context.user_data.clear()

    async def _create_in_background():
        try:
            row_index = await asyncio.to_thread(
                sheets.append_task, task_name, members_str, creator_name, deadline_text
            )
            context.bot_data.setdefault("task_rows", {})[task_id] = row_index
        except Exception as e:
            logger.error("Lỗi ghi Google Sheets (task): %s", e)

    asyncio.create_task(_create_in_background())
    return ConversationHandler.END


async def task_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, task_id, name = query.data.split("|")

    info = context.bot_data.get("task_info", {}).get(task_id)
    if not info or name not in info["assigned"]:
        await query.answer("Mục này không hợp lệ hoặc đã quá cũ.", show_alert=True)
        return
    if MEMBERS.get(name) != query.from_user.id:
        await query.answer(f"Chỉ {name} mới xác nhận được mục này.", show_alert=True)
        return

    await query.answer("Đã xác nhận nhận việc!")

    state = context.bot_data.setdefault("task_state", {}).setdefault(task_id, {})
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    state[name] = now

    all_done = all(n in state for n in info["assigned"])
    await query.edit_message_text(
        _render_task_message(info, state),
        parse_mode="HTML",
        reply_markup=None if all_done else _build_task_confirm_kb(task_id, info["assigned"], state),
    )

    summary_text = "; ".join(
        f"{n}: ✅ {state[n]}" if n in state else f"{n}: Chưa xác nhận" for n in info["assigned"]
    )
    row_index = context.bot_data.get("task_rows", {}).get(task_id)
    if row_index:
        _run_in_background(sheets.update_task_confirm_by_row, row_index, summary_text)


# ---------------------------------------------------------------------------
# Mục 2: Bàn giao vật chất
# ---------------------------------------------------------------------------

def _build_handover_kb(handover_id: str, confirmed: dict) -> InlineKeyboardMarkup:
    rows = []
    for name in MEMBER_ORDER:
        mark = "✅" if name in confirmed else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {name}", callback_data=f"hc|{handover_id}|{name}")])
    return InlineKeyboardMarkup(rows)


async def bangiao_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ASSIGNER_IDS:
        await update.message.reply_text(f"Chỉ {ASSIGNER_NAMES} mới có quyền tạo mục bàn giao.")
        return ConversationHandler.END
    await update.message.reply_text("Nhập tên vật/nhiệm vụ cần bàn giao:")
    return ITEM_NAME


async def bangiao_gotname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_name = update.message.text.strip()
    handover_id = str(uuid.uuid4())[:8]

    context.bot_data.setdefault("handover_state", {})[handover_id] = {}

    text = (
        f"📦 BÀN GIAO VẬT CHẤT\n"
        f"Tên: {item_name}\n"
        f"Thời gian: {datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Mỗi thành viên bấm nút của mình để xác nhận đã nhận:"
    )
    await update.message.reply_text(text, reply_markup=_build_handover_kb(handover_id, {}))
    context.user_data.clear()

    async def _create_in_background():
        try:
            row_index = await asyncio.to_thread(sheets.append_handover, handover_id, item_name)
            context.bot_data.setdefault("handover_rows", {})[handover_id] = row_index
        except Exception as e:
            logger.error("Lỗi ghi Google Sheets (handover): %s", e)

    asyncio.create_task(_create_in_background())
    return ConversationHandler.END


async def handover_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, handover_id, name = query.data.split("|")

    if MEMBERS.get(name) != query.from_user.id:
        await query.answer(f"Chỉ {name} mới xác nhận được mục này.", show_alert=True)
        return

    await query.answer("Đã xác nhận!")

    state = context.bot_data.setdefault("handover_state", {}).setdefault(handover_id, {})
    now = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    state[name] = now

    all_done = all(m in state for m in MEMBER_ORDER)
    base_text = query.message.text.split("\n\nMỗi thành viên")[0]

    if all_done:
        await query.edit_message_text(base_text + "\n\n✅ ĐÃ BÀN GIAO ĐẦY ĐỦ")
    else:
        await query.edit_message_text(
            base_text + "\n\nMỗi thành viên bấm nút của mình để xác nhận đã nhận:",
            reply_markup=_build_handover_kb(handover_id, state),
        )

    confirm_text = f"✅ {now}"
    row_index = context.bot_data.get("handover_rows", {}).get(handover_id)
    if row_index:
        _run_in_background(sheets.update_handover_confirm_by_row, row_index, name, confirm_text)
    else:
        # Chưa có sẵn số dòng (VD bot vừa khởi động lại) -> dùng cách quét chậm hơn
        _run_in_background(sheets.update_handover_confirm, handover_id, name, confirm_text)


# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Đã huỷ thao tác.")
    return ConversationHandler.END


async def deadline_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    task_info = context.bot_data.get("task_info", {})
    task_state = context.bot_data.get("task_state", {})
    tomorrow = (datetime.now(VN_TZ) + timedelta(days=1)).date()

    for task_id, info in task_info.items():
        if info.get("deadline_date") != tomorrow or info.get("reminded"):
            continue

        state = task_state.get(task_id, {})
        pending = [n for n in info["assigned"] if n not in state]
        if not pending:
            continue

        mentions = " ".join(f'<a href="tg://user?id={MEMBERS[n]}">{n}</a>' for n in pending)
        try:
            await context.bot.send_message(
                chat_id=info["chat_id"],
                text=(
                    f"⏰ NHẮC HẠN\n"
                    f"Nhiệm vụ: {info['task_name']}\n"
                    f"Còn 1 ngày nữa là tới hạn ({info['deadline_text']}).\n"
                    f"{mentions} vui lòng xác nhận đã nhận và hoàn thành nhiệm vụ."
                ),
                parse_mode="HTML",
            )
            info["reminded"] = True
        except Exception as e:
            logger.error("Lỗi gửi nhắc hạn cho nhiệm vụ %s: %s", task_id, e)


async def daily_report_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    report_members = ["Tân", "Hương", "Thịnh"]
    mentions = " ".join(f'<a href="tg://user?id={MEMBERS[n]}">{n}</a>' for n in report_members)
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"🔔 NHẮC NỘP BÁO CÁO\n{mentions} vui lòng nộp báo cáo hàng ngày.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Lỗi gửi nhắc nộp báo cáo: %s", e)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    task_conv = ConversationHandler(
        entry_points=[
            CommandHandler("giaonhiemvu", giaonhiemvu_start),
            MessageHandler(filters.Regex("^📋 Giao nhiệm vụ$"), giaonhiemvu_start),
        ],
        states={
            TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, giaonhiemvu_gotname)],
            SELECT_MEMBERS: [
                CallbackQueryHandler(toggle_member, pattern=r"^tm\|"),
                CallbackQueryHandler(finish_task, pattern=r"^tm_done$"),
            ],
            TASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, giaonhiemvu_gotdeadline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    handover_conv = ConversationHandler(
        entry_points=[
            CommandHandler("bangiao", bangiao_start),
            MessageHandler(filters.Regex("^📦 Bàn giao vật chất$"), bangiao_start),
        ],
        states={
            ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bangiao_gotname)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(task_conv)
    app.add_handler(handover_conv)
    app.add_handler(CallbackQueryHandler(handover_confirm, pattern=r"^hc\|"))
    app.add_handler(CallbackQueryHandler(task_confirm, pattern=r"^tc\|"))

    app.job_queue.run_daily(
        deadline_reminder_job,
        time=dt_time(hour=9, minute=0, tzinfo=VN_TZ),
        name="deadline_reminder",
    )

    app.job_queue.run_daily(
        daily_report_reminder_job,
        time=dt_time(hour=8, minute=45, tzinfo=VN_TZ),
        days=(0, 1, 2, 3, 4),  # 0=Thứ 2 ... 4=Thứ 6 (bỏ Thứ 7, Chủ nhật)
        name="daily_report_reminder",
    )

    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        logger.info("Chạy ở chế độ webhook trên port %s", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=BOT_TOKEN,
            webhook_url=f"{webhook_url}/{BOT_TOKEN}",
        )
    else:
        logger.info("Chạy ở chế độ polling (dùng để test local)")
        app.run_polling()


if __name__ == "__main__":
    main()
