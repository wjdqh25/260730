import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import time

st.set_page_config(page_title="7월 박스오피스 대시보드", layout="wide")
st.title("🎬 7월 박스오피스")

# 비밀 금고에서 인증키 꺼내기 (코드에는 키를 적지 않는다)
KOBIS_KEY = st.secrets["KOBIS_KEY"]

# --- [기준 연월(7월) 설정] ---
# 배포 서버 시계를 고려해 한국 시간으로 설정
now = datetime.now(ZoneInfo("Asia/Seoul"))

# 7월 데이터가 최소 하루치(7월 1일)라도 존재하려면 오늘이 7월 2일 이후이거나 8월 이후여야 함
if now.month > 7 or (now.month == 7 and now.day > 1):
    target_year = now.year
else:
    target_year = now.year - 1  # 아직 올해 7월 데이터가 없다면 작년 7월 조회

start_date = date(target_year, 7, 1)
last_day_of_july = date(target_year, 7, 31)
yesterday_date = (now - timedelta(days=1)).date()

# 미래 날짜를 조회하지 않도록 7월 31일과 어제 날짜 중 더 이른 날짜까지만 조회
end_date = min(last_day_of_july, yesterday_date)

st.caption(f"조회 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")

# --- [데이터 수집 함수] ---
# 한 달 치 API를 연속 호출하므로, 중복 요청 방지와 로딩 개선을 위해 캐싱(하루) 유지
@st.cache_data(ttl=86400)
def fetch_monthly_boxoffice(year, start_dt, end_dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    all_data = []
    
    current_dt = start_dt
    while current_dt <= end_dt:
        dt_str = current_dt.strftime("%Y%m%d")
        res = requests.get(url, params={"key": KOBIS_KEY, "targetDt": dt_str}, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            if "faultInfo" in data:
                return data # 에러 시 에러 딕셔너리 반환
            
            box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
            all_data.extend(box_list)
            
        # KOBIS API 초당 호출 제한을 피하기 위해 0.1초 대기
        time.sleep(0.1) 
        current_dt += timedelta(days=1)
        
    return all_data

# 로딩 스피너 표시
with st.spinner("7월 한 달간의 일별 박스오피스 데이터를 모아 분석 중입니다..."):
    box_list = fetch_monthly_boxoffice(target_year, start_date, end_date)

if isinstance(box_list, dict) and "faultInfo" in box_list:
    st.error("인증키가 올바르지 않거나 API 한도를 초과했습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요.")
    st.stop()

if not box_list:
    st.warning("조회된 7월 데이터가 없습니다.")
    st.stop()

df_raw = pd.DataFrame(box_list)

# 문자열로 들어온 수치형 데이터를 숫자로 변환
for col in ["audiCnt", "audiAcc", "scrnCnt"]:
    df_raw[col] = pd.to_numeric(df_raw[col])

# --- [7월 한 달 기준으로 데이터 분석 (그룹화)] ---
# 일별 TOP10 데이터를 영화명과 개봉일로 묶어 한 달간의 총관객수 등을 집계
df_monthly = df_raw.groupby(["movieNm", "openDt"]).agg(
    month_audiCnt=("audiCnt", "sum"),     # 7월 한 달간 관객수 합계
    final_audiAcc=("audiAcc", "max"),     # 7월 마지막으로 집계된 누적 관객수
    max_scrnCnt=("scrnCnt", "max")        # 7월 중 해당 영화가 점유했던 최다 스크린수
).reset_index()

# 7월 관객수(month_audiCnt)를 기준으로 내림차순 정렬 후 순위(1, 2, 3...) 부여
df_monthly = df_monthly.sort_values("month_audiCnt", ascending=False).reset_index(drop=True)
df_monthly.index = df_monthly.index + 1
df_monthly = df_monthly.reset_index().rename(columns={"index": "순위"})

# --- [화면 출력부] ---
# 1위 영화 지표 카드 세 장
top = df_monthly.iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("7월 1위", top["movieNm"])
c2.metric("7월 관객수", f"{int(top['month_audiCnt']):,}명")
c3.metric("누적 관객수", f"{int(top['final_audiAcc']):,}명")

# 표를 한국어 열 이름으로 정리하여 상위 10개 출력
table = df_monthly[["순위", "movieNm", "openDt", "month_audiCnt", "final_audiAcc", "max_scrnCnt"]].copy()
table.columns = ["순위", "영화명", "개봉일", "7월 관객수", "누적관객수", "최대 스크린수"]

st.subheader("📋 7월 박스오피스 TOP 10")
st.dataframe(table.head(10), use_container_width=True)

st.subheader("📈 7월 관객수 상위 5편")
top5 = table.head(5)
st.bar_chart(top5.set_index("영화명")["7월 관객수"])
