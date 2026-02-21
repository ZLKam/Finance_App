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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

FIREBASE_CRED_JSON = os.environ.get("FIREBASE_CREDENTIALS", "")

def upload_to_firebase(macro_data, news_data):
    if not FIREBASE_CRED_JSON:
        print("⚠️ 未配置 FIREBASE_CREDENTIALS，跳过数据库同步。")
        return
    try:
        cred_dict = json.loads(FIREBASE_CRED_JSON)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        if macro_data:
            db.collection('market_data').document('macro').set({
                'events': macro_data,
                'last_updated': datetime.now(ZoneInfo("Asia/Singapore")).strftime('%Y-%m-%d %H:%M:%S')
            })
        if news_data:
            db.collection('market_data').document('news').set({
                'articles': news_data,
                'last_updated': datetime.now(ZoneInfo("Asia/Singapore")).strftime('%Y-%m-%d %H:%M:%S')
            })
        print("☁️ ✅ 成功同步最新数据至 Firebase 数据库！")
    except Exception as e:
        print(f"☁️ ❌ Firebase 同步失败: {e}")

def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        pass

def fetch_macro_events():
    print("正在获取本周重要经济数据 (数据源: TradingView 国际版)...")
    now_utc = datetime.now(timezone.utc)
    monday_utc = now_utc - timedelta(days=now_utc.weekday())
    start_of_week = monday_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    start_str = start_of_week.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    end_str = end_of_week.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    url = f"https://economic-calendar.tradingview.com/events?from={start_str}&to={end_str}&countries=US"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # 恢复状态码检查
        
        data = response.json()
        events = data.get('result', data) if isinstance(data, dict) else data
        
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
                    "title": event.get("title", "未知事件"),
                    "date": display_time,
                    "previous": str(event.get("previous", "N/A")) if event.get("previous") is not None else "N/A",
                    "forecast": str(event.get("forecast", "N/A")) if event.get("forecast") is not None else "N/A",
                    "actual": str(event.get("actual", "尚未公布")) if event.get("actual") is not None else "尚未公布",
                    "timestamp": timestamp,
                    "analysis": "AI 解读生成中..."
                })
        important_events = sorted(important_events, key=lambda x: x['timestamp'])
        print(f"✅ 成功获取 {len(important_events)} 条高重要性宏观数据！\n")
        return important_events
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
        print(f"✅ 成功获取 {len(recent_entries)} 条最新新闻！\n")
        return recent_entries 
    except Exception as e:
        print(f"❌ 获取新闻失败: {e}")
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
        print(f"❌ 新闻 AI 分析失败: {e}")
        return []

def analyze_macro_with_gemini(all_events):
    if not all_events: return all_events
    print("🤖 正在呼叫 Gemini AI 全面分析【本周经济数据】...")
    macro_text = ""
    for i, ev in enumerate(all_events):
        macro_text += f"[{i}] 📅 {ev['date']} | 📌 {ev['title']} | 前值:{ev['previous']} 预期:{ev['forecast']} 实际:{ev['actual']}\n"
        
    prompt = f"""你是宏观分析师。本周有以下重要数据。请针对每一个数据分析其潜在影响（若未公布写交易剧本，已公布写实际影响）。
返回纯 JSON 数组: [{{"id": 对应编号, "analysis": "分析及影响剧本(80字内)"}}]
数据：
{macro_text}"""
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
        print(f"❌ 数据 AI 分析失败: {e}")
        return all_events

if __name__ == "__main__":
    print("=== MarketMind 数据获取与 AI 引擎启动 ===\n")
    
    all_macro_data = fetch_macro_events()
    if all_macro_data:
        all_macro_data = analyze_macro_with_gemini(all_macro_data)
        
    news_data = fetch_latest_news()
    critical_news = analyze_news_with_gemini(news_data) if news_data else []
    
    today_sgt = datetime.now(ZoneInfo("Asia/Singapore")).date()
    today_macro = [ev for ev in all_macro_data if datetime.fromtimestamp(ev['timestamp'], tz=ZoneInfo("Asia/Singapore")).date() == today_sgt]
    
    print("-" * 40)
    if today_macro:
        tg_msg = f"📊 **今日核心经济数据** ({datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y-%m-%d')})\n\n"
        for ev in today_macro:
            tg_msg += f"🔹 **{ev['title']}**\n⏱ {ev['date'].split(' ')[1]}\n📉 预:{ev['forecast']} | 前:{ev['previous']} | 实:{ev['actual']}\n💡 **AI**: {ev['analysis']}\n\n"
        print(tg_msg)
        send_telegram_alert(tg_msg)
        
    if critical_news:
        for news in critical_news:
            tg_msg = f"🚨 **重要情报 ({news['score']}/10)**\n\n📰 **{news['title']}**\n📈 方向: {news['impact']}\n💡 **AI**: {news['reason']}\n🔗 [阅读]({news.get('link','')})\n"
            print(tg_msg)
            send_telegram_alert(tg_msg)

    upload_to_firebase(all_macro_data, critical_news)
    print("\n=== MarketMind 运行完毕 ===")