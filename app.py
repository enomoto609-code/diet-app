import streamlit as st
from google import genai
from google.genai import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from PIL import Image
import datetime

# 1. ページ設定（スマホで見やすいレイアウト）
st.set_page_config(
    page_title="食事管理・栄養分析アプリ",
    page_icon="🥗",
    layout="centered"
)

st.title("🥗 食事記録 ＆ 栄養分析")
st.write("食事の写真を撮影またはアップロードして、AI分析とスプレッドシート記録を行います。")

# 2. 秘密情報（APIキー）の読み込み設定
# ※ローカルでテストする際は、st.secretsの代わりにサイドバー等で入力を受け付けるか、
# 後述する .streamlit/secrets.toml を使いますが、まずはコード内に直接設定してテストすることも可能です。
# （後ほどクラウドに上げる際はSecrets機能に移行します）

# ここでは、StreamlitのSecrets、または安全な読み込みのための下準備を行います
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    GEMINI_API_KEY = st.sidebar.text_input("Gemini APIキーを入力", type="password")

# 3. 写真のアップロード（スマホのカメラ起動・ライブラリ選択に対応）
uploaded_file = st.file_uploader("食事の写真をアップロード", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="アップロードされた食事", use_container_width=True)
    
    if st.button("AI分析してスプレッドシートに記録する", type="primary"):
        if not GEMINI_API_KEY:
            st.error("Gemini APIキーが設定されていません。")
        else:
            with st.spinner("Geminiがプレートの品目と栄養素を分析中..."):
                try:
                    # Gemini APIの初期化 (Google GenAI SDKを使用)
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    
                    # 要件定義に基づく詳細なプロンプト
                    prompt = """
                    この食事の写真から、1つのプレートに複数盛られている場合も考慮して詳細を分析し、必ず以下のキーを持つJSON形式のみで回答してください。
                    余分なテキストやマークダウンのバッククォート（```json等）は含めず、純粋なJSON文字列だけを返してください。

                    {
                      "food_items": "プレート内の主要な料理や食材のリスト・内訳（例: 鶏の唐揚げ3個, 千切りキャベツ, 白米）",
                      "food_name": "総合的な料理名または代表メニュー名",
                      "calories": 推定合計カロリーの数値のみ（例: 650）,
                      "protein": 合計タンパク質の数値のみ（例: 35.5）,
                      "fat": 合計脂質の数値のみ（例: 22.0）,
                      "carbs": 合計炭水化物の数値のみ（例: 75.0）,
                      "cholesterol_impact": "コレステロールへの影響（高・中・低、およびその簡単な理由）",
                      "blood_sugar_impact": "血糖値への影響（高・中・低、およびその簡単な理由）",
                      "advice": "改善や注意点のアドバイス"
                    }
                    """
                    
                    # Gemini API呼び出し (gemini-3.8-flashを使用)
                    response = client.models.generate_content(
                        model='gemini-3.5-flash',
                        contents=[image, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        ),
                    )
                    
                    # 結果をパース
                    result_text = response.text.strip()
                    # バッククォートなどが含まれている場合の保険処理
                    if result_text.startswith("```"):
                        result_text = result_text.split("```")[1]
                        if result_text.startswith("json"):
                            result_text = result_text[4:]
                    
                    result_data = json.loads(result_text.strip())
                    
                    # Googleスプレッドシートへの書き込み処理
                    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                    from google.oauth2.service_account import Credentials
                    
                    # 修正：ローカルに credentials.json があればそれを使い、なければ Streamlit Secrets から読み込む
                    import os
                    if os.path.exists("credentials.json"):
                        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
                    else:
                        creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
                        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                        
                    gc = gspread.authorize(creds)
                    
                    # 「食事管理シート」を開く
                    sheet = gc.open("食事管理シート").sheet1
                    
                    # 現在日時
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    # 要件定義通りのカラム順に追記
                    # A:日時, B:料理名・内訳, C:カロリー, D:タンパク質, E:脂質, F:炭水化物, G:コレステロール影響, H:血糖値影響, I:アドバイス
                    sheet.append_row([
                        now,
                        f"{result_data.get('food_name')} ({result_data.get('food_items')})",
                        result_data.get("calories"),
                        result_data.get("protein"),
                        result_data.get("fat"),
                        result_data.get("carbs"),
                        result_data.get("cholesterol_impact"),
                        result_data.get("blood_sugar_impact"),
                        result_data.get("advice")
                    ])
                    
                    st.success("✨ 分析完了＆Googleスプレッドシートへの記録が完了しました！")
                    
                    # 結果を見やすく表示
                    st.subheader("📊 分析結果サマリー")
                    st.write(f"**料理名・内訳**: {result_data.get('food_name')} ({result_data.get('food_items')})")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("カロリー", f"{result_data.get('calories')} kcal")
                    col2.metric("タンパク質", f"{result_data.get('protein')} g")
                    col3.metric("脂質", f"{result_data.get('fat')} g")
                    col4.metric("炭水化物", f"{result_data.get('carbs')} g")
                    
                    st.write(f"**🔴 コレステロールへの影響**: {result_data.get('cholesterol_impact')}")
                    st.write(f"**🔵 血糖値への影響**: {result_data.get('blood_sugar_impact')}")
                    st.info(f"💡 **アドバイス**: {result_data.get('advice')}")
                    
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")