import requests
from bs4 import BeautifulSoup
import time

def fetch_latest_yahoo_news_full():
    """
    爬取 Yahoo 日本新聞的最新一則「完整內文」。
    包含 RSS 解析、尋找全文連結，以及過濾雜訊段落。
    """
    rss_url = "https://news.yahoo.co.jp/rss/topics/top-picks.xml"
    
    # 【關鍵防呆】設定 User-Agent 偽裝成一般瀏覽器。
    # 如果不加這行，Yahoo 伺服器一看到是 Python 爬蟲就會直接拒絕連線。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # ==========================================
        # 步驟 1：抓取 RSS 取得「摘要頁面 (Pickup)」的連結
        # ==========================================
        rss_resp = requests.get(rss_url, headers=headers, timeout=10)
        rss_resp.raise_for_status()
        rss_resp.encoding = 'utf-8'
        
        soup_xml = BeautifulSoup(rss_resp.content, 'xml')
        first_item = soup_xml.find('item')
        
        if not first_item:
            return "無法在 RSS 中找到新聞項目。"
            
        title = first_item.find('title').text if first_item.find('title') else "無標題"
        pickup_link = first_item.find('link').text if first_item.find('link') else None
        
        if not pickup_link:
            return "找不到新聞連結。"

        # ==========================================
        # 步驟 2：進入 Pickup 頁面，尋找「閱讀全文」的連結
        # ==========================================
        time.sleep(1) # 禮貌性延遲，避免短時間內對伺服器發送過多請求而被封鎖
        pickup_resp = requests.get(pickup_link, headers=headers, timeout=10)
        pickup_resp.raise_for_status()
        soup_pickup = BeautifulSoup(pickup_resp.text, 'html.parser')
        
        # 尋找 href 中包含 '/articles/' 的 <a> 標籤，這通常是指向完整內文的 URL
        full_article_link = None
        for a_tag in soup_pickup.find_all('a', href=True):
            if 'news.yahoo.co.jp/articles/' in a_tag['href']:
                full_article_link = a_tag['href']
                break
                
        # ==========================================
        # 步驟 3：進入內文頁面，抓取完整新聞內容
        # ==========================================
        full_text = "無法取得完整內文（可能被網站阻擋或找不到內文連結）。"
        
        if full_article_link:
            time.sleep(1)
            article_resp = requests.get(full_article_link, headers=headers, timeout=10)
            article_resp.raise_for_status()
            soup_article = BeautifulSoup(article_resp.text, 'html.parser')
            
            # 【動態過濾技巧】Yahoo 新聞的排版常變更。
            # 這裡直接抓取所有段落 <p>，並過濾掉太短的文字（排除導覽列、頁腳等雜訊）
            paragraphs = soup_article.find_all('p')
            article_lines = []
            
            # 定義黑名單關鍵字，只要段落包含這些字就直接略過
            blacklist = ["JavaScriptが無効", "JavaScriptの設定", "Copyright", "無断転載を禁じます"]
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                
                # 1. 確保長度大於 15
                # 2. 確保沒有踩到黑名單
                if len(text) > 15 and not any(bad_word in text for bad_word in blacklist):
                    # 3. 排除下方無關的新聞推薦：真正的新聞內文通常會有正常的標點符號結尾（如句號、引號或括號）
                    # 推薦新聞的標題通常不會有這些結尾符號
                    if text.endswith('。') or text.endswith('」') or text.endswith('）') or text.endswith('碑'):
                        article_lines.append(text)
            
            if article_lines:
                # 將各個段落組合起來，用兩個換行符號隔開
                full_text = "\n\n".join(article_lines)

        # ==========================================
        # 步驟 4：組合最終字串，準備餵給 AI
        # ==========================================
        news_output = (
            f"『今日最新日本新聞』\n"
            f"標題：{title}\n"
            f"網址：{full_article_link or pickup_link}\n"
            f"------------------------\n"
            f"{full_text}"
        )
        return news_output

    except Exception as e:
        return f"爬蟲發生錯誤：{e}"

if __name__ == "__main__":
    print("正在連線至 Yahoo 日本新聞並抓取內文...\n")
    print("-" * 50)
    result = fetch_latest_yahoo_news_full()
    print(result)
    print("-" * 50)
    print("測試完成！")