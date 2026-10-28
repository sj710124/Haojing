import streamlit as st
import pandas as pd
import os
import io
import base64
import requests
from datetime import datetime
from PIL import Image
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt

API_URL = st.secrets.get("GSHEET_API_URL", "")
COLUMNS = ["id", "part_no", "part_name", "vendor", "process", "qty", "status", "due_date", "gdrive_link", "image_path", "notes"]

def load_data():
    if not API_URL:
        return pd.DataFrame(columns=COLUMNS)
    try:
        resp = requests.get(API_URL, timeout=10)
        data = resp.json()
        if len(data) <= 1:
            return pd.DataFrame(columns=COLUMNS)
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[COLUMNS].fillna("")
    except Exception as e:
        st.error(f"讀取 Google 試算表失敗: {e}")
        return pd.DataFrame(columns=COLUMNS)

def save_data(df):
    if not API_URL:
        st.error("尚未設定 GSHEET_API_URL！請檢查 Streamlit Secrets。")
        return False
    try:
        df_clean = df[COLUMNS].copy().fillna("")
        df_clean["id"] = df_clean["id"].astype(str)
        df_clean["qty"] = df_clean["qty"].astype(str)
        
        all_data = [COLUMNS] + df_clean.values.tolist()
        payload = {
            "action": "update_all",
            "data": all_data
        }
        resp = requests.post(API_URL, json=payload, timeout=20)
        res_json = resp.json()
        return res_json.get("status") == "success"
    except Exception as e:
        st.error(f"寫入 Google 試算表失敗: {e}")
        return False

def safe_str(val):
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def encode_image_to_b64(file_obj):
    try:
        img = Image.open(file_obj)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"
    except Exception:
        return ""

def parse_images(img_str):
    s = safe_str(img_str)
    if not s:
        return []
    items = [p.strip() for p in s.split("|") if p.strip()]
    return [p for p in items if p.startswith("data:image")]

def display_stored_image(img_item):
    b64_data = img_item.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64_data)))

def get_history_options(df, col_name, default_list=None):
    if df.empty or col_name not in df.columns:
        return default_list if default_list else []
    db_items = [safe_str(x) for x in df[col_name].dropna().unique() if safe_str(x)]
    if default_list:
        return list(dict.fromkeys(db_items + default_list))
    return db_items

st.set_page_config(page_title="委外加工追蹤系統", layout="wide")
st.title("🏭 工業委外加工追蹤系統 (Google 雲端版)")

menu = st.sidebar.radio("功能選單", ["📋 工單看板與修改", "➕ 新增委外工單"])

DEFAULT_PROCS = ["車床", "銑床", "CNC複合", "熱處理", "表面處理/電鍍", "雷射切割", "線切割", "研磨"]
STAT_LIST = ["待發包", "加工中", "表面處理中", "待品檢", "已完工入庫", "異常處理中"]

df = load_data()

