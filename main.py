import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("🗺️ 전국 시군구 고령화 지도")
st.markdown("연도별 전국 시군구의 65세 이상 인구 비율(%)을 보여줍니다. 연도를 변경해 고령화 추이를 확인해 보세요.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 함수 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    # 인구 데이터 불러오기 ('코드' 열을 문자로 유지)
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 지도 경계 데이터(GeoJSON) 불러오기
    geo_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geo_url).json()
    
    return df, geojson_data

with st.spinner("데이터를 불러오고 계산하는 중입니다..."):
    df_raw, geojson_kr = load_data()

# -----------------------------------------------------------------------------
# 3. 연도 선택 UI (버튼 형태)
# -----------------------------------------------------------------------------
# 데이터에 있는 모든 연도를 추출하여 오름차순으로 정렬합니다.
years = sorted(df_raw['연도'].unique())

# st.radio의 horizontal=True 옵션을 사용해 버튼처럼 가로로 배치합니다.
# 기본 선택값은 가장 최근 연도(리스트의 맨 마지막)로 설정합니다.
selected_year = st.radio(
    "📅 조회할 연도를 선택하세요", 
    options=years, 
    horizontal=True, 
    index=len(years)-1
)

st.subheader(f"📍 {selected_year}년 기준 시군구별 고령화율")

# 선택한 연도의 데이터만 따로 빼냅니다.
df = df_raw[df_raw['연도'] == selected_year].copy()

# -----------------------------------------------------------------------------
# 4. 행정구역 코드 보정 및 데이터 가공
# -----------------------------------------------------------------------------
# '코드' 열의 앞 5자리를 잘라 '시군구코드'를 만듭니다.
df['시군구코드'] = df['코드'].str[:5]

# [핵심] 행정구역 개편에 따른 옛 시군구코드 수정 (현재 지도 경계와 맞추기 위함)
# 1. 강원특별자치도 출범: 옛 시도 코드 42 -> 51로 변경
df.loc[df['시군구코드'].str.startswith('42'), '시군구코드'] = '51' + df['시군구코드'].str[2:]
# 2. 전북특별자치도 출범: 옛 시도 코드 45 -> 52로 변경
df.loc[df['시군구코드'].str.startswith('45'), '시군구코드'] = '52' + df['시군구코드'].str[2:]
# 3. 군위군 대구광역시 편입: 옛 코드 47720 -> 27720으로 변경
df.loc[df['시군구코드'] == '47720', '시군구코드'] = '27720'

# 총 인구와 65세 이상 인구를 구할 열 찾기
total_cols = [col for col in df.columns if col.startswith('계_') and '세' in col]
old_cols = []
for col in total_cols:
    num_str = col.replace('계_', '').replace('세 이상', '').replace('세', '')
    if num_str.isdigit() and int(num_str) >= 65:
        old_cols.append(col)

# 읍면동 단위 인구를 합산하여 새 열 생성
df['총인구'] = df[total_cols].sum(axis=1)
df['고령인구'] = df[old_cols].sum(axis=1)

# '시군구코드', '시도', '시군구'를 기준으로 그룹화(합산)
df_sigungu = df.groupby(['시군구코드', '시도', '시군구'])[['총인구', '고령인구']].sum().reset_index()

# 고령화율(%) 계산 (소수점 첫째 자리까지)
df_sigungu['고령화율(%)'] = (df_sigungu['고령인구'] / df_sigungu['총인구']) * 100
df_sigungu['고령화율(%)'] = df_sigungu['고령화율(%)'].round(1)

# -----------------------------------------------------------------------------
# 5. 지도 경계와 안 맞는 지역 처리 (데이터 없음 - 회색 표시용)
# -----------------------------------------------------------------------------
# GeoJSON 파일에서 모든 시군구 코드와 이름 정보를 딕셔너리로 추출합니다.
geo_info = {
    feature['properties']['코드']: {
        '시도': feature['properties']['시도'],
        '시군구': feature['properties']['시군구']
    } 
    for feature in geojson_kr['features']
}

