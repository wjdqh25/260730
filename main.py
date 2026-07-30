import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("🗺️ 전국 시군구 고령화 및 지표 분석 지도")
st.markdown("연도 및 시도를 선택하여 지역별 고령화율을 확인하고, 광주·전남 지역의 주요 지표 추이를 분석해 보세요.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 및 사전 가공 (캐싱 적용)
# -----------------------------------------------------------------------------
# 모든 연도의 계산을 미리 해두면 화면을 조작할 때 속도가 훨씬 빠릅니다.
@st.cache_data
def load_and_preprocess_data():
    # 1. 인구 데이터 불러오기 ('코드' 열 문자 유지)
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 2. 지도 경계 데이터(GeoJSON) 불러오기
    geo_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geo_url).json()
    
    # 3. 행정구역 개편에 따른 코드 및 이름 일괄 보정 (모든 연도 공통)
    df['시군구코드'] = df['코드'].str[:5]
    # 강원특별자치도 (42 -> 51)
    df.loc[df['시군구코드'].str.startswith('42'), '시군구코드'] = '51' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('강원도', '강원특별자치도')
    # 전북특별자치도 (45 -> 52)
    df.loc[df['시군구코드'].str.startswith('45'), '시군구코드'] = '52' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('전라북도', '전북특별자치도')
    # 군위군 대구 편입 (47720 -> 27720)
    df.loc[df['시군구코드'] == '47720', '시군구코드'] = '27720'
    df.loc[df['시군구코드'] == '27720', '시도'] = '대구광역시'

    # 4. 분석에 필요한 나이 열 분류하기
    total_cols = [col for col in df.columns if col.startswith('계_') and '세' in col]
    old_cols = []   # 65세 이상
    youth_cols = [] # 9~24세 (청소년 기본법 기준)
    birth_cols = ['계_0세'] # 신생아 (출산율 지표 대용)
    
    for col in total_cols:
        num_str = col.replace('계_', '').replace('세 이상', '').replace('세', '')
        if num_str.isdigit():
            age = int(num_str)
            if age >= 65: old_cols.append(col)
            if 9 <= age <= 24: youth_cols.append(col)

    # 읍면동 단위를 시군구 단위로 합산하기 위해 그룹화
    # 숫자 열(인구수)들만 더해줍니다.
    df_grouped = df.groupby(['연도', '시군구코드', '시도', '시군구'])[total_cols].sum().reset_index()
    
    # 주요 지표 인구수 합산
    df_grouped['총인구'] = df_grouped[total_cols].sum(axis=1)
    df_grouped['고령인구'] = df_grouped[old_cols].sum(axis=1)
    df_grouped['청소년인구'] = df_grouped[youth_cols].sum(axis=1)
    df_grouped['신생아인구'] = df_grouped[birth_cols].sum(axis=1)
    
    # 5. 비율(%) 계산
    df_grouped['고령화율(%)'] = (df_grouped['고령인구'] / df_grouped['총인구'] * 100).round(1)
    df_grouped['청소년률(%)'] = (df_grouped['청소년인구'] / df_grouped['총인구'] * 100).round(1)
    df_grouped['신생아비율(%)'] = (df_grouped['신생아인구'] / df_grouped['총인구'] * 100).round(2)
    
    return df_grouped, geojson_data

with st.spinner("데이터를 불러오고 계산하는 중입니다..."):
    df_all, geojson_kr = load_and_preprocess_data()

# -----------------------------------------------------------------------------
# 3. UI: 시도 선택(드롭다운) & 연도 선택(버튼)
# -----------------------------------------------------------------------------
st.markdown("### 🗺️ 맞춤형 고령화 지도 조회")

col_sel1, col_sel2 = st.columns([1, 3])

with col_sel1:
    # 데이터에 존재하는 시도 목록 추출 (가나다순 정렬)
    sido_list = ['전국'] + sorted(df_all['시도'].unique().tolist())
    selected_sido = st.selectbox("🔍 시도 선택 (지도 확대)", sido_list)

with col_sel2:
    years = sorted(df_all['연도'].unique())
    selected_year = st.radio(
        "📅 조회할 연도를 선택하세요", 
        options=years, 
        horizontal=True, 
        index=len(years)-1
    )

# -----------------------------------------------------------------------------
# 4. 지도용 데이터 필터링 및 결측치(회색) 처리
# -----------------------------------------------------------------------------
# 선택한 연도 데이터만 추출
df_map = df_all[df_all['연도'] == selected_year].copy()

# '전국'이 아니라면 특정 시도만 남기기 (이것만으로 Plotly가 알아서 지도를 확대해 줌)
if selected_sido != '전국':
    df_map = df_map[df_map['시도'] == selected_sido]

# GeoJSON 파일에서 현재 선택된 범위('전국' 또는 특정 '시도')에 해당하는 코드 목록 찾기
geo_info = {
    f['properties']['코드']: {'시도': f['properties']['시도'], '시군구': f['properties']['시군구']} 
    for f in geojson_kr['features']
}

if selected_sido != '전국':
    expected_codes = [code for code, info in geo_info.items() if info['시도'] == selected_sido]
else:
    expected_codes = list(geo_info.keys())

# 지도 경계에는 있지만 데이터엔 없는 곳 찾기
missing_codes = set(expected_codes) - set(df_map['시군구코드'])

