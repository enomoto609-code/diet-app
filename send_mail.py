import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# 1. 認証情報や設定の読み込み（GitHub Actionsの環境変数から取得）
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON") # JSONの文字列を丸ごと入れる想定

# メール送信設定（Gmail等）
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")       # 送信元メールアドレス
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD") # Gmailのアプリパスワード
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")   # 受け取り先メールアドレス

def main():
    try:
        # 2. スプレッドシートから直近7日間のデータを取得
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # GitHub SecretsからJSONを読み込んで一時ファイル化または直接認証
        import json
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        gc = gspread.authorize(creds)
        
        sheet = gc.open("食事管理シート").sheet1
        rows = sheet.get_all_values() # すべての行を取得
        
        if len(rows) <= 1:
            print("データがまだありません。")
            return

        header = rows[0]
        data_rows = rows[1:]
        
        # 直近7日間のデータを抽出
        today = datetime.date.today()
        seven_days_ago = today - datetime.timedelta(days=7)
        
        recent_records = []
        for row in data_rows:
            record_date_str = row[0][:10] # YYYY-MM-DD
            try:
                r_date = datetime.datetime.strptime(record_date_str, "%Y-%m-%d").date()
                if r_date >= seven_days_ago:
                    recent_records.append(row)
            except Exception:
                continue
                
        if not recent_records:
            print("直近7日間のデータがありません。")
            return

        # 3. Gemini APIでデータを分析し、メール文面を生成
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        以下はユーザーの直近7日間の食事記録データです。このデータを分析し、以下の構成でメール文面を作成してください。
        
        【データ】
        {recent_records}
        
        【出力構成】
        1. 好ましい傾向（改善できている点、良いポイント）
        2. 好ましくない傾向（脂質やカロリーオーバーの傾向、野菜不足など）
        3. 今後の方向性（今日から意識すべきポイント）
        4. AIからの総合アドバイス
        
        温かみがあり、モチベーションが上がるようなトーンで日本語で作成してください。
        """
        
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
        )
        email_body = response.text
        
        # 4. メールを送信する
        msg = MIMEMultipart()
        msg['Subject'] = "🥗 【AI食事管理】直近1週間の振り返りとアドバイス"
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        
        msg.attach(MIMEText(email_body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            
        print("メールの送信が正常に完了しました！")
        
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()