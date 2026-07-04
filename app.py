import os
import time
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

load_dotenv()
app = Flask(__name__)

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('RENDER_DB_URL', 'sqlite:///local.db') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class MathFormula(db.Model):
    __tablename__ = 'crawled_formulas'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class ExamPaper(db.Model):
    __tablename__ = 'exam_papers'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(50))       
    pdf_url = db.Column(db.String(500))   

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/math')
def math():
    return render_template('math.html')

@app.route('/physics')
def physics():
    return render_template('physics.html')

@app.route('/favorites')
def favorites():
    return render_template('favorites.html')

@app.route('/exams')
def exams(): 
    papers = ExamPaper.query.order_by(ExamPaper.id.desc()).all()
    return render_template('exams.html', papers=papers)


@app.route('/api/chat', methods=['POST'])
def chat():
    if not api_key:
        return jsonify({"reply": "系統發生錯誤：未設定 API Key"}), 500

    data = request.json
    user_message = data.get('message')

    if not user_message:
        return jsonify({"reply": "請輸入問題喔！"}), 400

    prompt = f"""
    你現在是一位專業、有耐心的國中理化與數學老師。
    學生的問題是：「{user_message}」

    請嚴格遵守以下對話原則：
    1. 語氣自然、專業、平易近人。絕對不要扮演任何動物角色，不要使用顏文字或奇怪的語尾助詞。
    2. 如果是腦筋急轉彎或邏輯陷阱題（例如一公斤鐵和棉花哪個重），請一針見血地點破盲點，不要生硬地套用物理公式。
    3. 如果是真實的計算題，引導學生思考該用什麼公式，並解釋公式代號，但不要直接給出最終答案。
    4. 格式限制：絕對禁止使用 LaTeX 語法（不要出現任何 $ 符號）。公式請一律使用純文字，例如：W = m * g。
    """
    try:
        response = model.generate_content(prompt)
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"reply": f"AI 助教目前連線異常，請稍後再試。錯誤代碼：{str(e)}"}), 500

@app.route('/crawl')
def crawl_formulas():
    print("啟動 Selenium 爬蟲 (Scribd)...")
    options = Options()
    options.binary_location = "/usr/bin/chromium" 
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument('--disable-blink-features=AutomationControlled')

    driver = webdriver.Chrome(options=options)
    target_url = "https://www.scribd.com/document/1009176805/%E5%9C%8B%E4%B8%AD%E6%95%B8%E5%AD%B8%E5%85%AC%E5%BC%8F%E5%92%8C%E9%87%8D%E9%BB%9E%E6%95%B4%E7%90%86-%E8%87%AA%E7%B7%A8"
    
    try:
        driver.get(target_url)
        time.sleep(5)
        for i in range(5):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1.5)
            
        elements = driver.find_elements(By.CSS_SELECTOR, ".text_layer span")
        extracted_text = " ".join([el.text.strip() for el in elements if el.text.strip()])
                
        if extracted_text:
            MathFormula.query.delete() 
            new_data = MathFormula(title="Scribd國中數學公式整理", content=extracted_text)
            db.session.add(new_data)
            db.session.commit()
            return "Crawl Success! Scribd 文本爬蟲成功並已存入資料庫！"
        else:
            return "⚠️ 未擷取到文字，請檢查網頁。"
    except Exception as e:
        return f"爬蟲發生錯誤：{e}"
    finally:
        driver.quit()

@app.route('/analyze')
def analyze_data():
    latest_data = MathFormula.query.order_by(MathFormula.created_at.desc()).first()
    if not latest_data or not latest_data.content:
        return "<h3>⚠️ 目前雲端資料庫沒有文本可供分析，請先前往 /crawl 執行爬蟲。</h3>"
        
    text_content = latest_data.content
    keywords = ["方程式", "三角形", "面積", "函數", "相似", "機率", "圓周率", "絕對值", "平方根", "多項式", "幾何", "座標"]

    analysis_result = {word: text_content.count(word) for word in keywords if text_content.count(word) > 0}
    sorted_result = sorted(analysis_result.items(), key=lambda x: x[1], reverse=True)
    
    html = """
    <div style="font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
        <h2 style="color: #2c3e50;">📊 國中數學公式庫：核心概念詞頻分析報表</h2>
        <p style="color: #555; line-height: 1.6;">本系統對爬蟲取得之文本進行了關鍵字萃取與特徵分析。</p>
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
    """
    max_count = sorted_result[0][1] if sorted_result else 1
    for word, count in sorted_result:
        bar_width = int((count / max_count) * 100)
        html += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 12px; font-weight: bold;">{word}</td>
                <td style="padding: 12px;">{count} 次</td>
                <td style="padding: 12px; width: 50%;">
                    <div style="background-color: #3498db; height: 18px; width: {bar_width}%; border-radius: 3px;"></div>
                </td>
            </tr>
        """
    html += "</table></div>"
    return html

@app.route('/crawl_exams')
def crawl_exams():
    print("啟動 Selenium 爬蟲 (歷屆會考)...")
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://cap.rcpet.edu.tw/examination.html")
        time.sleep(3) 
        
        ExamPaper.query.delete() 
        
        select_element = driver.find_element(By.TAG_NAME, "select")
        select = Select(select_element)
        options_count = len(select.options)
        
        count = 0
        for i in range(options_count):
            select = Select(driver.find_element(By.TAG_NAME, "select"))
            year_text = select.options[i].text 
            select.select_by_index(i)
            time.sleep(2) 
            
            try:
                driver.switch_to.frame("iframe")
                
                math_link = driver.find_element(By.XPATH, "//a[contains(., '數學科')]")
                pdf_url = math_link.get_attribute("href")
                
                if pdf_url:
                    new_paper = ExamPaper(year=year_text, pdf_url=pdf_url)
                    db.session.add(new_paper)
                    count += 1
                    print(f"✅ {year_text} 成功！網址: {pdf_url}")
                    
            except Exception as e:
                print(f"⚠️ {year_text} 找不到連結或發生錯誤: {e}")
                
            finally:
                driver.switch_to.default_content()
                
        db.session.commit()
        return f"Crawl Success! 機器人成功破解 iframe，共抓到 {count} 份考題！"

    except Exception as e:
        return f"題庫爬蟲發生錯誤：{e}"
    finally:
        driver.quit()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)