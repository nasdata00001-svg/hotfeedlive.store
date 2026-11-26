# -*- coding: utf-8 -*-
"""
Real-time Trend Collector for HOTFEED LIVE (hotfeedlive.store):
- X (Twitter) Korea Trends
- Signal.bz (Naver alternative real-time trends)
- Google Trends (Korea Daily Search Trends)
- Nate Real-time Issue Keywords
- Naver Ranking News Topics
- Nate Pann Community Hot Topics
- Google News Korea Breaking Headlines
"""

import datetime
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

KST = datetime.timezone(datetime.timedelta(hours=9))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(text))).strip()


def fetch_url(url, encoding="utf-8", timeout=10):
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
        seen = set()
        rank = 1
        for item in items:
            title_node = item.find("title")
            title = clean_text(title_node.text if title_node is not None else "")
            if not title or title in seen:
                continue
            seen.add(title)

            approx = item.find("{https://trends.google.com/trending/rss}approx_traffic")
            traffic = clean_text(approx.text if approx is not None else "") or "급상승"
            news_items = item.findall("{https://trends.google.com/trending/rss}news_item")
            snippets = []
            for ni in news_items[:2]:
                ntit = ni.find("{https://trends.google.com/trending/rss}news_item_title")
                nurl = ni.find("{https://trends.google.com/trending/rss}news_item_url")
                if ntit is not None and ntit.text:
                    snippets.append({
                        "title": clean_text(ntit.text),
                        "url": clean_text(nurl.text if nurl is not None else "")
                    })

            results.append({
                "rank": rank,
                "keyword": title,
                "change": "new",
                "traffic": traffic,
                "url": f"https://www.google.com/search?q={urllib.parse.quote(title)}",
                "news": snippets,
            })
            rank += 1
            if rank > 15:
                break
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
        seen = set()
        for idx, item in enumerate(top10, 1):
            keyword = clean_text(item.get("keyword", ""))
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            try:
                rank = int(item.get("rank", idx))
            except (TypeError, ValueError):
                rank = idx
            state = clean_text(item.get("state", "s")).lower() or "s"
            results.append({
                "rank": rank,
                "keyword": keyword,
                "change": state,
                "traffic": "실시간",
                "url": f"https://search.naver.com/search.naver?query={urllib.parse.quote(keyword)}",
                "news": [],
            })
    except Exception as e:
        print(f"[!] Signal parse error: {e}", file=sys.stderr)
    return results


