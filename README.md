# 🚀 TREND PULSE - 1시간 주기 실시간 검색어 & 핫토픽 허브

대한민국 대형 플랫폼(**X(구 트위터), 네이버 실검(Signal), 구글 트렌드, 네이트 실검, 네이버 랭킹 뉴스, 다음 포털**)의 실시간 급상승 키워드를 1시간마다 자동 수집 및 발신하는 실시간 대시보드 웹 서비스입니다.

---

## 📂 프로젝트 구조

```text
trend_live/
├── .github/workflows/
│   └── update_trends.yml  # [핵심] 1시간마다 GitHub Actions로 자동 크롤링 & push
├── collector.py           # 6개 플랫폼 실시간 키워드 수집 엔진
├── server.py              # 로컬 및 VPS 운영용 내장 웹 서버 (1시간 스케줄러 내장)
├── trends.json            # 1시간마다 갱신되는 실시간 트렌드 데이터
├── index.html             # 모던 다크모드 글래스모피즘 웹 대시보드
├── style.css              # 프리미엄 UI 스타일시트
├── app.js                 # 1시간 카운트다운 타이머, 탭 필터링, 검색, 클립보드 복사
└── vercel.json            # Vercel 원클릭 배포 설정
```

---

## 🌐 1. 도메인 구매 가이드

1. **도메인 등록 대행업체 접속**:
   - 국내 추천: [가비아 (Gabia)](https://www.gabia.com) 또는 [호스팅KR](https://www.hosting.kr)
   - 글로벌/수수료 최저 추천: [Cloudflare Registrar](https://www.cloudflare.com) 또는 [Namecheap](https://www.namecheap.com)
2. **도메인 검색 및 결제**:
   - 예: `mytrendpulse.com`, `realtime-keywords.kr` 등
   - `.com` 또는 `.kr` 기준 연간 약 15,000원 ~ 20,000원 내외.

---

## ⚡ 2. 호스팅 및 배포 방법 (비용 0원 무중단 추천)

### 🥇 플랜 A: GitHub + Vercel (가장 추천, 서버비 0원)

이 방식은 별도의 24시간 켜두는 유료 서버 없이, **GitHub 무료 크론(GitHub Actions)**이 1시간마다 크롤링을 수행하여 최신 데이터를 반영하고, **Vercel**이 전 세계 초고속 무료 CDN으로 호스팅하는 완벽한 서버리스 아키텍처입니다.

1. **GitHub 저장소 생성 및 푸시**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for Trend Pulse"
   git branch -M main
   git remote add origin https://github.com/{내계정}/{저장소이름}.git
   git push -u origin main
   ```
2. **Vercel 무료 배포**:
   - [Vercel.com](https://vercel.com)에 로그인 후 **"Add New Project"** 클릭
   - 방금 올린 GitHub 저장소를 선택하고 **"Deploy"** 클릭 (1분 안에 배포 완료)
3. **도메인 연결**:
   - Vercel 대시보드 -> **Settings** -> **Domains** 메뉴로 이동
   - 구매한 도메인(예: `mytrendpulse.com`) 입력
   - 가비아/호스팅KR의 DNS 설정 화면에서 Vercel이 안내하는 `CNAME` (예: `cname.vercel-dns.com`) 또는 `A 레코드` (`76.76.21.21`)를 추가하면 SSL(https) 보안 인증서까지 무료 자동 발급됩니다.
4. **1시간 자동 갱신 활성화**:
   - `.github/workflows/update_trends.yml` 파일이 이미 포함되어 있어, GitHub에 올리는 즉시 1시간마다 자동으로 크롤러가 실행되어 최신 실검으로 사이트가 갱신됩니다!

---

### 🥈 플랜 B: 독립 가상서버(VPS / AWS Lightsail)에 직접 호스팅할 때

내 서버에 상시 띄워두고 싶다면, 내장된 `server.py`를 실행하기만 하면 됩니다.

1. **서버 실행**:
   ```bash
   python server.py
   ```
2. **백그라운드 무중단 실행 (Linux / VPS 기준)**:
   ```bash
   nohup python3 server.py > server.log 2>&1 &
   ```
   - 내부 스레드 데몬이 1시간(3600초)마다 자동으로 `collector.py`의 `collect_all()`을 실행하여 `trends.json`을 갱신합니다.
3. **도메인 연결**:
   - 도메인 구매 사이트 DNS 관리에서 VPS의 **공인 IP(IPv4)**를 **A 레코드**로 등록합니다.

---

## 💡 플랫폼별 실검/트렌드 수집 기준

- **X (구 트위터)**: 대한민국 실시간 트렌드 및 해시태그 순위
- **네이버 실검 (Signal)**: 네이버 뉴스/검색 빅데이터 기반 실시간 급상승 키워드 1~10위
- **구글 트렌드**: 구글 코리아 일별 및 실시간 급상승 검색어 & 뉴스
- **네이트 실검**: 네이트 포털 실시간 이슈 키워드
- **네이버 랭킹 뉴스**: 네이버 최다 조회수 뉴스 토픽 헤드라인
- **다음 (Daum)**: 다음 포털 주요 포커스/실시간 이슈 토픽
- *(참고) 페이스북은 2018년 이후 개인정보 및 알고리즘 이슈로 실시간 검색어/트렌딩 서비스를 영구 폐지하였으므로, 소셜 트렌드는 X(트위터) 트렌드로 통합 제공됩니다.*
