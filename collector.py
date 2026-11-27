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
import email.utils
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def write_sitemap(out_dir, lastmod, data=None):
    """Generate sitemap with main page, archive pages, and top topic pages."""
    sitemap_path = os.path.join(out_dir, "sitemap.xml")
    base = "https://hotfeedlive.store"

    urls = [
        f'  <url>\n    <loc>{base}/</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>hourly</changefreq>\n    <priority>1.0</priority>\n  </url>',
        f'  <url>\n    <loc>{base}/archive.html</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>hourly</changefreq>\n    <priority>0.8</priority>\n  </url>',
    ]

    # Top trending keyword analysis pages (SEO programmatic pages)
    if data:
        seen_kw = set()
        top_kws = []
        for it in data.get("platforms", {}).get("all", {}).get("items", []):
            kw = (it.get("keyword") or "").strip()
            if kw and kw not in seen_kw:
                seen_kw.add(kw)
                top_kws.append(kw)
            if len(top_kws) >= 10:
                break
        if len(top_kws) < 10:
            for k, pinfo in data.get("platforms", {}).items():
                if k == "all" or not isinstance(pinfo, dict):
                    continue
                for it in (pinfo.get("items") or [])[:3]:
                    kw = (it.get("keyword") or "").strip()
                    if kw and kw not in seen_kw:
                        seen_kw.add(kw)
                        top_kws.append(kw)
                    if len(top_kws) >= 10:
                        break
        for kw in top_kws:
            urls.append(
                f'  <url>\n    <loc>{base}/topic.html?k={urllib.parse.quote(kw)}</loc>\n'
                f'    <lastmod>{lastmod}</lastmod>\n    <changefreq>hourly</changefreq>\n'
                f'    <priority>0.7</priority>\n  </url>'
            )

    # Archive date/hour pages
    archives_dir = os.path.join(out_dir, "archives")
    if os.path.isdir(archives_dir):
        for date_dir in sorted(os.listdir(archives_dir)):
            date_path = os.path.join(archives_dir, date_dir)
            if not os.path.isdir(date_path):
                continue
            urls.append(
                f'  <url>\n    <loc>{base}/archive.html?date={date_dir}</loc>\n'
                f'    <lastmod>{lastmod}</lastmod>\n    <changefreq>daily</changefreq>\n'
                f'    <priority>0.6</priority>\n  </url>'
            )
            for fname in sorted(os.listdir(date_path)):
                if not fname.endswith(".json"):
                    continue
                hour = fname.replace(".json", "")
                urls.append(
                    f'  <url>\n    <loc>{base}/archive.html?date={date_dir}&amp;hour={hour}</loc>\n'
                    f'    <lastmod>{date_dir}T{hour}:00:00+09:00</lastmod>\n'
                    f'    <changefreq>never</changefreq>\n    <priority>0.5</priority>\n  </url>'
                )

    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(xml_content)


def _xml_escape(text):
    return html.escape(str(text), quote=False)