if missing_codes:
    missing_data = []
    for code in missing_codes:
        missing_data.append({
            '시군구코드': code,
            '시도': geo_info[code]['시도'],
            '시군구': geo_info[code]['시군구'],
            '고령화율(%)': None
        })
    df_map = pd.concat([df_map, pd.DataFrame(missing_data)], ignore_index=True)

# 5단계 구간 나누기 (연도가 달라도 고정)
bins = [0, 19, 23, 28, 38, 100]
labels = ['19% 미만', '19%~23%', '23%~28%', '28%~38%', '38% 이상']
df_map['고령화율 구간'] = pd.cut(df_map['고령화율(%)'], bins=bins, labels=labels, right=False)
df_map['고령화율 구간'] = df_map['고령화율 구간'].cat.add_categories(['데이터 없음'])
df_map['고령화율 구간'] = df_map['고령화율 구간'].fillna('데이터 없음')

# -----------------------------------------------------------------------------
# 5. 지도 그리기 (Plotly)
# -----------------------------------------------------------------------------
color_scale = ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#cccccc']
category_order = labels + ['데이터 없음']

fig = px.choropleth(
    df_map,
    geojson=geojson_kr,                  
    locations='시군구코드',              
    featureidkey='properties.코드',      
    color='고령화율 구간',               
    color_discrete_sequence=color_scale, 
    category_orders={'고령화율 구간': category_order},
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
    margin={"r":0, "t":0, "l":0, "b":0},
    legend_title_text="고령화율 구간",
)

st.plotly_chart(fig, use_container_width=True)
st.info("💡 **안내:** 연도에 따른 행정구역 개편 등으로 옛 데이터와 현재 지도 경계가 일부 맞지 않는 지역은 **회색(데이터 없음)**으로 표시됩니다.")

# -----------------------------------------------------------------------------
# 6. 표 나란히 보여주기 (Top 10 / Bottom 10) - 전국 기준
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader(f"📊 {selected_year}년 전국 고령화율 랭킹")

# 데이터 없음(NaN) 제외
df_rank = df_all[df_all['연도'] == selected_year].dropna(subset=['고령화율(%)'])
table_cols = ['시도', '시군구', '고령화율(%)', '총인구', '고령인구']

top10_df = df_rank.nlargest(10, '고령화율(%)')[table_cols].reset_index(drop=True)
bottom10_df = df_rank.nsmallest(10, '고령화율(%)')[table_cols].reset_index(drop=True)
top10_df.index += 1
bottom10_df.index += 1

col_t1, col_t2 = st.columns(2)
with col_t1:
    st.markdown("**🚨 고령화율 높은 지역 Top 10**")
    st.dataframe(top10_df, use_container_width=True)
with col_t2:
    st.markdown("**🌱 고령화율 낮은 지역 Top 10**")
    st.dataframe(bottom10_df, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. 광주·전남 기준 3대 지표(고령화, 청소년, 출산) 추이 비교
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 광주·전남 지역 3대 지표 추이 분석")
st.markdown(f"**{selected_year}년 기준**, 광주광역시와 전라남도 내에서 각 지표별로 가장 **높은 지역**과 **낮은 지역**의 연도별 변화 추이입니다.")

# 광주·전남 데이터만 필터링
df_gj_jn = df_all[df_all['시도'].isin(['광주광역시', '전라남도'])].copy()
df_gj_jn_current = df_gj_jn[df_gj_jn['연도'] == selected_year]

# 추이 차트를 그리는 도우미 함수
def plot_trend(metric_col, title, unit="비율(%)"):
    # 현재 연도 기준으로 최고/최저 시군구를 찾음
    max_idx = df_gj_jn_current[metric_col].idxmax()
    min_idx = df_gj_jn_current[metric_col].idxmin()
    
    max_row = df_gj_jn_current.loc[max_idx]
    min_row = df_gj_jn_current.loc[min_idx]
    
    # 해당 시군구의 전체 연도 데이터를 뽑아옴
    max_trend = df_gj_jn[df_gj_jn['시군구코드'] == max_row['시군구코드']].copy()
    max_trend['분류'] = f"최고: {max_row['시군구']}"
    
    min_trend = df_gj_jn[df_gj_jn['시군구코드'] == min_row['시군구코드']].copy()
    min_trend['분류'] = f"최저: {min_row['시군구']}"
    
    # 두 지역의 데이터를 하나로 합침
    trend_df = pd.concat([max_trend, min_trend])
    
    # 선 그래프 그리기
    fig_line = px.line(
        trend_df, x='연도', y=metric_col, color='분류', 
        markers=True, title=title,
        labels={metric_col: unit}
    )
    # 연도를 가로축에서 숫자가 아닌 항목(Category)으로 취급해 깔끔하게 보이도록 설정
    fig_line.update_xaxes(type='category')
    fig_line.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    
    return fig_line

# 3개의 지표를 3단으로 나란히 배치
col_c1, col_c2, col_c3 = st.columns(3)

with col_c1:
    fig1 = plot_trend('고령화율(%)', '1️⃣ 고령화율 추이 (65세 이상)')
    st.plotly_chart(fig1, use_container_width=True)

with col_c2:
    fig2 = plot_trend('청소년률(%)', '2️⃣ 청소년률 추이 (9~24세)')
    st.plotly_chart(fig2, use_container_width=True)

with col_c3:
    fig3 = plot_trend('신생아비율(%)', '3️⃣ 신생아(0세) 비율 추이 (출산율 지표)')
    st.plotly_chart(fig3, use_container_width=True)