def collect_twitter_trends():
    """X (구 트위터) 대한민국 실시간 트렌드"""
    results = []
    url = "https://trends24.in/korea/"
    page_html = fetch_url(url)
    if not page_html:
        return results
    try:
        # Match first (latest hour) trend card list, handling unquoted or quoted class attributes
        match = re.search(r'<ol[^>]*class=["\']?trend-card__list["\']?[^>]*>(.*?)</ol>', page_html, re.DOTALL)
        content = match.group(1) if match else page_html

        li_blocks = re.findall(r'<li[^>]*>(.*?)</li>', content, re.DOTALL)
        seen = set()
        rank = 1
        for block in li_blocks:
            link_match = re.search(
                r'<a[^>]+href=["\']https://(?:twitter|x)\.com/search\?q=[^"\']+["\'][^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not link_match:
                continue
            kw = clean_text(re.sub(r'<[^>]+>', '', link_match.group(1)))
            if not kw or kw in seen:
                continue
            seen.add(kw)

            cnt_match = re.search(r'<span[^>]*class=["\']?tweet-count["\']?[^>]*>(.*?)</span>', block, re.DOTALL)
            cnt = clean_text(re.sub(r'<[^>]+>', '', cnt_match.group(1))) if cnt_match else ""

            results.append({
                "rank": rank,
                "keyword": kw,
                "change": "hot",
                "traffic": cnt if cnt else "실시간",
                "url": f"https://x.com/search?q={urllib.parse.quote(kw)}",
                "news": [],
            })
            rank += 1
            if rank > 15:
                break
    except Exception as e:
        print(f"[!] X trends parse error: {e}", file=sys.stderr)
    return results


def collect_nate_trends():
    """네이트 실시간 이슈 키워드 (1~10위 공식 JSON 피드 + HTML 폴백)"""
    results = []

    # 1. Primary: Official full 1~10 JSON array used by nate.com liveIssueKeyword widget
    json_url = "https://www.nate.com/js/data/jsonLiveKeywordDataV1.js"
    raw_js = fetch_url(json_url, encoding="euc-kr")
    if raw_js:
        try:
            rows = json.loads(raw_js)
            seen = set()
            for row in rows:
                if not isinstance(row, list) or len(row) < 4:
                    continue
                rank_str = clean_text(row[0])
                kw = clean_text(row[4] if len(row) > 4 and row[4] else row[1])
                state = clean_text(row[2]).lower() or "s"
                delta = clean_text(row[3])
                if not kw or kw in seen:
                    continue
                seen.add(kw)
                try:
                    rank = int(rank_str)
                except ValueError:
                    rank = len(results) + 1

                traffic = "실시간"
                if state == "+" and delta.isdigit() and int(delta) > 0:
                    traffic = f"+{delta}"
                elif state == "-" and delta.isdigit() and int(delta) > 0:
                    traffic = f"-{delta}"

                results.append({
                    "rank": rank,
                    "keyword": kw,
                    "change": state,
                    "traffic": traffic,
                    "url": f"https://search.daum.net/nate?q={urllib.parse.quote(kw)}",
                    "news": [],
                })
            if results:
                results.sort(key=lambda x: x["rank"])
                return results[:10]
        except Exception as e:
            print(f"[!] Nate JSON parse error, falling back to HTML: {e}", file=sys.stderr)

    # 2. Fallback: nate.com homepage HTML (UTF-8)
    page_html = fetch_url("https://www.nate.com", encoding="utf-8")
    if not page_html:
        return results
    try:
        items = re.findall(
            r'<span class=["\']num_rank["\']>(\d+)</span>.*?<span class=["\']txt_rank["\']>([^<]+)</span>',
            page_html,
            re.DOTALL,
        )
        seen = set()
        for rank_str, kw_raw in items:
            kw = clean_text(kw_raw)
            if not kw or kw in seen:
                continue
            seen.add(kw)
            results.append({
                "rank": int(rank_str),
                "keyword": kw,
                "change": "up" if int(rank_str) <= 3 else "same",
                "traffic": "실시간",
                "url": f"https://search.daum.net/nate?q={urllib.parse.quote(kw)}",
                "news": [],
            })
        results.sort(key=lambda x: x["rank"])
    except Exception as e:
        print(f"[!] Nate fallback parse error: {e}", file=sys.stderr)
    return results[:10]


def collect_naver_news_topics():
    """네이버 랭킹 뉴스 주요 언론사별 최다 조회 토픽 (언론사 다양성 반영)"""
    results = []
    url = "https://news.naver.com/main/ranking/popularDay.naver"
    page_html = fetch_url(url, encoding="euc-kr")
    if not page_html:
        return results
    try:
        matches = re.findall(r'<a href="([^"]*article/(\d+)/[^"]*)"[^>]*>([^<]+)</a>', page_html)
        seen_titles = set()
        seen_press = set()
        candidates = []

        for link, oid, title in matches:
            t = clean_text(title)
            if len(t) < 6 or t in seen_titles:
                continue
            seen_titles.add(t)
            full_url = link if link.startswith("http") else f"https://news.naver.com{link}"
            candidates.append((oid, t, full_url))

        # Pass 1: Top #1 article from each unique media outlet
        selected = []
        leftover = []
        for oid, t, full_url in candidates:
            if oid not in seen_press:
                seen_press.add(oid)
                selected.append((t, full_url))
            else:
                leftover.append((t, full_url))
            if len(selected) >= 10:
                break

        # Pass 2: Fill up to 10 if fewer than 10 outlets matched
        for t, full_url in leftover:
            if len(selected) >= 10:
                break
            selected.append((t, full_url))

        for rank, (t, full_url) in enumerate(selected, 1):
            results.append({
                "rank": rank,
                "keyword": t,
                "change": "hot",
                "traffic": "랭킹뉴스",
                "url": full_url,
                "news": [],
            })
    except Exception as e:
        print(f"[!] Naver news parse error: {e}", file=sys.stderr)
    return results


def collect_nate_pann():
    """네이트판 실시간 랭킹 톡 (국내 대형 커뮤니티 핫이슈)"""
    results = []
    url = "https://pann.nate.com/talk/ranking"
    page_html = fetch_url(url, encoding="utf-8")
    if not page_html:
        return results
    try:
        items = re.findall(r'<a href="(/talk/\d+)"[^>]*title="([^"]+)"', page_html)
        seen = set()
        rank = 1
        for href, title in items:
            clean_t = clean_text(title)
            if clean_t and clean_t not in seen and len(clean_t) >= 3:
                seen.add(clean_t)
                results.append({
                    "rank": rank,
                    "keyword": clean_t,
                    "change": "hot",
                    "traffic": "커뮤니티",
                    "url": f"https://pann.nate.com{href}",
                    "news": [],
                })
                rank += 1
                if rank > 15:
                    break
    except Exception as e:
        print(f"[!] Nate Pann parse error: {e}", file=sys.stderr)
    return results


def collect_google_news():
    """구글 뉴스 대한민국 주요 속보 (신뢰할 수 있는 언론사 종합 피드)"""
    results = []
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    raw_xml = fetch_url(url, encoding="utf-8")
    if not raw_xml:
        return results
    try:
        tree = ET.fromstring(raw_xml)
        items = tree.findall(".//item")
        seen = set()
        rank = 1
        for item in items:
            title_node = item.find("title")
            link_node = item.find("link")
            if title_node is None or not title_node.text:
                continue
            t = clean_text(title_node.text)
            outlet = "주요속보"
            if " - " in t:
                parts = t.rsplit(" - ", 1)
                t = parts[0].strip()
                outlet = parts[1].strip() or "주요속보"

            if t and t not in seen and len(t) >= 4:
                seen.add(t)
                link = (
                    link_node.text.strip()
                    if link_node is not None and link_node.text
                    else "https://news.google.com"
                )
                results.append({
                    "rank": rank,
                    "keyword": t,
                    "change": "new",
                    "traffic": outlet,
                    "url": link,
                    "news": [],
                })
                rank += 1
                if rank > 15:
                    break
    except Exception as e:
        print(f"[!] Google News parse error: {e}", file=sys.stderr)
    return results


def collect_all():
    now_kst = datetime.datetime.now(KST)
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    now_iso = now_kst.isoformat(timespec="seconds")

    print(f"[*] Starting trends collection at {now_str} KST...")

    google = collect_google_trends()
    signal = collect_signal_trends()
    twitter = collect_twitter_trends()
    nate = collect_nate_trends()
    naver = collect_naver_news_topics()
    community = collect_nate_pann()
    gnews = collect_google_news()

    all_items = []
    for idx, item in enumerate(
        signal[:3] + twitter[:3] + google[:3] + community[:3] + gnews[:3], 1
    ):
        all_items.append({**item, "rank": idx})

    payload = {
        "updated_at": now_str,
        "updated_at_iso": now_iso,
        "timezone": "KST",
        "next_update_in_seconds": 3600,
        "platforms": {
            "all": {
                "name": "전체 종합 (TOP 통합)",
                "icon": "🔥",
                "items": all_items,
            },
            "twitter": {
                "name": "X (구 트위터)",
                "icon": "𝕏",
                "description": "실시간 대한민국 트렌드 및 바이럴 해시태그",
                "items": twitter,
            },
            "signal": {
                "name": "네이버 실검 (Signal)",
                "icon": "🟢",
                "description": "네이버 검색/뉴스 빅데이터 실시간 급상승",
                "items": signal,
            },
            "google": {
                "name": "구글 트렌드 (Google)",
                "icon": "🌐",
                "description": "구글 코리아 일별 및 실시간 급상승 검색어",
                "items": google,
            },
            "nate": {
                "name": "네이트 실검 (Nate)",
                "icon": "🔴",
                "description": "네이트 포털 실시간 이슈 키워드 1~10위",
                "items": nate,
            },
            "naver_news": {
                "name": "네이버 랭킹 뉴스",
                "icon": "📰",
                "description": "주요 언론사별 최다 조회 뉴스 헤드라인",
                "items": naver,
            },
            "community": {
                "name": "커뮤니티 핫토픽",
                "icon": "💬",
                "description": "국내 대형 커뮤니티(네이트판) 실시간 인기글",
                "items": community,
            },
            "google_news": {
                "name": "주요 언론 속보",
                "icon": "⚡",
                "description": "국내 주요 언론사 실시간 헤드라인 속보 (구글 뉴스)",
                "items": gnews,
            },
        },
    }
    return payload


def write_sitemap(out_dir, lastmod):
    """Update sitemap.xml lastmod so search crawlers see hourly updates."""
    sitemap_path = os.path.join(out_dir, "sitemap.xml")
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        "    <loc>https://hotfeedlive.store/</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        "    <changefreq>hourly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml_content)


def save_trends(data, out_dir=None):
    if out_dir is None:
        out_dir = os.path.dirname(os.path.abspath(__file__))

    total_items = sum(
        len(v.get("items", []))
        for k, v in data.get("platforms", {}).items()
        if k != "all"
    )
    out_path = os.path.join(out_dir, "trends.json")
    js_path = os.path.join(out_dir, "trends_data.js")

    if total_items == 0 and os.path.exists(out_path):
        print("[!] All sources returned 0 items; keeping previous cached files.", file=sys.stderr)
        return False

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.INITIAL_TRENDS = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")

    lastmod = data.get("updated_at_iso") or datetime.datetime.now(KST).isoformat(timespec="seconds")
    write_sitemap(out_dir, lastmod)

    print(f"[OK] Saved {total_items} trends to {out_path} and {js_path}")
    return True


if __name__ == "__main__":
    data = collect_all()
    save_trends(data)
