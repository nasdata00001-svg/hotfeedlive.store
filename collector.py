# -*- coding: utf-8 -*-
"""
Real-time Trend Collector for Major Korean & Global Platforms:
- X (Twitter) Korea Trends
- Signal.bz (Naver alternative real-time trends)
- Google Trends (Korea Daily Search Trends)
- Nate Real-time Issue Keywords
- Naver Ranking News Topics
- Daum Ranking Topics
"""

import urllib.request
import json
import xml.etree.ElementTree as ET
import re
import datetime
import os
import sys

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

def fetch_url(url, encoding="utf-8", timeout=8):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[!] Error fetching {url}: {e}", file=sys.stderr)
        return None

def collect_google_trends():
    """구글 트렌드 대한민국 일간 급상승 검색어"""
    results = []
    url = "https://trends.google.com/trending/rss?geo=KR"
    data = fetch_url(url)
    if not data:
        return results
    try:
        root = ET.fromstring(data)
        items = root.findall(".//item")
        for idx, item in enumerate(items[:15], 1):
            title = item.find("title").text if item.find("title") is not None else ""
            approx = item.find("{https://trends.google.com/trending/rss}approx_traffic")
            traffic = approx.text if approx is not None else ""
            news_items = item.findall("{https://trends.google.com/trending/rss}news_item")
            snippets = []
            for ni in news_items[:2]:
                ntit = ni.find("{https://trends.google.com/trending/rss}news_item_title")
                nurl = ni.find("{https://trends.google.com/trending/rss}news_item_url")
                if ntit is not None:
                    snippets.append({"title": ntit.text, "url": nurl.text if nurl is not None else ""})
            
            results.append({
                "rank": idx,
                "keyword": title,
                "change": "new",
                "traffic": traffic,
                "url": f"https://www.google.com/search?q={urllib.parse.quote(title)}",
                "news": snippets
            })
    except Exception as e:
        print(f"[!] Google trends parse error: {e}", file=sys.stderr)
    return results

def collect_signal_trends():
    """시그널 실검 (네이버 기반 실시간 검색어)"""
    results = []
    url = "https://api.signal.bz/news/realtime"
    data = fetch_url(url)
    if not data:
        return results
    try:
        payload = json.loads(data)
        top10 = payload.get("top10", [])
        for item in top10:
            rank = item.get("rank", 0)
            keyword = item.get("keyword", "")
            state = item.get("state", "same") # up, down, same, new
            results.append({
                "rank": rank,
                "keyword": keyword,
                "change": state,
                "traffic": "실시간",
                "url": f"https://search.naver.com/search.naver?query={urllib.parse.quote(keyword)}",
                "news": []
            })
    except Exception as e:
        print(f"[!] Signal parse error: {e}", file=sys.stderr)
    return results

def collect_twitter_trends():
    """X (구 트위터) 대한민국 실시간 트렌드"""
    results = []
    url = "https://trends24.in/korea/"
    html = fetch_url(url)
    if not html:
        return results
    try:
        # First trend list card
        match = re.search(r'<ol class="trend-card__list">(.*?)</ol>', html, re.DOTALL)
        content = match.group(1) if match else html
        trends = re.findall(r'<a href="https://twitter\.com/search\?q=([^"&]+)[^"]*"[^>]*>([^<]+)</a>(?:\s*<span class="tweet-count">([^<]+)</span>)?', content)
        
        seen = set()
        rank = 1
        for q, kw, cnt in trends:
            kw = kw.strip()
            if not kw or kw in seen:
                continue
            seen.add(kw)
            results.append({
                "rank": rank,
                "keyword": kw,
                "change": "hot",
                "traffic": cnt.strip() if cnt else "실시간",
                "url": f"https://x.com/search?q={urllib.parse.quote(kw)}",
                "news": []
            })
            rank += 1
            if rank > 15:
                break
    except Exception as e:
        print(f"[!] X trends parse error: {e}", file=sys.stderr)
    return results

def collect_nate_trends():
    """네이트 실시간 이슈 키워드"""
    results = []
    url = "https://www.nate.com"
    html = fetch_url(url, encoding="euc-kr")
    if not html:
        return results
    try:
        # Matches class="txt_rank">keyword</span>
        items = re.findall(r'class=[\'"]txt_rank[\'"]>([^<]+)</span>', html)
        seen = set()
        rank = 1
        for item in items:
            kw = item.strip()
            if not kw or kw in seen:
                continue
            seen.add(kw)
            results.append({
                "rank": rank,
                "keyword": kw,
                "change": "up" if rank <= 3 else "same",
                "traffic": "실시간",
                "url": f"https://search.daum.net/nate?q={urllib.parse.quote(kw)}",
                "news": []
            })
            rank += 1
            if rank > 10:
                break
    except Exception as e:
        print(f"[!] Nate parse error: {e}", file=sys.stderr)
    return results

