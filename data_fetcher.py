import requests
import feedparser
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar 
import google.generativeai as genai
import json
import os

# ==========================================
# 核心配置区域 (支持本地运行与云端环境变量)
# ==========================================
# 优先从环境变量获取，如果没有则使用填写的字符串
# 这样做可以安全地将代码上传到 GitHub，而在 GitHub Secrets 中配置真实的 Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Telegram 推送配置
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# ==========================================
# 基础工具: Telegram 推送模块
# ==========================================
def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_BOT_TOKEN:
        print("⚠️ 未配置 Telegram Token，仅在控制台打印，跳过推送。")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" # 使用基础的 Markdown 加粗格式
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ 成功推送到 Telegram!")
        else:
            print(f"❌ Telegram 推送失败，错误码: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"❌ Telegram 推送异常: {e}")

# ==========================================
# 模块 1: 获取宏观经济数据 (含实际值)
# ==========================================
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
        response.raise_for_status()
        
        data = response.json()
        events = data.get('result', data) if isinstance(data, dict) else data
        important_events = []
        
        for event in events:
            importance = event.get("importance", 0)
            if importance >= 1:
                title = event.get("title", "未知事件")
                previous = event.get("previous")
                forecast = event.get("forecast")
                actual = event.get("actual") # 新增：尝试获取实际公布值
                date_str = event.get("date")
                
                if not date_str:
                    continue
                    
                try:
                    clean_date_str = date_str.replace('Z', '').split('.')[0] 
                    dt_utc = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    dt_sgt = dt_utc.astimezone(ZoneInfo("Asia/Singapore"))
                    
                    display_time = dt_sgt.strftime("%Y-%m-%d %H:%M") + " (SGT)"
                    timestamp = dt_utc.timestamp()
                except Exception as e:
                    display_time = date_str
                    timestamp = 0
                
                important_events.append({
                    "title": title,
                    "date": display_time,
                    "previous": str(previous) if previous is not None else "N/A",
                    "forecast": str(forecast) if forecast is not None else "N/A",
                    "actual": str(actual) if actual is not None else "尚未公布",
                    "timestamp": timestamp
                })
        
        important_events = sorted(important_events, key=lambda x: x['timestamp'])
        print(f"✅ 成功获取 {len(important_events)} 条高重要性宏观数据！\n")
        return important_events

    except Exception as e:
        print(f"❌ 获取宏观数据失败: {e}")
        return []

# ==========================================
# 模块 2: 获取最新财经突发新闻
# ==========================================
def fetch_latest_news():
    print("-" * 40)
    print("正在获取最新财经新闻...")
    rss_url = "https://www.investing.com/rss/news_25.rss"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        recent_entries = []
        
        # 优化：移除严格的24小时过滤，直接抓取 RSS 排序中最顶部的 30 条最新新闻
        for entry in feed.entries:
            recent_entries.append(entry)
            
            # 抓满 30 条就停止
            if len(recent_entries) >= 30:
                break
                
        print(f"✅ 成功获取 {len(recent_entries)} 条最新新闻！\n")
        return recent_entries 
        
    except Exception as e:
        print(f"❌ 获取新闻失败: {e}")
        return []

# ==========================================
# 模块 3: AI 分析核心功能 (新闻 + 数据)
# ==========================================
def analyze_news_with_gemini(news_entries):
    if not news_entries:
        return []
    print("🤖 正在呼叫 Gemini AI 分析【突发新闻】...")
    
    news_list_text = ""
    for i, entry in enumerate(news_entries):
        title = entry.get('title', '无标题')
        link = entry.get('link', '无链接')
        pub_time = entry.get('published', '未知时间')
        
        # 尝试获取全文内容 (部分 RSS 源会在 content 中提供全文)
        content_list = entry.get('content', [])
        full_content = ""
        if content_list and len(content_list) > 0:
            full_content = content_list[0].get('value', '')
            # 简单清理 HTML 标签
            full_content = full_content.split('<img')[0].replace('<p>', '').replace('</p>', '\n').strip()
        
        # 如果没有 content，退而求其次用 summary/description
        if not full_content:
            full_content = entry.get('summary', entry.get('description', ''))
            full_content = full_content.split('<img')[0].split('<br')[0].split('<p')[0].strip()
            
        if not full_content:
            full_content = "无正文，请结合标题和链接进行推测。"
        else:
            full_content = full_content[:1500] # 放宽字数限制到1500字，给AI提供极长上下文
            
        news_list_text += f"[{i}] 标题: {title}\n时间: {pub_time}\n链接: {link}\n内容/摘要: {full_content}\n\n"
        
    prompt = f"""
    你是一个华尔街顶级宏观交易员和个股分析师。请评估以下最新财经新闻对【美股大盘】、【黄金】或【重要权重股/热门板块】的潜在影响。
    你可以通过阅读标题、正文内容以及新闻链接来综合判断。
    
    打分规则 (0-10分):
    - 0-3分: 普通噪音（小公司财报、高管常规发言、无实质影响的日常新闻）。
    - 4-6分: 一般重要（普通经济数据、非核心个股的日常新闻）。
    - 7-8分: 高度重要（明星股/权重股的评级大幅下调或业绩暴雷、热门行业重大突发、能引发市场情绪波动的宏观事件）。
    - 9-10分: 极度重要（突发战争、美联储超预期政策、系统性黑天鹅事件）。
    
    注意：即使是单一股票，只要它是具有市场影响力的公司（如科技七巨头、知名蓝筹股等），其重大利空/利好也应给予 7 分及以上。
    
    返回格式必须是纯 JSON 数组：
    [
      {{"id": 编号, "score": 打分(0-10), "impact": "利多/利空/中性 (指明对大盘/黄金/某板块/特定股票)", "reason": "一句话简短说明原因"}}
    ]
    待分析新闻列表:
    {news_list_text}
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        result_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        ai_analysis = json.loads(result_text)
        
        important_news = []
        for item in ai_analysis:
            # 推送阈值下调：7分及以上（包含重要个股异动）就触发抓取
            if item['score'] >= 7:
                orig = news_entries[item['id']]
                important_news.append({
                    "title": orig.title, 
                    "score": item['score'], 
                    "impact": item['impact'], 
                    "reason": item['reason'],
                    "link": orig.get('link', '') 
                })
        return important_news
    except Exception as e:
        print(f"❌ 新闻 AI 分析失败: {e}")
        return []

def analyze_macro_with_gemini(today_events):
    if not today_events:
        return []
    print("🤖 正在呼叫 Gemini AI 分析【今日经济数据】影响...")
    
    macro_text = ""
    for ev in today_events:
        macro_text += f"- 📅 {ev['date']} | 📌 {ev['title']}\n"
        macro_text += f"  前值: {ev['previous']}, 预期: {ev['forecast']}, 实际: {ev['actual']}\n\n"
        
    prompt = f"""
    你是华尔街顶级宏观分析师。今日有以下重要经济数据发布。
    请结合“前值”、“预期”和“实际值(若有)”，用最通俗易懂的话分析该数据对【美股大盘】和【黄金】的潜在影响。
    
    要求：
    1. 如果实际值是“尚未公布”，请给出“交易剧本”（如：若公布值大于预期X，则利空美股/利多黄金）。
    2. 如果实际值已经存在，请直接判定“超预期”或“不及预期”，并指出当前已经产生的影响。
    
    返回格式必须是纯 JSON 数组：
    [
      {{"title": "数据名称", "analysis": "分析及影响剧本 (限80字以内)"}}
    ]
    
    今日数据：
    {macro_text}
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        result_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(result_text)
    except Exception as e:
        print(f"❌ 数据 AI 分析失败: {e}")
        return []

# ==========================================
# 主程序流
# ==========================================
if __name__ == "__main__":
    print("=== MarketMind 数据获取与 AI 引擎启动 ===\n")
    
    # 1. 获取并过滤宏观数据 (只取今天的)
    all_macro_data = fetch_macro_events()
    today_sgt = datetime.now(ZoneInfo("Asia/Singapore")).date()
    today_macro = []
    
    for ev in all_macro_data:
        try:
            ev_date = datetime.fromtimestamp(ev['timestamp'], tz=ZoneInfo("Asia/Singapore")).date()
            if ev_date == today_sgt:
                today_macro.append(ev)
        except:
            pass
            
    # 2. 获取新闻
    news_data = fetch_latest_news()
    
    # 3. AI 分析并执行 Telegram 推送
    print("-" * 40)
    
    # -- 处理今日宏观数据 --
    if today_macro:
        print(f"📌 发现 {len(today_macro)} 个今日核心经济数据，开始 AI 解读...")
        macro_analysis = analyze_macro_with_gemini(today_macro)
        
        if macro_analysis:
            # 组合要推送到 Telegram 的消息
            tg_msg = f"📊 **今日核心经济数据前瞻/解读** 📊\n"
            tg_msg += f"日期: {datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y-%m-%d')}\n\n"
            
            for orig, ai_result in zip(today_macro, macro_analysis):
                tg_msg += f"🔹 **{ai_result['title']}**\n"
                tg_msg += f"⏱ 时间: {orig['date'].split(' ')[1]}\n"
                tg_msg += f"📉 预期: {orig['forecast']} | 前值: {orig['previous']} | 实际: {orig['actual']}\n"
                tg_msg += f"💡 **AI剧本**: {ai_result['analysis']}\n\n"
            
            print(tg_msg)
            send_telegram_alert(tg_msg)
    else:
        print("📭 今天没有高重要性的经济数据。")

    # -- 处理突发新闻 --
    if news_data:
        critical_news = analyze_news_with_gemini(news_data)
        if critical_news:
            for news in critical_news:
                tg_msg = f"🚨 **市场重要情报 (评分:{news['score']}/10)** 🚨\n\n"
                tg_msg += f"📰 **{news['title']}**\n"
                tg_msg += f"📈 影响: {news['impact']}\n"
                tg_msg += f"💡 **AI 简评**: {news['reason']}\n"
                if news.get('link'):
                    tg_msg += f"🔗 [查看原文]({news['link']})\n"
                
                print(tg_msg)
                send_telegram_alert(tg_msg)
        else:
            print("✅ 市场暂无评分大于 7 的重要情报。")
            
    print("\n=== MarketMind 运行完毕 ===")