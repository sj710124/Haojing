import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
from PIL import Image
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt

# --- 1. 建立資料夾與資料庫初始化 ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_FILE = "outsourcing.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_no TEXT,
            part_name TEXT,
            vendor TEXT,
            process TEXT,
            qty INTEGER,
            status TEXT,
            due_date TEXT,
            gdrive_link TEXT,
            image_path TEXT,
            cad_path TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 安全轉換文字函數（防止 CSV 還原後空值變成 NaN 導致當機）
def safe_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

# 讀取歷史不重複清單（供下拉選單自動完成與關鍵字搜尋使用）
def get_history_options(column_name, default_list=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"SELECT DISTINCT {column_name} FROM orders WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
    db_items = [safe_str(row[0]) for row in c.fetchall() if safe_str(row[0])]
    conn.close()
    if default_list:
        combined = list(dict.fromkeys(db_items + default_list))
        return combined
    return db_items

# 解析多張圖片路徑（以分號 ; 區隔，並相容舊版單張路徑與防呆）
def parse_image_paths(img_path_str):
    s = safe_str(img_path_str)
    if not s:
        return []
    paths = [p.strip() for p in s.split(";") if p.strip()]
    return [p for p in paths if os.path.exists(p)]

# --- 2. CAD (DXF) 轉圖片預覽函數 ---
def render_dxf(dxf_path):
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        fig = plt.figure(figsize=(8, 6), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)
        return fig
    except Exception as e:
        st.error(f"CAD 解析失敗: {e}")
        return None

# --- 3. 網頁介面設定 ---
st.set_page_config(page_title="委外加工追蹤系統 2.3", layout="wide")
st.title("🏭 工業委外加工追蹤系統")

menu = st.sidebar.radio("功能選單", ["📋 工單看板與修改", "➕ 新增委外工單", "☁️ Google雲端備份/還原"])

DEFAULT_PROCESSES = ["車床", "銑床", "CNC複合", "熱處理", "表面處理/電鍍", "雷射切割", "線切割", "研磨"]

# --- 4. 功能一：新增委外工單 ---
if menu == "➕ 新增委外工單":
    st.subheader("建立新委外加工單")
    st.caption("💡 提示：料號、品名、廠商與加工工序皆會自動記憶！點開選單可直接打關鍵字篩選，或選「➕ 手動輸入」新增。")

    history_part_nos = get_history_options("part_no")
    history_part_names = get_history_options("part_name")
    history_vendors = get_history_options("vendor")
    history_processes = get_history_options("process", DEFAULT_PROCESSES)

    if "form_reset_key" not in st.session_state:
        st.session_state.form_reset_key = 0

    col_reset1, col_reset2 = st.columns([4, 1])
    with col_reset2:
        if st.button("🧹 清空表單重填"):
            st.session_state.form_reset_key += 1
            st.rerun()

    rk = st.session_state.form_reset_key

    col1, col2 = st.columns(2)
    with col1:
        p_no_choice = st.selectbox("料號 / 圖號 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新料號"] + history_part_nos, key=f"pno_sel_{rk}")
        if p_no_choice == "➕ 手動輸入新料號":
            part_no = st.text_input("請輸入新料號 *", key=f"pno_txt_{rk}")
        else:
            part_no = p_no_choice

        p_name_choice = st.selectbox("品名 / 零件名稱 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新品名"] + history_part_names, key=f"pname_sel_{rk}")
        if p_name_choice == "➕ 手動輸入新品名":
            part_name = st.text_input("請輸入新品名 *", key=f"pname_txt_{rk}")
        else:
            part_name = p_name_choice

        vendor_choice = st.selectbox("委外廠商名稱 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新廠商"] + history_vendors, key=f"ven_sel_{rk}")
        if vendor_choice == "➕ 手動輸入新廠商":
            vendor = st.text_input("請輸入新廠商名稱 *", key=f"ven_txt_{rk}")
        else:
            vendor = vendor_choice

        proc_choice = st.selectbox("加工工序 *(可輸入關鍵字搜尋或新增)*", history_processes + ["➕ 手動輸入新工序"], key=f"proc_sel_{rk}")
        if proc_choice == "➕ 手動輸入新工序":
            process = st.text_input("請輸入新加工工序 *(輸入過一次後系統會自動記住)*", key=f"proc_txt_{rk}")
        else:
            process = proc_choice

    with col2:
        qty = st.number_input("數量", min_value=1, value=1, key=f"qty_{rk}")
        status = st.selectbox("目前狀態", ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"], key=f"stat_{rk}")
        order_date = st.date_input("📅 發包日期", key=f"due_{rk}")
        notes = st.text_area("加工備註 / 注意事項", key=f