# 지도(GeoJSON)에는 있지만, 현재 계산된 데이터프레임에는 없는 코드를 찾습니다.
missing_codes = set(geo_info.keys()) - set(df_sigungu['시군구코드'])

# 누락된 코드가 있다면 빈 데이터프레임으로 만들어 기존 데이터 아래에 붙여줍니다. (회색 표시용)
if missing_codes:
    missing_data = []
    for code in missing_codes:
        missing_data.append({
            '시군구코드': code,
            '시도': geo_info[code]['시도'],
            '시군구': geo_info[code]['시군구'],
            '총인구': None,
            '고령인구': None,
            '고령화율(%)': None
        })
    missing_df = pd.DataFrame(missing_data)
    df_sigungu = pd.concat([df_sigungu, missing_df], ignore_index=True)

# -----------------------------------------------------------------------------
# 6. 구간(범위) 및 색상 설정 (연도가 바뀌어도 고정)
# -----------------------------------------------------------------------------
bins = [0, 19, 23, 28, 38, 100]
labels = ['19% 미만', '19%~23%', '23%~28%', '28%~38%', '38% 이상']

# 고령화율에 따라 5단계 범주(Label) 할당
df_sigungu['고령화율 구간'] = pd.cut(df_sigungu['고령화율(%)'], bins=bins, labels=labels, right=False)

# 판다스 카테고리에 '데이터 없음'을 추가하고, 값이 비어있는(누락된) 지역을 '데이터 없음'으로 채움
df_sigungu['고령화율 구간'] = df_sigungu['고령화율 구간'].cat.add_categories(['데이터 없음'])
df_sigungu['고령화율 구간'] = df_sigungu['고령화율 구간'].fillna('데이터 없음')

# -----------------------------------------------------------------------------
# 7. 지도 그리기 (Plotly)
# -----------------------------------------------------------------------------
# 기존 5단계 색상(점점 진해지는 빨간색) 뒤에 회색(#cccccc)을 추가합니다.
color_scale = ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#cccccc']
category_order = labels + ['데이터 없음']

fig = px.choropleth(
    df_sigungu,
    geojson=geojson_kr,                  
    locations='시군구코드',              
    featureidkey='properties.코드',      
    color='고령화율 구간',               
    color_discrete_sequence=color_scale, 
    category_orders={'고령화율 구간': category_order}, # 범례 순서 고정
    hover_name='시군구',                 
    hover_data={                         
        '시군구코드': False, 
        '시도': True, 
        '고령화율(%)': True, 
        '고령화율 구간': False
    }
)

fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r":0, "t":30, "l":0, "b":0},
    legend_title_text="고령화율 구간",
)

st.plotly_chart(fig, use_container_width=True)

# 안내 문구 출력
st.info("💡 **안내:** 연도에 따른 행정구역 개편 등으로 옛 데이터와 현재 지도 경계가 일부 맞지 않는 지역은 **회색(데이터 없음)**으로 표시됩니다.")

# -----------------------------------------------------------------------------
# 8. 표 나란히 보여주기 (Top 10 / Bottom 10)
# -----------------------------------------------------------------------------
st.markdown("---")

# '데이터 없음'인 행(고령화율이 NaN인 행)은 제외하고 랭킹을 매깁니다.
df_valid = df_sigungu.dropna(subset=['고령화율(%)'])

col1, col2 = st.columns(2)
table_columns = ['시도', '시군구', '고령화율(%)', '총인구', '고령인구']

top10_df = df_valid.nlargest(10, '고령화율(%)')[table_columns].reset_index(drop=True)
bottom10_df = df_valid.nsmallest(10, '고령화율(%)')[table_columns].reset_index(drop=True)

# 인덱스를 1부터 시작하게 변경
top10_df.index = top10_df.index + 1
bottom10_df.index = bottom10_df.index + 1

with col1:
    st.subheader("🚨 고령화율 높은 지역 Top 10")
    st.dataframe(top10_df, use_container_width=True)

with col2:
    st.subheader("🌱 고령화율 낮은 지역 Top 10")
    st.dataframe(bottom10_df, use_container_width=True)
