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
from datetime import datetime

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
MEMBERS = {
    "Quý": QUY_ID,
    "Tân": int(os.environ["TAN_ID"]),
    "Hương": int(os.environ["HUONG_ID"]),
    "Thịnh": int(os.environ["THINH_ID"]),
}
MEMBER_ORDER = ["Quý", "Tân", "Hương", "Thịnh"]

# Những người được phép tạo mục "Giao nhiệm vụ" và "Bàn giao vật chất"
ASSIGNER_IDS = {MEMBERS["Quý"], MEMBERS["Tân"]}
ASSIGNER_NAMES = "đ/c Quý hoặc đ/c Tân"
ID_TO_NAME = {v: k for k, v in MEMBERS.items()}

TASK_NAME, SELECT_MEMBERS = range(2)
ITEM_NAME = 2


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
        f"• 📋 Giao nhiệm vụ — chỉ {ASSIGNER_NAMES} dùng được\n"
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

    task_name = context.user_data["task_name"]
    members_str = ", ".join(sorted(selected, key=MEMBER_ORDER.index))
    creator_name = ID_TO_NAME.get(query.from_user.id, "Không rõ")

    try:
        sheets.append_task(task_name, members_str, creator_name)
    except Exception as e:
        logger.error("Lỗi ghi Google Sheets (task): %s", e)

    await query.edit_message_text(
        f"📋 NHIỆM VỤ MỚI\n"
        f"Tên: {task_name}\n"
        f"Người thực hiện: {members_str}\n"
        f"Giao bởi: {creator_name}\n"
        f"Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    context.user_data.clear()
    return ConversationHandler.END


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

    try:
        sheets.append_handover(handover_id, item_name)
    except Exception as e:
        logger.error("Lỗi ghi Google Sheets (handover): %s", e)

    context.bot_data.setdefault("handover_state", {})[handover_id] = {}

    text = (
        f"📦 BÀN GIAO VẬT CHẤT\n"
        f"Tên: {item_name}\n"
        f"Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Mỗi thành viên bấm nút của mình để xác nhận đã nhận:"
    )
    await update.message.reply_text(text, reply_markup=_build_handover_kb(handover_id, {}))
    context.user_data.clear()
    return ConversationHandler.END


async def handover_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, handover_id, name = query.data.split("|")

    if MEMBERS.get(name) != query.from_user.id:
        await query.answer(f"Chỉ {name} mới xác nhận được mục này.", show_alert=True)
        return

    await query.answer("Đã xác nhận!")

    state = context.bot_data.setdefault("handover_state", {}).setdefault(handover_id, {})
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    state[name] = now

    try:
        sheets.update_handover_confirm(handover_id, name, f"✅ {now}")
    except Exception as e:
        logger.error("Lỗi cập nhật Google Sheets (confirm): %s", e)

    all_done = all(m in state for m in MEMBER_ORDER)
    base_text = query.message.text.split("\n\nMỗi thành viên")[0]

    if all_done:
        await query.edit_message_text(base_text + "\n\n✅ ĐÃ BÀN GIAO ĐẦY ĐỦ")
    else:
        await query.edit_message_text(
            base_text + "\n\nMỗi thành viên bấm nút của mình để xác nhận đã nhận:",
            reply_markup=_build_handover_kb(handover_id, state),
        )


# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Đã huỷ thao tác.")
    return ConversationHandler.END


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
