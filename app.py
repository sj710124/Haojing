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

def safe_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def get_history_options(col_name, default_list=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    q = f"SELECT DISTINCT {col_name} FROM orders WHERE {col_name} IS NOT NULL AND {col_name} != '' ORDER BY {col_name}"
    c.execute(q)
    db_items = [safe_str(r[0]) for r in c.fetchall() if safe_str(r[0])]
    conn.close()
    if default_list:
        return list(dict.fromkeys(db_items + default_list))
    return db_items

def parse_image_paths(img_path_str):
    s = safe_str(img_path_str)
    if not s:
        return []
    paths = [p.strip() for p in s.split(";") if p.strip()]
    return [p for p in paths if os.path.exists(p)]

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

st.set_page_config(page_title="委外加工追蹤系統", layout="wide")
st.title("🏭 工業委外加工追蹤系統")

menu = st.sidebar.radio(
    "功能選單",
    ["📋 工單看板與修改", "➕ 新增委外工單", "☁️ Google雲端備份/還原"]
)

DEFAULT_PROCS = ["車床", "銑床", "CNC複合", "熱處理", "表面處理/電鍍", "雷射切割", "線切割", "研磨"]
STAT_LIST = ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"]

if menu == "➕ 新增委外工單":
    st.subheader("建立新委外加工單")
    st.caption("💡 料號、品名、廠商與工序皆會自動記憶，點選單可打關鍵字搜尋！")

    hist_pnos = get_history_options("part_no")
    hist_pnames = get_history_options("part_name")
    hist_vendors = get_history_options("vendor")
    hist_procs = get_history_options("process", DEFAULT_PROCS)

    if "form_reset_key" not in st.session_state:
        st.session_state.form_reset_key = 0

    c_r1, c_r2 = st.columns([4, 1])
    with c_r2:
        if st.button("🧹 清空表單重填"):
            st.session_state.form_reset_key += 1
            st.rerun()

    rk = st.session_state.form_reset_key
    col1, col2 = st.columns(2)

    with col1:
        p_no_sel = st.selectbox("料號 / 圖號 *(可打字搜尋)*", ["➕ 手動輸入新料號"] + hist_pnos, key=f"pno_s_{rk}")
        part_no = st.text_input("請輸入新料號 *", key=f"pno_t_{rk}") if p_no_sel == "➕ 手動輸入新料號" else p_no_sel

        p_name_sel = st.selectbox("品名 / 零件名稱 *(可打字搜尋)*", ["➕ 手動輸入新品名"] + hist_pnames, key=f"pname_s_{rk}")
        part_name = st.text_input("請輸入新品名 *", key=f"pname_t_{rk}") if p_name_sel == "➕ 手動輸入新品名" else p_name_sel

        ven_sel = st.selectbox("委外廠商名稱 *(可打字搜尋)*", ["➕ 手動輸入新廠商"] + hist_vendors, key=f"ven_s_{rk}")
        vendor = st.text_input("請輸入新廠商名稱 *", key=f"ven_t_{rk}") if ven_sel == "➕ 手動輸入新廠商" else ven_sel

        proc_sel = st.selectbox("加工工序 *(可打字搜尋或新增)*", hist_procs + ["➕ 手動輸入新工序"], key=f"proc_s_{rk}")
        process = st.text_input("請輸入新加工工序 *", key=f"proc_t_{rk}") if proc_sel == "➕ 手動輸入新工序" else proc_sel

    with col2:
        qty = st.number_input("數量", min_value=1, value=1, key=f"qty_{rk}")
        status = st.selectbox("目前狀態", STAT_LIST, key=f"stat_{rk}")
        order_date = st.date_input("📅 發包日期", key=f"due_{rk}")
        notes = st.text_area("加工備註 / 注意事項", key=f"note_{rk}")

    st.markdown("---")
    st.write("📎 **上傳圖面與多張照片（可一次選多張，也可建單後陸續補拍追加）**")
    gdrive_link = st.text_input("🔗 Google 雲端硬碟連結 (選填)", key=f"gd_{rk}")
    img_files = st.file_uploader("📸 拍照或上傳照片 (可選多張 JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"img_{rk}")
    cad_file = st.file_uploader("📐 上傳 CAD 圖檔 (DXF 預覽 / DWG 備份)", type=["dxf", "dwg"], key=f"cad_{rk}")

    if st.button("💾 儲存建立工單", type="primary", use_container_width=True):
        if not part_no.strip() or not vendor.strip() or not process.strip():
            st.error("⚠️ 請確認「料號」、「委外廠商名稱」與「加工工序」皆已填寫！")
        else:
            saved_imgs = []
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            if img_files:
                for idx, img_f in enumerate(img_files):
                    p = os.path.join(UPLOAD_DIR, f"{part_no.strip()}_{ts}_{idx}_{img_f.name}")
                    with open(p, "wb") as f:
                        f.write(img_f.getbuffer())
                    saved_imgs.append(p)
            img_path_str = ";".join(saved_imgs)

            cad_path = ""
            if cad_file:
                cad_path = os.path.join(UPLOAD_DIR, f"{part_no.strip()}_{ts}_{cad_file.name}")
                with open(cad_path, "wb") as f:
                    f.write(cad_file.getbuffer())

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO orders (part_no, part_name, vendor, process, qty, status, due_date, gdrive_link, image_path, cad_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (part_no.strip(), part_name.strip(), vendor.strip(), process.strip(), qty, status, str(order_date), gdrive_link.strip(), img_path_str, cad_path, notes.strip()))
            conn.commit()
            conn.close()
            st.success(f"✅ 工單【{part_no} - {part_name}（工序：{process}）】已成功建立！")

elif menu == "📋 工單看板與修改":
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("目前尚無委外工單，請從左側選單選擇「➕ 新增委外工單」。")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            valid_stats = df["status"].dropna().unique()
            status_filter = st.multiselect("依狀態篩選", valid_stats, default=valid_stats)
        with col_f2:
            search_kw = st.text_input("🔍 搜尋料號、品名、廠商或工序")

        filtered_df = df[df["status"].isin(status_filter)]
        if search_kw:
            m1 = filtered_df["part_no"].astype(str).str.contains(search_kw, case=False, na=False)
            m2 = filtered_df["part_name"].astype(str).str.contains(search_kw, case=False, na=False)
            m3 = filtered_df["vendor"].astype(str).str.contains(search_kw, case=False, na=False)
            m4 = filtered_df["process"].astype(str).str.contains(search_kw, case=False, na=False)
            filtered_df = filtered_df[m1 | m2 | m3 | m4]

        disp_df = filtered_df[["id", "part_no", "part_name", "vendor", "process", "qty", "status", "due_date"]].rename(
            columns={
                "id": "工單ID", "part_no": "料號", "part_name": "品名",
                "vendor": "委外廠商", "process": "加工工序", "qty": "數量",
                "status": "目前狀態", "due_date": "發包日期"
            }
        )
        st.dataframe(disp_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔍 工單詳細資訊、多圖預覽與修改")
        if not filtered_df.empty:
            def fmt_order(x):
                r = filtered_df[filtered_df["id"] == x].iloc[0]
                return f"工單 #{x} | 料號: {safe_str(r.get('part_no'))} | 品名: {safe_str(r.get('part_name'))} ({safe_str(r.get('vendor'))})"

            selected_id = st.selectbox("請選擇要檢視或修改的工單：", filtered_df["id"].tolist(), format_func=fmt_order)

            if selected_id:
                row = filtered_df[filtered_df["id"] == selected_id].iloc[0]
                existing_imgs = parse_image_paths(row.get("image_path"))
                cad_path_val = safe_str(row.get("cad_path"))
                gdrive_val = safe_str(row.get("gdrive_link"))
                notes_val = safe_str(row.get("notes"))

                with st.expander("✏️ 點此展開：修改工單內容 / 追加多張照片 / 更換 CAD 檔"):
                    with st.form(f"edit_form_{selected_id}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            new_pno = st.text_input("修改料號", value=safe_str(row.get("part_no")))
                            new_pname = st.text_input("修改品名", value=safe_str(row.get("part_name")))
                            new_vendor = st.text_input("修改廠商", value=safe_str(row.get("vendor")))
                            new_proc = st.text_input("修改加工工序", value=safe_str(row.get("process")))
                        with ec2:
                            q_val = int(row["qty"]) if pd.notna(row["qty"]) else 1
                            new_qty = st.number_input("修改數量", min_value=1, value=q_val)
                            curr_st = safe_str(row.get("status"))
                            st_idx = STAT_LIST.index(curr_st) if curr_st in STAT_LIST else 0
                            new_stat = st.selectbox("修改狀態", STAT_LIST, index=st_idx)
                            try:
                                def_date = datetime.strptime(safe_str(row.get("due_date")), "%Y-%m-%d").date()
                            except:
                                def_date = datetime.today().date()
                            new_order_date = st.date_input("修改發包日期", value=def_date)
                            new_gdrive = st.text_input("修改 Google 雲端連結", value=gdrive_val)

                        new_notes = st.text_area("修改備註", value=notes_val)
                        st.markdown("---")
                        st.markdown(f"**📸 補傳或管理照片（目前已有 {len(existing_imgs)} 張）**")
                        photo_mode = st.radio("照片處理方式：", ["➕ 追加新照片（保留舊照片）", "🔄 覆蓋全部照片（清空舊照片）"], horizontal=True)
                        new_img_files = st.file_uploader("選擇新增照片 (可選多張)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
                        new_cad_file = st.file_uploader("選擇新 CAD 圖檔 (DXF/DWG)", type=["dxf", "dwg"])

                        if st.form_submit_button("💾 儲存所有修改與新檔案", type="primary"):
                            ts = datetime.now().strftime("%Y%m%d%H%M%S")
                            if new_img_files:
                                newly_saved = []
                                for idx, img_f in enumerate(new_img_files):
                                    p = os.path.join(UPLOAD_DIR, f"{new_pno.strip()}_{ts}_{idx}_{img_f.name}")
                                    with open(p, "wb") as f:
                                        f.write(img_f.getbuffer())
                                    newly_saved.append(p)
                                final_imgs = existing_imgs + newly_saved if "追加" in photo_mode else newly_saved
                            else:
                                final_imgs = existing_imgs

                            updated_img_str = ";".join(final_imgs)
                            updated_cad = cad_path_val
                            if new_cad_file:
                                updated_cad = os.path.join(UPLOAD_DIR, f"{new_pno.strip()}_{ts}_{new_cad_file.name}")
                                with open(updated_cad, "wb") as f:
                                    f.write(new_cad_file.getbuffer())

                            conn = sqlite3.connect(DB_FILE)
                            conn.execute('''
                                UPDATE orders 
                                SET part_no=?, part_name=?, vendor=?, process=?, qty=?, status=?, due_date=?, gdrive_link=?, image_path=?, cad_path=?, notes=?
                                WHERE id=?
                            ''', (new_pno.strip(), new_pname.strip(), new_vendor.strip(), new_proc.strip(), new_qty, new_stat, str(new_order_date), new_gdrive.strip(), updated_img_str, updated_cad, new_notes.strip(), int(selected_id)))
                            conn.commit()
                            conn.close()
                            st.success("✅ 工單已更新！")
                            st.rerun()

                c1, c2 = st.columns([1, 1])
                with c1:
                    st.write(f"**料號：** {safe_str(row.get('part_no'))} | **品名：** {safe_str(row.get('part_name'))}")
                    st.write(f"**廠商：** {safe_str(row.get('vendor'))} | **工序：** {safe_str(row.get('process'))} | **數量：** {row.get('qty')}")
                    st.write(f"**目前狀態：** `{safe_str(row.get('status'))}` | **📅 發包日期：** {safe_str(row.get('due_date'))}")
                    st.write(f"**備註：** {notes_val if notes_val else '無'}")

                    if gdrive_val:
                        st.link_button("📂 開啟 Google 雲端硬碟", gdrive_val)

                    if st.button("🗑️ 刪除此整筆工單"):
                        conn = sqlite3.connect(DB_FILE)
                        conn.execute("DELETE FROM orders WHERE id = ?", (int(selected_id),))
                        conn.commit()
                        conn.close()
                        st.rerun()

                    st.markdown(f"#### 📸 照片相簿 (共 {len(existing_imgs)} 張)")
                    if existing_imgs:
                        img_cols = st.columns(2)
                        for idx, img_p in enumerate(existing_imgs):
                            with img_cols[idx % 2]:
                                st.image(Image.open(img_p), caption=f"照片 #{idx+1}", use_container_width=True)
                                if st.button(f"❌ 刪除照片 #{idx+1}", key=f"del_img_{selected_id}_{idx}"):
                                    rem = [p for i, p in enumerate(existing_imgs) if i != idx]
                                    conn = sqlite3.connect(DB_FILE)
                                    conn.execute("UPDATE orders SET image_path=? WHERE id=?", (";".join(rem), int(selected_id)))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
                    else:
                        st.caption("尚未上傳照片")

                with c2:
                    st.markdown("#### 📐 CAD 圖面預覽")
                    if cad_path_val and os.path.exists(cad_path_val):
                        with open(cad_path_val, "rb") as f:
                            st.download_button("⬇️ 下載 CAD 檔", data=f, file_name=os.path.basename(cad_path_val))
                        if cad_path_val.lower().endswith(".dxf"):
                            with st.spinner("渲染 CAD 圖面中..."):
                                fig = render_dxf(cad_path_val)
                                if fig:
                                    st.pyplot(fig)
                        else:
                            st.info("💡 DWG 檔可供下載，或搭配 Google 雲端連結調閱。")
                    else:
                        st.caption("尚未上傳 CAD 檔")

elif menu == "☁️ Google雲端備份/還原":
    st.subheader("☁️ 將工單資料存回 Google 雲端硬碟")
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()

    if not df.empty:
        csv_data = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 下載全部工單報表 (CSV)", data=csv_data, file_name="委外加工工單備份.csv", mime="text/csv")
    else:
        st.info("目前尚無資料可供備份。")

    st.markdown("---")
    st.subheader("🔄 從 Google 雲端硬碟還原工單")
    uploaded_csv = st.file_uploader("選擇備份的 CSV 檔案", type=["csv"])
    if uploaded_csv is not None:
        if st.button("🚀 立即還原工單資料"):
            restore_df = pd.read_csv(uploaded_csv).fillna("")
            conn = sqlite3.connect(DB_FILE)
            restore_df.to_sql("orders", conn, if_exists="replace", index=False)
            conn.close()
            st.success("✅ 所有工單資料已成功還原！")