def write_rss(data, out_dir):
    """Write RSS 2.0 feed for Korean search engines (Naver Search Advisor, Daum, Zum)."""
    rss_path = os.path.join(out_dir, "rss.xml")
    iso_str = data.get("updated_at_iso") or datetime.datetime.now(KST).isoformat(timespec="seconds")
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
    except ValueError:
        dt = datetime.datetime.now(KST)

    pub_date = email.utils.format_datetime(dt)
    stamp_id = dt.strftime("%Y%m%d%H")
    time_label = dt.strftime("%Y-%m-%d %H:%M KST")

    items_xml = []
    for key, pinfo in data.get("platforms", {}).items():
        if key == "all" or not isinstance(pinfo, dict):
            continue
        p_items = pinfo.get("items") or []
        if not p_items:
            continue

        pname = pinfo.get("name", key)
        pdesc = pinfo.get("description", "")
        summary_lines = [
            f"{it.get('rank', idx)}. {it.get('keyword', '')}"
            for idx, it in enumerate(p_items[:10], 1)
            if it.get("keyword")
        ]
        title_text = f"[{pname}] {time_label} 실시간 트렌드"
        desc_parts = [pdesc] if pdesc else []
        if summary_lines:
            desc_parts.append(" / ".join(summary_lines))
        desc_text = " - ".join(desc_parts)
        link_url = f"https://hotfeedlive.store/?platform={urllib.parse.quote(key)}&t={stamp_id}"
        guid = f"hotfeedlive-{stamp_id}-{key}"

        items_xml.append(
            "    <item>\n"
            f"      <title>{_xml_escape(title_text)}</title>\n"
            f"      <link>{_xml_escape(link_url)}</link>\n"
            f'      <guid isPermaLink="false">{_xml_escape(guid)}</guid>\n'
            f"      <pubDate>{pub_date}</pubDate>\n"
            f"      <description>{_xml_escape(desc_text)}</description>\n"
            "    </item>"
        )

    rss_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>HOTFEED LIVE | 대한민국 실시간 핫검색어 &amp; 핫토픽</title>\n"
        "    <link>https://hotfeedlive.store/</link>\n"
        '    <atom:link href="https://hotfeedlive.store/rss.xml" rel="self" type="application/rss+xml"/>\n'
        "    <description>네이버, X(트위터), 구글, 네이트, 커뮤니티, 주요 언론사의 1시간 주기 실시간 검색어 및 핫토픽 피드</description>\n"
        "    <language>ko</language>\n"
        f"    <lastBuildDate>{pub_date}</lastBuildDate>\n"
        + "\n".join(items_xml)
        + "\n  </channel>\n"
        "</rss>\n"
    )
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(rss_content)


