import streamlit as st
import sqlite3
import pandas as pd
import os
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
st.set_page_config(page_title="委外加工追蹤系統", layout="wide")
st.title("🏭 工業委外加工追蹤系統")

menu = st.sidebar.radio("功能選單", ["📋 工單看板與預覽", "➕ 新增委外工單", "☁️ Google雲端備份/還原"])

# --- 4. 功能一：新增委外工單 ---
if menu == "➕ 新增委外工單":
    st.subheader("建立新委外加工單")
    with st.form("order_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            part_no = st.text_input("料號 / 圖號 *")
            part_name = st.text_input("品名 / 零件名稱 *")
            vendor = st.text_input("委外廠商名稱 *")
            process = st.selectbox("加工工序", ["車床", "銑床", "CNC複合", "熱處理", "表面處理/電鍍", "雷射切割", "其他"])
        with col2:
            qty = st.number_input("數量", min_value=1, value=1)
            status = st.selectbox("目前狀態", ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"])
            due_date = st.date_input("預計交期")
            notes = st.text_area("加工備註 / 注意事項")

        st.markdown("---")
        st.write("📎 **連結您的 Google 雲端硬碟 或 直接上傳檔案**")
        gdrive_link = st.text_input("🔗 Google 雲端硬碟連結 (可貼上該零件的 DWG 圖檔或資料夾共用連結)")
        img_file = st.file_uploader("📸 直接拍照或上傳零件照片 (JPG/PNG)", type=["jpg", "jpeg", "png"])
        cad_file = st.file_uploader("📐 上傳 CAD 圖檔線上預覽 (支援 DXF 直接畫出圖面，DWG 可暫存)", type=["dxf", "dwg"])

        submitted = st.form_submit_button("💾 儲存工單")
        if submitted:
            if not part_no or not vendor:
                st.warning("請填寫「料號」與「委外廠商名稱」！")
            else:
                img_path, cad_path = "", ""
                if img_file:
                    img_path = os.path.join(UPLOAD_DIR, f"{part_no}_{img_file.name}")
                    with open(img_path, "wb") as f:
                        f.write(img_file.getbuffer())
                if cad_file:
                    cad_path = os.path.join(UPLOAD_DIR, f"{part_no}_{cad_file.name}")
                    with open(cad_path, "wb") as f:
                        f.write(cad_file.getbuffer())

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO orders (part_no, part_name, vendor, process, qty, status, due_date, gdrive_link, image_path, cad_path, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (part_no, part_name, vendor, process, qty, status, str(due_date), gdrive_link, img_path, cad_path, notes))
                conn.commit()
                conn.close()
                st.success(f"✅ 工單【{part_no} - {part_name}】已成功建立！")

# --- 5. 功能二：工單看板與圖面預覽 ---
elif menu == "📋 工單看板與預覽":
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
            search_kw = st.text_input("🔍 搜尋料號、品名或廠商")

        filtered_df = df[df["status"].isin(status_filter)]
        if search_kw:
            filtered_df = filtered_df[
                filtered_df["part_no"].str.contains(search_kw, case=False, na=False) |
                filtered_df["part_name"].str.contains(search_kw, case=False, na=False) |
                filtered_df["vendor"].str.contains(search_kw, case=False, na=False)
            ]

        st.dataframe(filtered_df[["id", "part_no", "part_name", "vendor", "process", "qty", "status", "due_date"]], use_container_width=True)

        st.markdown("---")
        st.subheader("🔍 工單詳細資訊與圖面預覽")
        if not filtered_df.empty:
            selected_id = st.selectbox(
                "選擇要檢視或更新的工單",
                filtered_df["id"].tolist(),
                format_func=lambda x: f"工單 #{x} - {filtered_df[filtered_df['id']==x]['part_no'].values[0]} ({filtered_df[filtered_df['id']==x]['part_name'].values[0]})"
            )

            if selected_id:
                row = filtered_df[filtered_df["id"] == selected_id].iloc[0]
                c1, c2 = st.columns([1, 1])

                with c1:
                    st.write(f"**料號：** {row['part_no']} | **品名：** {row['part_name']}")
                    st.write(f"**廠商：** {row['vendor']} | **工序：** {row['process']} | **數量：** {row['qty']}")
                    st.write(f"**預計交期：** {row['due_date']}")
                    st.write(f"**備註：** {row['notes']}")

                    if row.get("gdrive_link"):
                        st.link_button("📂 點擊開啟 Google 雲端硬碟圖檔/資料夾", row["gdrive_link"])

                    status_list = ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"]
                    curr_idx = status_list.index(row["status"]) if row["status"] in status_list else 0
                    new_status = st.selectbox("更新進度狀態", status_list, index=curr_idx)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("🔄 更新狀態"):
                            conn = sqlite3.connect(DB_FILE)
                            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, int(selected_id)))
                            conn.commit()
                            conn.close()
                            st.success("狀態已更新！")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ 刪除此工單"):
                            conn = sqlite3.connect(DB_FILE)
                            conn.execute("DELETE FROM orders WHERE id = ?", (int(selected_id),))
                            conn.commit()
                            conn.close()
                            st.warning("工單已刪除！")
                            st.rerun()

                    if row["image_path"] and os.path.exists(row["image_path"]):
                        st.markdown("#### 📸 實體/檢驗照片")
                        st.image(Image.open(row["image_path"]), use_container_width=True)

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
                        st.write("未直接上傳 CAD 檔（若已附 Google 雲端連結，請點左側按鈕開啟）")

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
    st.write("如果系統休眠重啟過，請從您的 Google 雲端硬碟選擇之前備份的 `委外加工工單備份.csv` 上傳即可一鍵還原：")
    uploaded_csv = st.file_uploader("選擇備份的 CSV 檔案", type=["csv"])
    if uploaded_csv is not None:
        if st.button("🚀 立即還原工單資料"):
            restore_df = pd.read_csv(uploaded_csv)
            conn = sqlite3.connect(DB_FILE)
            restore_df.to_sql("orders", conn, if_exists="replace", index=False)
            conn.close()
            st.success("✅ 所有工單資料已成功還原！")
