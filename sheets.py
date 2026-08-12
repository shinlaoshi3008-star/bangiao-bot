"""
Module xử lý đọc/ghi Google Sheets cho bot bàn giao.
Yêu cầu biến môi trường:
- GOOGLE_CREDENTIALS_JSON: toàn bộ nội dung file JSON service account (dạng chuỗi)
- SPREADSHEET_ID: ID của Google Sheet (lấy từ URL của sheet)
"""

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

TASK_HEADERS = [
    "STT", "Thời gian giao", "Tên nhiệm vụ", "Người thực hiện", "Người giao",
    "Hạn hoàn thành", "Xác nhận nhận việc",
]
HANDOVER_HEADERS = ["STT", "ID", "Thời gian tạo", "Tên vật/nhiệm vụ", "Quý", "Tân", "Hương", "Thịnh"]

MEMBER_ORDER = ["Quý", "Tân", "Hương", "Thịnh"]


def _get_client():
    creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_spreadsheet():
    client = _get_client()
    return client.open_by_key(os.environ["SPREADSHEET_ID"])


def _ensure_sheet(ss, title, headers):
    try:
        ws = ss.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
        ws.append_row(headers)
        return ws
    # đảm bảo có header nếu sheet đang trống
    if not ws.get_all_values():
        ws.append_row(headers)
    return ws


def get_task_sheet():
    ss = _get_spreadsheet()
    return _ensure_sheet(ss, "GiaoNhiemVu", TASK_HEADERS)


def get_handover_sheet():
    ss = _get_spreadsheet()
    return _ensure_sheet(ss, "BanGiaoVatChat", HANDOVER_HEADERS)


def append_task(task_name: str, members_str: str, creator_name: str, deadline_text: str) -> int:
    ws = get_task_sheet()
    values = ws.get_all_values()
    stt = len(values)  # trừ header
    ws.append_row([
        stt,
        datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M"),
        task_name,
        members_str,
        creator_name,
        deadline_text,
        "Chưa ai xác nhận",
    ])
    return len(values) + 1  # số dòng thật trên sheet (tính cả header)


def update_task_confirm_by_row(row_index: int, summary_text: str):
    ws = get_task_sheet()
    col_idx = TASK_HEADERS.index("Xác nhận nhận việc") + 1
    ws.update_cell(row_index, col_idx, summary_text)


def append_handover(handover_id: str, item_name: str) -> int:
    ws = get_handover_sheet()
    values = ws.get_all_values()
    stt = len(values)
    row = [
        stt,
        handover_id,
        datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M"),
        item_name,
    ] + ["Chưa xác nhận"] * 4
    ws.append_row(row)
    return len(values) + 1  # số dòng thật trên sheet (tính cả header)


def update_handover_confirm_by_row(row_index: int, person_name: str, confirm_text: str):
    ws = get_handover_sheet()
    col_idx = HANDOVER_HEADERS.index(person_name) + 1
    ws.update_cell(row_index, col_idx, confirm_text)


def update_handover_confirm(handover_id: str, person_name: str, confirm_text: str) -> bool:
    """Dự phòng: dùng khi không có sẵn row_index (VD sau khi bot khởi động lại)."""
    ws = get_handover_sheet()
    values = ws.get_all_values()
    if not values:
        return False
    header = values[0]
    if person_name not in header:
        return False
    col_idx = header.index(person_name) + 1
    for i, row in enumerate(values[1:], start=2):
        if len(row) > 1 and row[1] == handover_id:
            ws.update_cell(i, col_idx, confirm_text)
            return True
    return False
