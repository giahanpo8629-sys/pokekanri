import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import jpholiday

# ==========================================
# 1. 設定 & 関数
# ==========================================
st.set_page_config(page_title="ポケカ資産管理", layout="wide")

# PSAプラン設定
psa_japan_plans = {
    "Value":      {"business_days": 45, "price": 3980},
    "ValuePlus":     {"business_days": 20, "price": 6980},
    "Regular":   {"business_days": 10, "price": 9980},
    "Express":   {"business_days": 10, "price": 16980},
}

def add_business_days(start_date, days_to_add):
    current_date = start_date
    added_days = 0
    while added_days < days_to_add:
        current_date += datetime.timedelta(days=1)
        is_weekend = current_date.weekday() >= 5
        is_holiday = jpholiday.is_holiday(current_date)
        if not is_weekend and not is_holiday:
            added_days += 1
    return current_date

def calculate_psa(arrival_date, plan_name):
    if plan_name not in psa_japan_plans: return {"cost":0, "return_date":None}
    # 3週間の待機期間 + 営業日計算
    processing_start = arrival_date + datetime.timedelta(weeks=3)
    req_days = psa_japan_plans[plan_name]["business_days"]
    return_date = add_business_days(processing_start, req_days)
    return {"cost": psa_japan_plans[plan_name]["price"], "return_date": return_date}

# ==========================================
# 2. スプレッドシート接続
# ==========================================
# st.connectionを使ってスプレッドシートに接続
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # データを読み込む (キャッシュ対策でttl=0にする場合もあるが、基本はこれ)
    return conn.read(worksheet="Sheet1")

def save_data(new_row_df):
    # 現在のデータを読み込み
    df = load_data()
    # 新しい行を追加して更新
    updated_df = pd.concat([df, new_row_df], ignore_index=True)
    conn.update(worksheet="Sheet1", data=updated_df)

# ==========================================
# 3. アプリ画面
# ==========================================
menu = st.sidebar.radio("メニュー", ["📊 ダッシュボード", "📝 カード登録", "🗂 リスト"])

if menu == "📊 ダッシュボード":
    st.title("📊 資産運用ダッシュボード")
    df = load_data()
    
    if not df.empty and 'p_price' in df.columns:
        # 数値変換(エラー回避)
        df['p_price'] = pd.to_numeric(df['p_price'], errors='coerce').fillna(0)
        df['psa_cost'] = pd.to_numeric(df['psa_cost'], errors='coerce').fillna(0)
        df['sale_price'] = pd.to_numeric(df['sale_price'], errors='coerce').fillna(0)
        
        # 計算
        df['total_cost'] = df['p_price'] + df['psa_cost']
        df['profit'] = df['sale_price'] - df['total_cost']

        # KPI
        current_assets = df[df['status'] != '売却済']['total_cost'].sum()
        sold_df = df[df['status'] == '売却済']
        total_profit = sold_df['profit'].sum()

        c1, c2 = st.columns(2)
        c1.metric("📦 保有資産(簿価)", f"¥{current_assets:,.0f}")
        c2.metric("💰 確定利益", f"¥{total_profit:,.0f}")
        
        st.divider()
        st.caption("※データはGoogleスプレッドシートから読み込んでいます")

    else:
        st.info("データがまだありません")

elif menu == "📝 カード登録":
    st.title("📝 新規カード登録")
    with st.form("input_form"):
        name = st.text_input("カード名")
        model = st.text_input("型番")
        p_date = st.date_input("購入日", datetime.date.today())
        p_price = st.number_input("購入金額", min_value=0, step=100)
        
        use_psa = st.checkbox("PSA鑑定あり")
        psa_plan = st.selectbox("プラン", list(psa_japan_plans.keys()))
        sub_date = st.date_input("PSA到着日", datetime.date.today())
        
        submitted = st.form_submit_button("登録")

        if submitted:
            # PSA計算
            psa_res = {"cost":0, "return_date":None}
            status = "所有中"
            
            if use_psa:
                psa_res = calculate_psa(sub_date, psa_plan)
                status = "鑑定中"
            
            # データフレーム作成
            new_data = pd.DataFrame([{
                "name": name, "model": model,
                "p_date": p_date.strftime('%Y-%m-%d'),
                "p_price": p_price,
                "psa_plan": psa_plan if use_psa else "",
                "sub_date": sub_date.strftime('%Y-%m-%d') if use_psa else "",
                "psa_cost": psa_res["cost"],
                "ret_date": psa_res["return_date"].strftime('%Y-%m-%d') if psa_res["return_date"] else "",
                "status": status,
                "sale_date": "", "sale_price": 0
            }])
            
            save_data(new_data)
            st.success("スプレッドシートに保存しました！")

elif menu == "🗂 リスト":
    st.title("🗂 登録データ一覧")
    df = load_data()
    st.dataframe(df)

    st.info("データの修正・削除はGoogleスプレッドシート側で行ってください。")
