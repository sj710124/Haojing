import streamlit as st
import pandas as pd
import os
import time
import urllib.request
from PIL import Image
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
from supabase import create_client, Client

# --- 1. 連接 Supabase 雲端資料庫 ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
BUCKET_NAME = "files"

# --- 2. 雲端 CAD (DXF) 轉圖片預覽函數 ---
def render_dxf_from_url(dxf_url):
    try:
        # 先將雲端 DXF 下載到暫存區進行解析繪圖
        temp_path = "temp_preview.dxf"
        urllib.request.urlretrieve(dxf_url, temp_path)
        doc = ezdxf.readfile(temp_path)
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

# --- 3. 檔案上傳至雲端函數 ---
def upload_to_cloud(file_obj, part_no):
    if not file_obj:
        return ""
    ext = os.path.splitext(file_obj.name)[1].lower()
    # 使用時間戳記命名，避免中文檔名亂碼或重複覆蓋
    cloud_filename = f"{int(time.time())}_{ext}"
    file_bytes = file_obj.getvalue()
    
    supabase.storage.from_(BUCKET_NAME).upload(
        path=cloud_filename,
        file=file_bytes,
        file_options={"content-type": file_obj.type}
    )
    return supabase.storage.from_(BUCKET_NAME).get_public_url(cloud_filename)

# --- 4. 網頁介面設定 ---
st.set_page_config(page_title="委外加工雲端系統", layout="wide")
st.title("🏭 工業委外加工追蹤系統 (雲端永久版)")

menu = st.sidebar.radio("功能選單", ["📋 工單看板與預覽", "➕ 新增委外工單"])

# --- 5. 功能一：新增委外工單 ---
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
        st.write("📎 **上傳圖面與照片（自動永久備份至雲端）**")
        img_file = st.file_uploader("上傳零件照片或檢驗圖 (JPG/PNG)", type=["jpg", "jpeg", "png"])
        cad_file = st.file_uploader("上傳 CAD 圖檔 (支援 DXF 線上預覽，DWG 雲端備份下載)", type=["dxf", "dwg"])

        submitted = st.form_submit_button("☁️ 儲存至雲端")
        if submitted:
            if not part_no or not vendor:
                st.warning("請填寫「料號」與「委外廠商名稱」！")
            else:
                with st.spinner("正在上傳圖檔與寫入雲端資料庫..."):
                    img_url = upload_to_cloud(img_file, part_no)
                    cad_url = upload_to_cloud(cad_file, part_no)

                    data = {
                        "part_no": part_no,
                        "part_name": part_name,
                        "vendor": vendor,
                        "process": process,
                        "qty": qty,
                        "status": status,
                        "due_date": str(due_date),
                        "image_url": img_url,
                        "cad_url": cad_url,
                        "notes": notes
                    }
                    supabase.table("orders").insert(data).execute()
                    st.success(f"工單【{part_no} - {part_name}】已永久儲存至雲端！")

# --- 6. 功能二：工單看板與圖面預覽 ---
elif menu == "📋 工單看板與預覽":
    response = supabase.table("orders").select("*").order("id", desc=True).execute()
    df = pd.DataFrame(response.data)

    if df.empty:
        st.info("目前雲端尚無委外工單，請從左側選單新增。")
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

                    status_list = ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"]
                    curr_idx = status_list.index(row["status"]) if row["status"] in status_list else 0
                    new_status = st.selectbox("更新進度狀態", status_list, index=curr_idx)
                    
                    if st.button("更新雲端狀態"):
                        supabase.table("orders").update({"status": new_status}).eq("id", int(selected_id)).execute()
                        st.success("狀態已更新！")
                        st.rerun()

                    if row.get("image_url"):
                        st.markdown("#### 📸 實體/檢驗照片")
                        st.image(row["image_url"], use_container_width=True)

                with c2:
                    st.markdown("#### 📐 CAD 圖面預覽與下載")
                    cad_url = row.get("cad_url", "")
                    if cad_url:
                        st.link_button("⬇️ 點擊下載原始 CAD 檔", cad_url)
                        if cad_url.lower().endswith(".dxf"):
                            with st.spinner("正在從雲端讀取並渲染 CAD 圖面..."):
                                fig = render_dxf_from_url(cad_url)
                                if fig:
                                    st.pyplot(fig)
                        else:
                            st.info("💡 此為 DWG 檔，已安全備份於雲端，可點擊上方按鈕下載。若需在手機網頁直接顯示線條預覽，上傳時請選擇 DXF 格式。")
                    else:
                        st.write("未上傳 CAD 圖檔")
