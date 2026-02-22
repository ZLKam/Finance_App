import requests
import feedparser
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar 
import google.generativeai as genai
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

# --- 环境配置 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
FIREBASE_CRED_JSON = os.environ.get("FIREBASE_CREDENTIALS", "")

# ==========================================
# 模块 0: Firebase 初始化与连接
# ==========================================
def get_firebase_db():
    if not FIREBASE_CRED_JSON:
        print("⚠️ 未配置 FIREBASE_CREDENTIALS，跳过数据库操作。")
        return None
    try:
        cred_dict = json.loads(FIREBASE_CRED_JSON)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"☁️ ❌ Firebase 连接失败: {e}")
        return None

# ==========================================
# 模块 1: 抓取前端订阅的自选股财报 (全新强大的后端接管逻辑)
# ==========================================
def fetch_watchlist_earnings(db):
    if not db: return []
    print("正在处理前端发来的自选股财报订阅队列...")
    try:
        doc = db.collection('market_data').document('watchlist').get()
        if not doc.exists:
            return []
            
        tickers = doc.to_dict().get('tickers', [])
        if not tickers:
            return []
            
        custom_events = []
        for ticker in tickers:
            # 使用强大的后端网络环境直接调用金融接口，无视跨域限制
            url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=calendarEvents"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    earnings_list = data.get('quoteSummary', {}).get('result', [{}])[0].get('calendarEvents', {}).get('earnings', {}).get('earningsDate', [])
                    
                    if earnings_list:
                        ts = earnings_list[0].get('raw')
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                        display_time = dt.astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M") + " (SGT)"
                        
                        custom_events.append({
                            "title": f"{ticker} 财报",
                            "ticker": ticker,
                            "date": display_time,
                            "timestamp": ts,
                            "type": "custom",
                            "forecast": "盘前/盘后",
                            "previous": "--",
                            "actual": "--"
                        })
                        print(f"✅ 成功锁定 {ticker} 财报日: {display_time}")
            except Exception as e:
                print(f"⚠️ 获取 {ticker} 失败: {e}")
                
        return custom_events
    except Exception as e:
        print(f"❌ 同步自选股失败: {e}")
        return []

