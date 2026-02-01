import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import jpholiday
import plotly.express as px

# ==========================================
# 1. 設定 & 定数
# ==========================================
st.set_page_config(page_title="ポケカ資産管理", layout="wide", page_icon="🃏")

# PSAプラン設定
PSA_JAPAN_PLANS = {
    "Value":      {"business_days": 45, "price": 3980},
    "ValuePlus":  {"business_days": 20, "price": 6980},
    "Regular":    {"business_days": 10, "price": 9980},
    "Express":    {"business_days": 10, "price": 16980},
}

# 必須カラムの定義（エラー防止用）
REQUIRED_COLUMNS = [
    "name", "model", "p_date", "p_price", 
    "psa_plan", "sub_date", "psa_cost", "ret_date", 
    "status", "sale_date", "sale_price", "memo"
]

# ==========================================
# 2. 関数群
# ==========================================
def add_business_days(start_date, days_to_add):
    """営業日計算"""
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
    """PSA鑑定の返却予定日とコストを計算"""
    if plan_name not in PSA_JAPAN_PLANS:
        return {"cost": 0, "return_date": None}
    
    # 3週間の待機期間 + 営業日計算
    processing_start = arrival_date + datetime.timedelta(weeks=3)
    req_days = PSA_JAPAN_PLANS[plan_name]["business_days"]
    return_date = add_business_days(processing_start, req_days)
    return {"cost": PSA_JAPAN_PLANS[plan_name]["price"], "return_date": return_date}

def ensure_columns(df):
    """必須カラムが不足している場合に補完し、型変換を行う"""
    # カラム不足の解消
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col not in ["p_price", "psa_cost", "sale_price"] else 0

    # 数値型への変換（エラー回避）
    num_cols = ['p_price', 'psa_cost', 'sale_price']
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 日付型への変換（表示用）
    date_cols = ['p_date', 'sub_date', 'ret_date', 'sale_date']
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # 不要なカラム（Unnamedなど）を除去し、定義順に並べ替え
    return df[REQUIRED_COLUMNS]

# ==========================================
# 3. データ接続
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    """データを読み込み、前処理を行う"""
    try:
        # worksheetを指定せず、1枚目のシートを読み込む（エラー回避）
        df = conn.read()
        return ensure_columns(df)
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

def update_data(df):
    """データフレーム全体をスプレッドシートに書き込む"""
    try:
        # 日付型を文字列に戻して保存（JSONシリアライズ対策）
        save_df = df.copy()
        date_cols = ['p_date', 'sub_date', 'ret_date', 'sale_date']
        for col in date_cols:
            save_df[col] = save_df[col].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else "")
            
        conn.update(data=save_df)
        st.toast("✅ データを更新しました！", icon="💾")
        st.cache_data.clear() # キャッシュクリア
    except Exception as e:
        st.error(f"保存エラー: {e}")

# ==========================================
# 4. アプリ画面構成
# ==========================================
menu = st.sidebar.radio("メニュー", ["📊 ダッシュボード", "📝 カード登録", "🗂 管理リスト(編集)"])

# データをロード
df = load_data()

# 利益などの計算列を追加（表示用）
df['total_cost'] = df['p_price'] + df['psa_cost']
df['profit'] = df['sale_price'] - df['total_cost']
# 売却済の場合は利益、未売却の場合は「-」
df['profit_display'] = df.apply(lambda x: x['profit'] if x['sale_price'] > 0 else 0, axis=1)


