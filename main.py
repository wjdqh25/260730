import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("🗺️ 전국 시군구 고령화 지도")
st.markdown("가장 최근 연도의 인구 데이터를 바탕으로 전국 시군구별 65세 이상 인구 비율(%)을 보여줍니다.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 함수 (캐싱 적용)
# -----------------------------------------------------------------------------
# @st.cache_data를 쓰면 데이터를 매번 다운로드하지 않고 임시 저장(캐시)해두어 속도가 빠릅니다.
@st.cache_data
def load_data():
    # 인구 데이터 불러오기
    # '코드' 열은 숫자가 아닌 문자로 읽어오도록 설정합니다. (앞의 0이 사라지지 않게)
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 지도 경계 데이터(GeoJSON) 불러오기
    # requests 모듈을 이용해 웹에서 JSON 데이터를 바로 가져옵니다.
    geo_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geo_url).json()
    
    return df, geojson_data

# 데이터 로딩 실행
with st.spinner("데이터를 불러오고 계산하는 중입니다..."):
    df_raw, geojson_kr = load_data()

# -----------------------------------------------------------------------------
# 3. 데이터 가공하기 (가장 최신 연도 기준, 시군구 단위로 묶기)
# -----------------------------------------------------------------------------
# 가장 최신 연도 찾기
latest_year = df_raw['연도'].max()
st.subheader(f"📍 {latest_year}년 기준 고령화율")

# 최신 연도 데이터만 필터링
df = df_raw[df_raw['연도'] == latest_year].copy()

# '코드' 열의 앞 5자리를 잘라 '시군구코드'를 만듭니다. (시군구 단위 병합용)
df['시군구코드'] = df['코드'].str[:5]

# 총 인구와 65세 이상 인구를 구할 열(Column) 이름 리스트 만들기
# '계_'로 시작하면서 '세'라는 글자가 들어간 열들 중에서 총인구와 고령인구를 분리합니다.
total_cols = []
old_cols = []

for col in df.columns:
    if col.startswith('계_') and '세' in col:
        total_cols.append(col) # 0세부터 100세 이상까지 전체
        
        # 열 이름에서 숫자만 빼내서 65 이상인지 확인 (예: '계_65세' -> 65)
        # '100세 이상'도 처리하기 위해 숫자가 아닌 글자는 빈칸으로 바꿔줍니다.
        num_str = col.replace('계_', '').replace('세 이상', '').replace('세', '')
        if num_str.isdigit() and int(num_str) >= 65:
            old_cols.append(col)

# 읍면동 단위의 데이터를 각 행마다 총인구와 고령인구로 합산
df['총인구'] = df[total_cols].sum(axis=1)
df['고령인구'] = df[old_cols].sum(axis=1)

# 읍면동 데이터를 '시군구코드', '시도', '시군구' 기준으로 그룹화하여 모두 더해줍니다.
df_sigungu = df.groupby(['시군구코드', '시도', '시군구'])[['총인구', '고령인구']].sum().reset_index()

# 고령화율(%) 계산 (소수점 첫째 자리까지 표시)
df_sigungu['고령화율(%)'] = (df_sigungu['고령인구'] / df_sigungu['총인구']) * 100
df_sigungu['고령화율(%)'] = df_sigungu['고령화율(%)'].round(1)

# -----------------------------------------------------------------------------
# 4. 지도 색상(단계별 구간) 설정하기
# -----------------------------------------------------------------------------
# 5단계 구간 나누기 (0~19, 19~23, 23~28, 28~38, 38~100)
# right=False 옵션은 왼쪽 값은 포함하고 오른쪽 값은 포함하지 않는다는 뜻입니다. (예: 19% 미만)
bins = [0, 19, 23, 28, 38, 100]
labels = ['19% 미만', '19%~23%', '23%~28%', '28%~38%', '38% 이상']

df_sigungu['고령화율 구간'] = pd.cut(df_sigungu['고령화율(%)'], bins=bins, labels=labels, right=False)

# -----------------------------------------------------------------------------
# 5. 지도 그리기 (Plotly)
# -----------------------------------------------------------------------------
# 낮은 구간은 옅은 빨강, 높은 구간은 진한 빨강으로 색상 리스트를 지정합니다.
color_scale = ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15']

fig = px.choropleth(
    df_sigungu,
    geojson=geojson_kr,                  # 불러온 GeoJSON 경계 데이터
    locations='시군구코드',              # 데이터프레임에서 경계와 매칭할 열 (5자리 코드)
    featureidkey='properties.코드',      # GeoJSON 안에서 매칭할 키 (속성의 '코드')
    color='고령화율 구간',               # 색을 칠할 기준 열
    color_discrete_sequence=color_scale, # 5단계 지정 색상 사용
    category_orders={'고령화율 구간': labels}, # 범례 순서 고정
    hover_name='시군구',                 # 마우스를 올렸을 때 제목으로 보일 열
    hover_data={                         # 툴팁(hover)에 보일 세부 정보 설정
        '시군구코드': False, 
        '시도': True, 
        '고령화율(%)': True, 
        '고령화율 구간': False
    }
)

# 배경 지도를 없애고(visible=False), 폴리곤(경계선)만 꽉 차게 보이도록(fitbounds="locations") 설정합니다.
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r":0, "t":30, "l":0, "b":0},
    legend_title_text="고령화율 구간",
)

# 스트림릿에 지도 출력
st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# 6. 표 나란히 보여주기 (Top 10 / Bottom 10)
# -----------------------------------------------------------------------------
st.markdown("---")

# 레이아웃을 2개의 단(Column)으로 나눕니다.
col1, col2 = st.columns(2)

# 표에 보여줄 컬럼만 추려냅니다.
table_columns = ['시도', '시군구', '고령화율(%)', '총인구', '고령인구']

# 고령화율 높은 순으로 정렬 후 10개 추출
top10_df = df_sigungu.nlargest(10, '고령화율(%)')[table_columns].reset_index(drop=True)
# 고령화율 낮은 순으로 정렬 후 10개 추출
bottom10_df = df_sigungu.nsmallest(10, '고령화율(%)')[table_columns].reset_index(drop=True)

# 인덱스를 1부터 시작하도록 조정 (보기 좋게)
top10_df.index = top10_df.index + 1
bottom10_df.index = bottom10_df.index + 1

with col1:
    st.subheader("🚨 고령화율 높은 지역 Top 10")
    st.dataframe(top10_df, use_container_width=True)

with col2:
    st.subheader("🌱 고령화율 낮은 지역 Top 10")
    st.dataframe(bottom10_df, use_container_width=True)
