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

# 讀取歷史不重複清單（供下拉選單自動完成與關鍵字搜尋使用）
def get_history_options(column_name, default_list=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"SELECT DISTINCT {column_name} FROM orders WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
    db_items = [row[0] for row in c.fetchall()]
    conn.close()
    if default_list:
        # 合併預設清單與歷史輸入過的項目，並去除重複
        combined = list(dict.fromkeys(db_items + default_list))
        return combined
    return db_items

# 解析多張圖片路徑（以分號 ; 區隔，並相容舊版單張路徑）
def parse_image_paths(img_path_str):
    if not img_path_str or pd.isna(img_path_str):
        return []
    paths = [p.strip() for p in str(img_path_str).split(";") if p.strip()]
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
st.set_page_config(page_title="委外加工追蹤系統 2.2", layout="wide")
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
        # 1. 料號
        p_no_choice = st.selectbox("料號 / 圖號 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新料號"] + history_part_nos, key=f"pno_sel_{rk}")
        if p_no_choice == "➕ 手動輸入新料號":
            part_no = st.text_input("請輸入新料號 *", key=f"pno_txt_{rk}")
        else:
            part_no = p_no_choice

        # 2. 品名
        p_name_choice = st.selectbox("品名 / 零件名稱 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新品名"] + history_part_names, key=f"pname_sel_{rk}")
        if p_name_choice == "➕ 手動輸入新品名":
            part_name = st.text_input("請輸入新品名 *", key=f"pname_txt_{rk}")
        else:
            part_name = p_name_choice

        # 3. 廠商
        vendor_choice = st.selectbox("委外廠商名稱 *(可輸入關鍵字搜尋)*", ["➕ 手動輸入新廠商"] + history_vendors, key=f"ven_sel_{rk}")
        if vendor_choice == "➕ 手動輸入新廠商":
            vendor = st.text_input("請輸入新廠商名稱 *", key=f"ven_txt_{rk}")
        else:
            vendor = vendor_choice

        # 4. 加工工序（支援關鍵字搜尋與自訂新增）
        proc_choice = st.selectbox("加工工序 *(可輸入關鍵字搜尋或新增)*", history_processes + ["➕ 手動輸入新工序"], key=f"proc_sel_{rk}")
        if proc_choice == "➕ 手動輸入新工序":
            process = st.text_input("請輸入新加工工序 *(輸入過一次後系統會自動記住)*", key=f"proc_txt_{rk}")
        else:
            process = proc_choice

    with col2:
        qty = st.number_input("數量", min_value=1, value=1, key=f"qty_{rk}")
        status = st.selectbox("目前狀態", ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"], key=f"stat_{rk}")
        order_date = st.date_input("📅 發包日期", key=f"due_{rk}")
        notes = st.text_area("加工備註 / 注意事項", key=f"note_{rk}")

    st.markdown("---")
    st.write("📎 **上傳圖面與多張照片（可一次選多張，也可建單後陸續補拍追加）**")
    gdrive_link = st.text_input("🔗 Google 雲端硬碟連結 (選填)", key=f"gd_{rk}")
    img_files = st.file_uploader("📸 拍照或上傳零件照片 (可一次選多張 JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"img_{rk}")
    cad_file = st.file_uploader("📐 上傳 CAD 圖檔 (支援 DXF 預覽 / DWG 備份)", type=["dxf", "dwg"], key=f"cad_{rk}")

    if st.button("💾 儲存建立工單", type="primary", use_container_width=True):
        if not part_no.strip() or not vendor.strip() or not process.strip():
            st.error("⚠️ 請確認「料號」、「委外廠商名稱」與「加工工序」皆已填寫！您剛才輸入的其他資料都保留著，請直接補填即可。")
        else:
            saved_img_paths = []
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            if img_files:
                for idx, img_f in enumerate(img_files):
                    p = os.path.join(UPLOAD_DIR, f"{part_no.strip()}_{timestamp}_{idx}_{img_f.name}")
                    with open(p, "wb") as f:
                        f.write(img_f.getbuffer())
                    saved_img_paths.append(p)
            
            img_path_str = ";".join(saved_img_paths)

            cad_path = ""
            if cad_file:
                cad_path = os.path.join(UPLOAD_DIR, f"{part_no.strip()}_{timestamp}_{cad_file.name}")
                with open(cad_path, "wb") as f:
                    f.write(cad_file.getbuffer())

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO orders (part_no, part_name, vendor, process, qty, status, due_date, gdrive_link, image_path, cad_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (part_no.strip(), part_name.strip(), vendor.strip(), process.strip(), qty, status, str(order_date), gdrive_link, img_path_str, cad_path, notes))
            conn.commit()
            conn.close()
            st.success(f"✅ 工單【{part_no} - {part_name}（工序：{process}）】已成功建立！")

# --- 5. 功能二：工單看板、多圖預覽與累計補傳 ---
elif menu == "📋 工單看板與修改":
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("目前尚無委外工單，請點選左上角「>」打開選單，選擇「➕ 新增委外工單」。")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.multiselect("依狀態篩選", df["status"].unique(), default=df["status"].unique())
        with col_f2:
            search_kw = st.text_input("🔍 搜尋料號、品名、廠商或工序")

        filtered_df = df[df["status"].isin(status_filter)]
        if search_kw:
            filtered_df = filtered_df[
                filtered_df["part_no"].str.contains(search_kw, case=False, na=False) |
                filtered_df["part_name"].str.contains(search_kw, case=False, na=False) |
                filtered_df["vendor"].str.contains(search_kw, case=False, na=False) |
                filtered_df["process"].str.contains(search_kw, case=False, na=False)
            ]

        # 將表格顯示欄位名稱轉換為中文（due_date 顯示為 發包日期）
        display_df = filtered_df[["id", "part_no", "part_name", "vendor", "process", "qty", "status", "due_date"]].rename(
            columns={
                "id": "工單ID",
                "part_no": "料號",
                "part_name": "品名",
                "vendor": "委外廠商",
                "process": "加工工序",
                "qty": "數量",
                "status": "目前狀態",
                "due_date": "發包日期"
            }
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔍 工單詳細資訊、多圖預覽與修改")
        if not filtered_df.empty:
            selected_id = st.selectbox(
                "請選擇要檢視或修改的工單：",
                filtered_df["id"].tolist(),
                format_func=lambda x: f"工單 #{x} | 料號: {filtered_df[filtered_df['id']==x]['part_no'].values[0]} | 品名: {filtered_df[filtered_df['id']==x]['part_name'].values[0]} ({filtered_df[filtered_df['id']==x]['vendor'].values[0]} - {filtered_df[filtered_df['id']==x]['process'].values[0]})"
            )

            if selected_id:
                row = filtered_df[filtered_df["id"] == selected_id].iloc[0]
                existing_imgs = parse_image_paths(row["image_path"])
                
                # --- 折疊式修改與補傳圖檔面板 ---
                with st.expander("✏️ 點此展開：修改工單內容 / 繼續追加多張照片 / 更換 CAD 檔"):
                    with st.form(f"edit_form_{selected_id}"):
                        ec1, ec2 = st.columns(2)
                        stat_list = ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"]

                        with ec1:
                            new_pno = st.text_input("修改料號", value=row["part_no"])
                            new_pname = st.text_input("修改品名", value=row["part_name"])
                            new_vendor = st.text_input("修改廠商", value=row["vendor"])
                            new_proc = st.text_input("修改加工工序 *(可直接打字修改)*", value=row["process"])
                        with ec2:
                            new_qty = st.number_input("修改數量", min_value=1, value=int(row["qty"]))
                            new_stat = st.selectbox("修改狀態", stat_list, index=stat_list.index(row["status"]) if row["status"] in stat_list else 0)
                            try:
                                default_date = datetime.strptime(row["due_date"], "%Y-%m-%d").date()
                            except:
                                default_date = datetime.today().date()
                            new_order_date = st.date_input("修改發包日期", value=default_date)
                            new_gdrive = st.text_input("修改 Google 雲端連結", value=row["gdrive_link"] if row["gdrive_link"] else "")

                        new_notes = st.text_area("修改備註", value=row["notes"] if row["notes"] else "")
                        
                        st.markdown("---")
                        st.markdown(f"**📸 補傳或管理照片（目前已有 {len(existing_imgs)} 張照片）**")
                        photo_mode = st.radio(
                            "上傳照片時的處理方式：",
                            ["➕ 追加新照片（保留原本的照片，繼續往上加）", "🔄 覆蓋全部照片（清空舊照片，只留這次新傳的）"],
                            horizontal=True
                        )
                        new_img_files = st.file_uploader("選擇要新增的照片 (可一次選多張 JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
                        
                        st.markdown("**📐 補傳或更換 CAD 圖檔（若不更換請留空）**")
                        new_cad_file = st.file_uploader("選擇新的 CAD 圖檔 (DXF/DWG)", type=["dxf", "dwg"])

                        if st.form_submit_button("💾 儲存所有修改與新檔案", type="primary"):
                            ts = datetime.now().strftime("%Y%m%d%H%M%S")
                            
                            if new_img_files:
                                newly_saved = []
                                for idx, img_f in enumerate(new_img_files):
                                    p = os.path.join(UPLOAD_DIR, f"{new_pno.strip()}_{ts}_{idx}_{img_f.name}")
                                    with open(p, "wb") as f:
                                        f.write(img_f.getbuffer())
                                    newly_saved.append(p)
                                
                                if "追加" in photo_mode:
                                    final_img_list = existing_imgs + newly_saved
                                else:
                                    final_img_list = newly_saved
                            else:
                                final_img_list = existing_imgs

                            updated_img_path_str = ";".join(final_img_list)

                            updated_cad_path = row["cad_path"]
                            if new_cad_file:
                                updated_cad_path = os.path.join(UPLOAD_DIR, f"{new_pno.strip()}_{ts}_{new_cad_file.name}")
                                with open(updated_cad_path, "wb") as f:
                                    f.write(new_cad_file.getbuffer())

                            conn = sqlite3.connect(DB_FILE)
                            conn.execute('''
                                UPDATE orders 
                                SET part_no=?, part_name=?, vendor=?, process=?, qty=?, status=?, due_date=?, gdrive_link=?, image_path=?, cad_path=?, notes=?
                                WHERE id=?
                            ''', (new_pno.strip(), new_pname.strip(), new_vendor.strip(), new_proc.strip(), new_qty, new_stat, str(new_order_date), new_gdrive, updated_img_path_str, updated_cad_path, new_notes, int(selected_id)))
                            conn.commit()
                            conn.close()
                            st.success("✅ 工單資料與照片已成功更新！")
                            st.rerun()

                # --- 顯示目前工單資訊與預覽 ---
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.write(f"**料號：** {row['part_no']} | **品名：** {row['part_name']}")
                    st.write(f"**廠商：** {row['vendor']} | **工序：** {row['process']} | **數量：** {row['qty']}")
                    st.write(f"**目前狀態：** `{row['status']}` | **📅 發包日期：** {row['due_date']}")
                    st.write(f"**備註：** {row['notes']}")

                    if row.get("gdrive_link"):
                        st.link_button("📂 點擊開啟 Google 雲端硬碟圖檔/資料夾", row["gdrive_link"])

                    if st.button("🗑️ 刪除此整筆工單"):
                        conn = sqlite3.connect(DB_FILE)
                        conn.execute("DELETE FROM orders WHERE id = ?", (int(selected_id),))
                        conn.commit()
                        conn.close()
                        st.warning("工單已刪除！")
                        st.rerun()

                    st.markdown(f"#### 📸 實體/檢驗照片相簿 (共 {len(existing_imgs)} 張)")
                    if existing_imgs:
                        img_cols = st.columns(2)
                        for idx, img_p in enumerate(existing_imgs):
                            with img_cols[idx % 2]:
                                st.image(Image.open(img_p), caption=f"照片 #{idx+1} ({os.path.basename(img_p)})", use_container_width=True)
                                if st.button(f"❌ 刪除照片 #{idx+1}", key=f"del_img_{selected_id}_{idx}"):
                                    remaining = [p for i, p in enumerate(existing_imgs) if i != idx]
                                    conn = sqlite3.connect(DB_FILE)
                                    conn.execute("UPDATE orders SET image_path=? WHERE id=?", (";".join(remaining), int(selected_id)))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
                    else:
                        st.caption("尚未上傳照片（可點上方「✏️ 修改工單內容」一次選多張或陸續追加補傳）")

                with c2:
                    st.markdown("#### 📐 CAD 圖面預覽")
                    if row["cad_path"] and os.path.exists(row["cad_path"]):
                        with open(row["cad_path"], "rb") as f:
                            st.download_button("⬇️ 下載 CAD 檔", data=f, file_name=os.path.basename(row["cad_path"]))
                        
                        if row["cad_path"].lower().endswith(".dxf"):
                            with st.spinner("正在渲染 CAD 圖面..."):
                                fig = render_dxf(row["cad_path"])
                                if fig:
                                    st.pyplot(fig)
                        else:
                            st.info("💡 DWG 檔可供下載，或建議搭配左側「Google 雲端硬碟連結」直接調閱雲端圖檔。")
                    else:
                        st.caption("尚未上傳 CAD 檔（可點上方「✏️ 修改工單內容」補傳）")

# --- 6. 功能三：備份至手機 Google 雲端硬碟 ---
elif menu == "☁️ Google雲端備份/還原":
    st.subheader("☁️ 將工單資料存回您的 Google 雲端硬碟")
    st.write("您可以隨時將所有工單匯出成 CSV (Excel 格式)，手機下載後可直接選擇**「儲存至 Google 雲端硬碟」**永久保存。")
    
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()

    if not df.empty:
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載全部工單報表 (可存至 Google 雲端硬碟 / Excel)",
            data=csv_data,
            file_name="委外加工工單備份.csv",
            mime="text/csv"
        )
    else:
        st.info("目前尚無資料可供備份。")

    st.markdown("---")
    st.subheader("🔄 從 Google 雲端硬碟還原工單")
    uploaded_csv = st.file_uploader("選擇備份的 CSV 檔案", type=["csv"])
    if uploaded_csv is not None:
        if st.button("🚀 立即還原工單資料"):
            restore_df = pd.read_csv(uploaded_csv)
            conn = sqlite3.connect(DB_FILE)
            restore_df.to_sql("orders", conn, if_exists="replace", index=False)
            conn.close()
            st.success("✅ 所有工單資料已成功還原！")