if menu == "➕ 新增委外工單":
    st.subheader("建立新委外加工單")
    st.caption("☁️ 工單直接同步至 Google 雲端試算表，隨時自動保存。")

    hist_pnos = get_history_options(df, "part_no")
    hist_pnames = get_history_options(df, "part_name")
    hist_vendors = get_history_options(df, "vendor")
    hist_procs = get_history_options(df, "process", DEFAULT_PROCS)

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
    st.write("📎 **上傳圖面與照片**")
    gdrive_link = st.text_input("🔗 Google 雲端硬碟圖檔連結 (可直接貼 DWG 檔案分享網址)", key=f"gd_{rk}")
    img_files = st.file_uploader("📸 拍照或上傳照片 (可選多張 JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"img_{rk}")

    if st.button("💾 儲存建立工單", type="primary", use_container_width=True):
        if not part_no.strip() or not vendor.strip() or not process.strip():
            st.error("⚠️ 請確認「料號」、「委外廠商名稱」與「加工工序」皆已填寫！")
        else:
            with st.spinner("正在將工單寫入 Google 雲端試算表..."):
                encoded_imgs = []
                if img_files:
                    for img_f in img_files:
                        b64_img = encode_image_to_b64(img_f)
                        if b64_img:
                            encoded_imgs.append(b64_img)
                img_data_str = "|".join(encoded_imgs)

                new_id = 1 if df.empty else (pd.to_numeric(df["id"], errors="coerce").max() + 1)
                new_row = {
                    "id": str(int(new_id)),
                    "part_no": part_no.strip(),
                    "part_name": part_name.strip(),
                    "vendor": vendor.strip(),
                    "process": process.strip(),
                    "qty": str(qty),
                    "status": status,
                    "due_date": str(order_date),
                    "gdrive_link": gdrive_link.strip(),
                    "image_path": img_data_str,
                    "notes": notes.strip()
                }
                updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                if save_data(updated_df):
                    st.success(f"✅ 工單【{part_no} - {part_name}】已成功同步至 Google 雲端！")
                    st.rerun()

elif menu == "📋 工單看板與修改":
    if df.empty:
        st.info("目前 Google 雲端尚無委外工單，請從左側選單選擇「➕ 新增委外工單」。")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            valid_stats = [x for x in df["status"].unique() if safe_str(x)]
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
        st.subheader("🔍 工單詳細資訊與修改")
        if not filtered_df.empty:
            def fmt_order(x):
                r = filtered_df[filtered_df["id"] == str(x)].iloc[0]
                return f"工單 #{x} | 料號: {safe_str(r.get('part_no'))} | 品名: {safe_str(r.get('part_name'))} ({safe_str(r.get('vendor'))})"

            selected_id = st.selectbox("請選擇要檢視或修改的工單：", filtered_df["id"].tolist(), format_func=fmt_order)

            if selected_id:
                row = filtered_df[filtered_df["id"] == str(selected_id)].iloc[0]
                existing_imgs = parse_images(row.get("image_path"))
                gdrive_val = safe_str(row.get("gdrive_link"))
                notes_val = safe_str(row.get("notes"))

                with st.expander("✏️ 點此展開：修改工單內容 / 追加照片"):
                    with st.form(f"edit_form_{selected_id}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            new_pno = st.text_input("修改料號", value=safe_str(row.get("part_no")))
                            new_pname = st.text_input("修改品名", value=safe_str(row.get("part_name")))
                            new_vendor = st.text_input("修改廠商", value=safe_str(row.get("vendor")))
                            new_proc = st.text_input("修改加工工序", value=safe_str(row.get("process")))
                        with ec2:
                            raw_qty = row.get("qty")
                            q_val = int(raw_qty) if str(raw_qty).isdigit() else 1
                            new_qty = st.number_input("修改數量", min_value=1, value=q_val)
                            curr_st = safe_str(row.get("status"))
                            st_idx = STAT_LIST.index(curr_st) if curr_st in STAT_LIST else 0
                            new_stat = st.selectbox("修改狀態", STAT_LIST, index=st_idx)
                            try:
                                def_date = datetime.strptime(safe_str(row.get("due_date")), "%Y-%m-%d").date()
                            except Exception:
                                def_date = datetime.today().date()
                            new_order_date = st.date_input("修改發包日期", value=def_date)
                            new_gdrive = st.text_input("修改 Google 雲端連結", value=gdrive_val)

                        new_notes = st.text_area("修改備註", value=notes_val)
                        new_img_files = st.file_uploader("追加上傳新照片 (JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

                        if st.form_submit_button("💾 儲存修改至 Google 雲端", type="primary"):
                            with st.spinner("正在更新 Google 試算表..."):
                                if new_img_files:
                                    newly_encoded = [encode_image_to_b64(f) for f in new_img_files]
                                    final_imgs = existing_imgs + [x for x in newly_encoded if x]
                                else:
                                    final_imgs = existing_imgs

                                row_idx = df[df["id"] == str(selected_id)].index[0]
                                df.at[row_idx, "part_no"] = new_pno.strip()
                                df.at[row_idx, "part_name"] = new_pname.strip()
                                df.at[row_idx, "vendor"] = new_vendor.strip()
                                df.at[row_idx, "process"] = new_proc.strip()
                                df.at[row_idx, "qty"] = str(new_qty)
                                df.at[row_idx, "status"] = new_stat
                                df.at[row_idx, "due_date"] = str(new_order_date)
                                df.at[row_idx, "gdrive_link"] = new_gdrive.strip()
                                df.at[row_idx, "image_path"] = "|".join(final_imgs)
                                df.at[row_idx, "notes"] = new_notes.strip()

                                if save_data(df):
                                    st.success("✅ Google 雲端資料已同步更新！")
                                    st.rerun()

                c1, c2 = st.columns([1, 1])
                with c1:
                    st.write(f"**料號：** {safe_str(row.get('part_no'))} | **品名：** {safe_str(row.get('part_name'))}")
                    st.write(f"**廠商：** {safe_str(row.get('vendor'))} | **工序：** {safe_str(row.get('process'))} | **數量：** {row.get('qty')}")
                    st.write(f"**目前狀態：** `{safe_str(row.get('status'))}` | **📅 發包日期：** {safe_str(row.get('due_date'))}")
                    st.write(f"**備註：** {notes_val if notes_val else '無'}")

                    if gdrive_val:
                        st.link_button("📂 開啟 Google 雲端硬碟圖檔", gdrive_val)

                    if st.button("🗑️ 刪除此工單"):
                        with st.spinner("正在從 Google 試算表刪除..."):
                            df = df[df["id"] != str(selected_id)]
                            if save_data(df):
                                st.warning("工單已刪除！")
                                st.rerun()

                with c2:
                    st.markdown(f"#### 📸 照片相簿 (共 {len(existing_imgs)} 張)")
                    if existing_imgs:
                        img_cols = st.columns(2)
                        for idx, img_item in enumerate(existing_imgs):
                            with img_cols[idx % 2]:
                                st.image(display_stored_image(img_item), caption=f"照片 #{idx+1}", use_container_width=True)
                    else:
                        st.caption("尚未上傳照片")