def save_archive(data, out_dir):
    """Save hourly archive snapshot and update archive index."""
    iso_str = data.get("updated_at_iso") or datetime.datetime.now(KST).isoformat(timespec="seconds")
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
    except ValueError:
        dt = datetime.datetime.now(KST)

    date_str = dt.strftime("%Y-%m-%d")
    hour_str = dt.strftime("%H")

    archive_dir = os.path.join(out_dir, "archives", date_str)
    os.makedirs(archive_dir, exist_ok=True)

    archive_path = os.path.join(archive_dir, f"{hour_str}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Update master index
    archives_root = os.path.join(out_dir, "archives")
    index = {}
    for d in sorted(os.listdir(archives_root)):
        dp = os.path.join(archives_root, d)
        if not os.path.isdir(dp):
            continue
        hours = sorted([fn.replace(".json", "") for fn in os.listdir(dp) if fn.endswith(".json")])
        if hours:
            index[d] = hours
    with open(os.path.join(archives_root, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    print(f"[OK] Archived {date_str}/{hour_str}.json ({len(index)} days total)")


def _find_headless_browser():
    for cmd in ["google-chrome", "chromium", "chromium-browser", "chrome", "msedge"]:
        path = shutil.which(cmd)
        if path:
            return path
    win_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in win_candidates:
        if os.path.exists(path):
            return path
    return None


def generate_og_image(data, out_dir):
    """Generate 1200x630 Open Graph SVG and PNG card with TOP 10 trending keywords."""
    all_items = data.get("platforms", {}).get("all", {}).get("items", [])
    if not all_items:
        all_items = []
        for key, pinfo in data.get("platforms", {}).items():
            if key == "all" or not isinstance(pinfo, dict):
                continue
            all_items.extend((pinfo.get("items") or [])[:3])

    top_keywords = []
    seen = set()
    for it in all_items:
        kw = (it.get("keyword") or "").strip()
        if kw and kw not in seen:
            seen.add(kw)
            top_keywords.append(kw)
        if len(top_keywords) >= 10:
            break

    now_kst = datetime.datetime.now(KST)
    time_label = now_kst.strftime("%Y.%m.%d %H:%M KST")
    top1 = top_keywords[0] if top_keywords else "실시간 핫트렌드"

    # Build 2-column SVG rows (1-5 left, 6-10 right)
    svg_rows = []
    for i, kw in enumerate(top_keywords):
        col = 0 if i < 5 else 1
        row = i if i < 5 else i - 5
        x = 64 if col == 0 else 622
        y = 248 + row * 68
        display_kw = kw[:18] + ("..." if len(kw) > 18 else "")
        badge_bg = "#ef4444" if i == 0 else ("#4f46e5" if i < 3 else "#e2e8f0")
        badge_fg = "#ffffff" if i < 3 else "#475569"
        svg_rows.append(
            f'<rect x="{x}" y="{y - 34}" width="514" height="54" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>'
            f'<rect x="{x + 12}" y="{y - 23}" width="32" height="32" rx="8" fill="{badge_bg}"/>'
            f'<text x="{x + 28}" y="{y - 1}" text-anchor="middle" font-size="18" fill="{badge_fg}" font-weight="800" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">{i + 1}</text>'
            f'<text x="{x + 58}" y="{y}" font-size="22" fill="#0f172a" font-weight="700" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">{_xml_escape(display_kw)}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="hdr" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#4338ca"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="#f8fafc"/>
  <rect width="1200" height="106" fill="url(#hdr)"/>
  <text x="64" y="64" font-size="38" fill="#ffffff" font-weight="800" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">HOTFEED LIVE</text>
  <text x="360" y="62" font-size="20" fill="#e0e7ff" font-weight="600" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">대한민국 실시간 핫검색어 TOP 10</text>
  <text x="1136" y="62" text-anchor="end" font-size="18" fill="#c7d2fe" font-weight="600" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">{time_label}</text>
  <rect x="64" y="128" width="1072" height="60" rx="14" fill="#eef2ff" stroke="#c7d2fe" stroke-width="1.5"/>
  <rect x="82" y="141" width="76" height="34" rx="8" fill="#ef4444"/>
  <text x="120" y="164" text-anchor="middle" font-size="16" fill="#ffffff" font-weight="800" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">LIVE #1</text>
  <text x="176" y="166" font-size="25" fill="#1e1b4b" font-weight="800" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">{_xml_escape(top1[:34])}</text>
  {chr(10).join(svg_rows)}
  <text x="64" y="598" font-size="17" fill="#64748b" font-weight="600" font-family="NanumGothic, Pretendard Variable, Noto Sans KR, Malgun Gothic, sans-serif">hotfeedlive.store · X · 네이버 · 구글 · 네이트 · 커뮤니티 1시간 자동 집계</text>
</svg>'''

    svg_path = os.path.join(out_dir, "og-image.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    # Render PNG for KakaoTalk, X, Naver, Facebook OG compatibility
    browser = _find_headless_browser()
    if browser:
        png_path = os.path.join(out_dir, "og-image.png")
        html_wrapper = f'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>*{{margin:0;padding:0;}}body{{width:1200px;height:630px;overflow:hidden;}}</style></head>
<body>{svg}</body></html>'''
        tmp_html = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", encoding="utf-8", delete=False) as tf:
                tf.write(html_wrapper)
                tmp_html = tf.name
            file_url = "file:///" + tmp_html.replace(os.sep, "/").lstrip("/")
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--virtual-time-budget=2500",
                    f"--screenshot={png_path}",
                    "--window-size=1200,630",
                    file_url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=True,
            )
            print(f"[OK] Generated {png_path}")
        except Exception as e:
            print(f"[!] OG PNG generation notice: {e}", file=sys.stderr)
        finally:
            if tmp_html and os.path.exists(tmp_html):
                os.unlink(tmp_html)


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
    save_archive(data, out_dir)
    write_sitemap(out_dir, lastmod, data)
    write_rss(data, out_dir)
    generate_og_image(data, out_dir)

    print(f"[OK] Saved {total_items} trends to {out_path} and {js_path}")
    return True


if __name__ == "__main__":
    data = collect_all()
    save_trends(data)