if menu == "📊 ダッシュボード":
    st.title("📊 資産運用ダッシュボード")
    
    if not df.empty:
        # --- KPIエリア ---
        col1, col2, col3 = st.columns(3)
        
        # 保有資産（売却済以外）
        holding_df = df[df['status'] != '売却済']
        current_assets = holding_df['total_cost'].sum()
        
        # 確定利益（売却済のみ）
        sold_df = df[df['status'] == '売却済']
        realized_profit = sold_df['profit'].sum()
        roi = (realized_profit / sold_df['total_cost'].sum() * 100) if not sold_df.empty else 0

        col1.metric("📦 保有資産総額 (原価)", f"¥{current_assets:,.0f}")
        col2.metric("💰 確定利益", f"¥{realized_profit:,.0f}", delta=f"ROI {roi:.1f}%")
        col3.metric("🃏 保有枚数", f"{len(holding_df)}枚")

        st.divider()

        # --- グラフエリア ---
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("ステータス別 内訳")
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['status', 'count']
            fig_pie = px.pie(status_counts, values='count', names='status', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with c2:
            st.subheader("高額カード TOP5 (取得額)")
            top5 = holding_df.nlargest(5, 'total_cost')
            if not top5.empty:
                fig_bar = px.bar(top5, x='name', y='total_cost', color='model', title="保有カード原価")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("保有中のカードがありません")

    else:
        st.info("データがまだありません。「カード登録」から追加してください。")


elif menu == "📝 カード登録":
    st.title("📝 新規カード登録")
    
    with st.form("input_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("カード名", placeholder="例：リザードンVMAX")
            model = st.text_input("型番", placeholder="例：S4a 308/190")
            p_date = st.date_input("購入日", datetime.date.today())
            p_price = st.number_input("購入金額 (円)", min_value=0, step=100)
        
        with c2:
            use_psa = st.checkbox("PSA鑑定に出す", value=False)
            if use_psa:
                psa_plan = st.selectbox("PSAプラン", list(PSA_JAPAN_PLANS.keys()))
                sub_date = st.date_input("PSA日本支社到着日", datetime.date.today())
            else:
                psa_plan = None
                sub_date = None
            
            memo = st.text_area("メモ", height=100)

        submitted = st.form_submit_button("登録する", use_container_width=True)

        if submitted:
            if not name:
                st.error("カード名は必須です")
            else:
                # PSA計算
                psa_res = {"cost":0, "return_date":None}
                status = "所有中"
                
                if use_psa:
                    psa_res = calculate_psa(sub_date, psa_plan)
                    status = "鑑定中"
                
                # 新規データ作成
                new_row = {
                    "name": name, 
                    "model": model,
                    "p_date": p_date, # 保存時に文字列化
                    "p_price": p_price,
                    "psa_plan": psa_plan if use_psa else "",
                    "sub_date": sub_date if use_psa else None,
                    "psa_cost": psa_res["cost"],
                    "ret_date": psa_res["return_date"],
                    "status": status,
                    "sale_date": None,
                    "sale_price": 0,
                    "memo": memo
                }
                
                # データフレームに追加して保存
                new_df = pd.DataFrame([new_row])
                # 既存データと結合するために型合わせ
                combined_df = pd.concat([df, ensure_columns(new_df)], ignore_index=True)
                
                update_data(combined_df)
                st.success(f"「{name}」を登録しました！")


elif menu == "🗂 管理リスト(編集)":
    st.title("🗂 データ管理・編集")
    st.caption("👇 表のセルをダブルクリックすると直接編集できます。「売却済」にする場合はステータスを変更し、売値を入れてください。")

    # 編集用データフレーム設定
    edited_df = st.data_editor(
        df,
        num_rows="dynamic", # 行の追加・削除を許可
        column_config={
            "p_price": st.column_config.NumberColumn("購入額", format="¥%d"),
            "psa_cost": st.column_config.NumberColumn("鑑定料", format="¥%d"),
            "sale_price": st.column_config.NumberColumn("売却額", format="¥%d"),
            "p_date": st.column_config.DateColumn("購入日"),
            "ret_date": st.column_config.DateColumn("返却予定"),
            "sub_date": st.column_config.DateColumn("提出日"),
            "sale_date": st.column_config.DateColumn("売却日"),
            "status": st.column_config.SelectboxColumn(
                "状態",
                options=["所有中", "鑑定中", "PSA提出準備", "売却済", "紛失/破損"],
                required=True
            ),
            "profit": st.column_config.NumberColumn("想定利益", format="¥%d", disabled=True), # 計算結果は編集不可
            "profit_display": None, # 表示用の一時カラムは隠す
            "total_cost": None      # 表示用の一時カラムは隠す
        },
        use_container_width=True,
        hide_index=True
    )

    # 保存ボタン
    if st.button("💾 変更を保存する", type="primary"):
        # 計算列を除外して保存
        columns_to_save = [c for c in edited_df.columns if c in REQUIRED_COLUMNS]
        final_df = edited_df[columns_to_save]
        
        update_data(final_df)