# ==========================================
# 模块 2 & 3: 宏观数据与新闻抓取分析 (保持之前的稳定逻辑)
# ==========================================
def fetch_macro_events():
    print("正在获取本周重要经济数据...")
    now_utc = datetime.now(timezone.utc)
    monday_utc = now_utc - timedelta(days=now_utc.weekday())
    start_of_week = monday_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    start_str = start_of_week.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    end_str = end_of_week.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    url = f"https://economic-calendar.tradingview.com/events?from={start_str}&to={end_str}&countries=US"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        events = response.json().get('result', response.json())
        important_events = []
        for event in events:
            if event.get("importance", 0) >= 1 and event.get("date"):
                try:
                    clean_date = event["date"].replace('Z', '').split('.')[0] 
                    dt_utc = datetime.strptime(clean_date, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    display_time = dt_utc.astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M") + " (SGT)"
                    timestamp = dt_utc.timestamp()
                except:
                    display_time = event["date"]
                    timestamp = 0
                important_events.append({
                    "title": event.get("title", "未知事件"), "date": display_time,
                    "previous": str(event.get("previous", "N/A")) if event.get("previous") is not None else "N/A",
                    "forecast": str(event.get("forecast", "N/A")) if event.get("forecast") is not None else "N/A",
                    "actual": str(event.get("actual", "尚未公布")) if event.get("actual") is not None else "尚未公布",
                    "timestamp": timestamp, "analysis": "AI 解读生成中..."
                })
        return sorted(important_events, key=lambda x: x['timestamp'])
    except Exception as e:
        print(f"❌ 获取宏观数据失败: {e}")
        return []

def fetch_latest_news():
    print("-" * 40)
    print("正在获取最新财经新闻...")
    try:
        response = requests.get("https://www.investing.com/rss/news_25.rss", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        feed = feedparser.parse(response.content)
        recent_entries = []
        for entry in feed.entries:
            recent_entries.append(entry)
            if len(recent_entries) >= 30: break
        return recent_entries 
    except Exception as e:
        return []

def analyze_news_with_gemini(news_entries):
    if not news_entries: return []
    news_list_text = ""
    for i, entry in enumerate(news_entries):
        title = entry.get('title', '无标题')
        link = entry.get('link', '')
        content_list = entry.get('content', [])
        full_content = content_list[0].get('value', '').split('<img')[0].replace('<p>', '').replace('</p>', '\n').strip() if content_list else ""
        if not full_content:
            full_content = entry.get('summary', entry.get('description', '')).split('<img')[0].split('<br')[0].split('<p')[0].strip()
        full_content = full_content[:1500] if full_content else "无正文，结合标题推测。"
        news_list_text += f"[{i}] 标题: {title}\n链接: {link}\n摘要: {full_content}\n\n"
        
    prompt = f"""你是顶级宏观交易员。评估以下新闻对【美股大盘】或【黄金】或【重要个股】影响。
评分(0-10): 7-8分高度重要(权重股暴雷/重要宏观)，9-10分黑天鹅。
返回纯 JSON 数组: [{{"id": 编号, "score": 打分(0-10), "impact": "利多/利空/中性", "reason": "一句话原因"}}]
新闻:
{news_list_text}"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        result_text = model.generate_content(prompt).text.strip().removeprefix("```json").removesuffix("```").strip()
        important_news = []
        for item in json.loads(result_text):
            if item['score'] >= 7:
                orig = news_entries[item['id']]
                important_news.append({
                    "title": orig.title, "score": item['score'], "impact": item['impact'], 
                    "reason": item['reason'], "link": orig.get('link', '') 
                })
        return important_news
    except Exception as e:
        return []

def analyze_macro_with_gemini(all_events):
    if not all_events: return all_events
    print("🤖 正在呼叫 Gemini AI 全面分析【本周经济数据】...")
    macro_text = ""
    for i, ev in enumerate(all_events):
        macro_text += f"[{i}] 📅 {ev['date']} | 📌 {ev['title']} | 前值:{ev['previous']} 预期:{ev['forecast']} 实际:{ev['actual']}\n"
    prompt = f"""你是宏观分析师。本周有以下重要数据。请针对每一个数据分析其潜在影响（若未公布写交易剧本，已公布写实际影响）。
返回纯 JSON 数组: [{{"id": 对应编号, "analysis": "分析及影响剧本(80字内)"}}]
数据：\n{macro_text}"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        result_text = model.generate_content(prompt).text.strip().removeprefix("```json").removesuffix("```").strip()
        ai_data = json.loads(result_text)
        for item in ai_data:
            idx = item.get('id')
            if idx is not None and 0 <= idx < len(all_events):
                all_events[idx]['analysis'] = item.get('analysis', '')
        return all_events
    except Exception as e:
        return all_events

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN": return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=10)
    except: pass

# ==========================================
# 主程序控制流
# ==========================================
if __name__ == "__main__":
    print("=== MarketMind 数据获取引擎 (含后端抓取) 启动 ===\n")
    
    db = get_firebase_db()
    
    # 1. 获取并分析宏观数据
    all_macro_data = fetch_macro_events()
    if all_macro_data:
        all_macro_data = analyze_macro_with_gemini(all_macro_data)
        
    # 2. 获取并分析新闻数据
    news_data = fetch_latest_news()
    critical_news = analyze_news_with_gemini(news_data) if news_data else []
    
    # 3. 执行自选股财报拉取任务 (接管前端任务)
    custom_events = fetch_watchlist_earnings(db) if db else []
    
    # 4. 统一执行数据上云推送
    if db:
        try:
            timestamp = datetime.now(ZoneInfo("Asia/Singapore")).strftime('%Y-%m-%d %H:%M:%S')
            if all_macro_data:
                db.collection('market_data').document('macro').set({'events': all_macro_data, 'last_updated': timestamp})
            if critical_news:
                db.collection('market_data').document('news').set({'articles': critical_news, 'last_updated': timestamp})
            if custom_events is not None:
                # 覆盖写入最新的财报日历
                db.collection('market_data').document('custom_calendar').set({'events': custom_events, 'last_updated': timestamp})
            print("\n☁️ ✅ 核心数据已全部同步至 Firebase 数据库！")
        except Exception as e:
            print(f"\n☁️ ❌ Firebase 上传失败: {e}")

    # 5. Telegram 日常推送
    today_sgt = datetime.now(ZoneInfo("Asia/Singapore")).date()
    today_macro = [ev for ev in all_macro_data if datetime.fromtimestamp(ev['timestamp'], tz=ZoneInfo("Asia/Singapore")).date() == today_sgt]
    
    print("-" * 40)
    if today_macro:
        tg_msg = f"📊 **今日核心经济数据** ({datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y-%m-%d')})\n\n"
        for ev in today_macro:
            tg_msg += f"🔹 **{ev['title']}**\n⏱ {ev['date'].split(' ')[1]}\n📉 预:{ev['forecast']} | 前:{ev['previous']} | 实:{ev['actual']}\n💡 **AI**: {ev['analysis']}\n\n"
        send_telegram_alert(tg_msg)
        
    if critical_news:
        for news in critical_news:
            tg_msg = f"🚨 **重要情报 ({news['score']}/10)**\n\n📰 **{news['title']}**\n📈 方向: {news['impact']}\n💡 **AI**: {news['reason']}\n🔗 [阅读]({news.get('link','')})\n"
            send_telegram_alert(tg_msg)

    print("\n=== MarketMind 运行完毕 ===")