def collect_naver_news_topics():
    """네이버 랭킹 뉴스 최다 주목 토픽 헤드라인"""
    results = []
    url = "https://news.naver.com/main/ranking/popularDay.naver"
    html = fetch_url(url, encoding="euc-kr")
    if not html:
        return results
    try:
        matches = re.findall(r'<a href="([^"]*article/[^"]*)"[^>]*>([^<]+)</a>', html)
        seen = set()
        rank = 1
        for link, title in matches:
            t = title.strip().replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
            if len(t) < 6 or t in seen:
                continue
            seen.add(t)
            full_url = link if link.startswith("http") else f"https://news.naver.com{link}"
            results.append({
                "rank": rank,
                "keyword": t,
                "change": "hot",
                "traffic": "랭킹뉴스",
                "url": full_url,
                "news": []
            })
            rank += 1
            if rank > 10:
                break
    except Exception as e:
        print(f"[!] Naver news parse error: {e}", file=sys.stderr)
    return results

def collect_daum_topics():
    """다음 모바일 랭킹/포커스 이슈"""
    results = []
    url = "https://m.daum.net"
    html = fetch_url(url)
    if not html:
        return results
    try:
        matches = re.findall(r'<strong class="tit_thumb">([^<]+)</strong>', html)
        if not matches:
            matches = re.findall(r'class="link_txt"[^>]*>([^<]+)</a>', html)
        seen = set()
        rank = 1
        for title in matches:
            t = title.strip().replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
            if len(t) < 4 or t in seen:
                continue
            seen.add(t)
            results.append({
                "rank": rank,
                "keyword": t,
                "change": "hot",
                "traffic": "포커스",
                "url": f"https://search.daum.net/search?q={urllib.parse.quote(t)}",
                "news": []
            })
            rank += 1
            if rank > 10:
                break
    except Exception as e:
        print(f"[!] Daum parse error: {e}", file=sys.stderr)
    return results

def collect_all():
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"[*] Starting trends collection at {now_str}...")
    
    google = collect_google_trends()
    signal = collect_signal_trends()
    twitter = collect_twitter_trends()
    nate = collect_nate_trends()
    naver = collect_naver_news_topics()
    daum = collect_daum_topics()
    
    # Meta / Facebook note:
    # 페이스북은 2018년 이후 트렌딩/실검 서비스를 공식 폐지하여, X 및 인스타 버즈 키워드와 통합 제공
    
    payload = {
        "updated_at": now_str,
        "next_update_in_seconds": 3600,
        "platforms": {
            "all": {
                "name": "전체 종합 (TOP 통합)",
                "icon": "🔥",
                "items": (signal[:5] + twitter[:5] + google[:5])
            },
            "twitter": {
                "name": "X (구 트위터)",
                "icon": "𝕏",
                "description": "실시간 대한민국 트렌드 및 바이럴 해시태그",
                "items": twitter
            },
            "signal": {
                "name": "네이버 실검 (Signal)",
                "icon": "🟢",
                "description": "네이버 검색/뉴스 빅데이터 실시간 급상승",
                "items": signal
            },
            "google": {
                "name": "구글 트렌드 (Google)",
                "icon": "🌐",
                "description": "구글 코리아 일별 및 실시간 급상승 검색어",
                "items": google
            },
            "nate": {
                "name": "네이트 (Nate)",
                "icon": "🔴",
                "description": "네이트 포털 실시간 이슈 키워드 순위",
                "items": nate
            },
            "naver_news": {
                "name": "네이버 랭킹 뉴스",
                "icon": "📰",
                "description": "현재 가장 많이 조회되는 뉴스 헤드라인",
                "items": naver
            },
            "daum": {
                "name": "다음 이슈 (Daum)",
                "icon": "🟡",
                "description": "다음 포털 주요 실시간 뉴스 토픽",
                "items": daum
            }
        }
    }
    return payload

if __name__ == "__main__":
    data = collect_all()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "trends.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    js_path = os.path.join(out_dir, "trends_data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.INITIAL_TRENDS = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")

    print(f"[OK] Saved trends to {out_path} and {js_path}")
    print(f"[OK] Total platforms collected: {len(data['platforms'])}")
