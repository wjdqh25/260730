import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="광주·전남 고령화 및 청소년 지표 지도", layout="wide")
st.title("🗺️ 광주·전남 고령화 지도 및 청소년 인구 추이")
st.markdown("선택한 지역의 고령화율(%)을 지도로 확인하고, 광주/전남의 주요 인구 지표를 분석합니다.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 및 사전 가공 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data
def load_and_preprocess_data():
    # 1. 인구 데이터 불러오기 ('코드' 열 문자 유지)
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    # 2. 지도 경계 데이터(GeoJSON) 불러오기
    geo_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geo_url).json()
    
    # 3. 행정구역 개편에 따른 코드 및 이름 일괄 보정
    df['시군구코드'] = df['코드'].str[:5]
    df.loc[df['시군구코드'].str.startswith('42'), '시군구코드'] = '51' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('강원도', '강원특별자치도')
    df.loc[df['시군구코드'].str.startswith('45'), '시군구코드'] = '52' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('전라북도', '전북특별자치도')
    df.loc[df['시군구코드'] == '47720', '시군구코드'] = '27720'
    df.loc[df['시군구코드'] == '27720', '시도'] = '대구광역시'

    # 4. 분석에 필요한 나이 열 분류 (총인구, 65세 이상, 9~24세 청소년)
    total_cols = [col for col in df.columns if col.startswith('계_') and '세' in col]
    old_cols = []
    youth_cols = []
    
    for col in total_cols:
        num_str = col.replace('계_', '').replace('세 이상', '').replace('세', '')
        if num_str.isdigit():
            age = int(num_str)
            if age >= 65: old_cols.append(col)
            if 9 <= age <= 24: youth_cols.append(col)

    # 시군구 단위로 합산
    df_grouped = df.groupby(['연도', '시군구코드', '시도', '시군구'])[total_cols].sum().reset_index()
    
    # 인구수 합산
    df_grouped['총인구'] = df_grouped[total_cols].sum(axis=1)
    df_grouped['고령인구'] = df_grouped[old_cols].sum(axis=1)
    df_grouped['청소년인구'] = df_grouped[youth_cols].sum(axis=1)
    
    # 고령화율(%) 계산
    df_grouped['고령화율(%)'] = (df_grouped['고령인구'] / df_grouped['총인구'] * 100).round(1)
    
    return df_grouped, geojson_data

with st.spinner("데이터를 준비하는 중입니다..."):
    df_all, geojson_kr = load_and_preprocess_data()

# -----------------------------------------------------------------------------
# 3. UI: 시도 선택(드롭다운) & 연도 선택(버튼)
# -----------------------------------------------------------------------------
col_sel1, col_sel2 = st.columns([1, 2])

with col_sel1:
    # 드롭다운에 광주광역시와 전라남도만 포함
    sido_list = ['광주/전남 전체', '광주광역시', '전라남도']
    selected_sido = st.selectbox("🔍 지역 선택 (지도 확대)", sido_list)

with col_sel2:
    years = sorted(df_all['연도'].unique())
    selected_year = st.radio(
        "📅 조회할 연도를 선택하세요", 
        options=years, 
        horizontal=True, 
        index=len(years)-1
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. 메인 화면 레이아웃 분할 (지도 영역 3 : 오른쪽 패널 1)
# -----------------------------------------------------------------------------
col_map, col_info = st.columns([3, 1])

# ==========================================
# 왼쪽 영역 (지도) 시작
# ==========================================
with col_map:
    # 4-1. 지도용 데이터 필터링
    df_map = df_all[df_all['연도'] == selected_year].copy()
    
    if selected_sido == '광주/전남 전체':
        target_sido = ['광주광역시', '전라남도']
    else:
        target_sido = [selected_sido]
        
    df_map = df_map[df_map['시도'].isin(target_sido)]
    
    geo_info = {
        f['properties']['코드']: {'시도': f['properties']['시도'], '시군구': f['properties']['시군구']} 
        for f in geojson_kr['features']
    }
    expected_codes = [code for code, info in geo_info.items() if info['시도'] in target_sido]
    
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
    
    bins = [0, 19, 23, 28, 38, 100]
    labels = ['19% 미만', '19%~23%', '23%~28%', '28%~38%', '38% 이상']
    df_map['고령화율 구간'] = pd.cut(df_map['고령화율(%)'], bins=bins, labels=labels, right=False)
    df_map['고령화율 구간'] = df_map['고령화율 구간'].cat.add_categories(['데이터 없음'])
    df_map['고령화율 구간'] = df_map['고령화율 구간'].fillna('데이터 없음')
    
    # 4-2. 지도 그리기 (Plotly)
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


# ==========================================
# 오른쪽 영역 (정보 하이라이트) 시작
# ==========================================
with col_info:
    st.markdown("### 🏆 광주/전남 주요 지표")
    
    # 분석 대상 데이터 필터링 (선택 연도 기준 광주/전남 전체)
    df_gj_jn = df_all[df_all['시도'].isin(['광주광역시', '전라남도'])].copy()
    df_current = df_gj_jn[df_gj_jn['연도'] == selected_year]
    
    # 1. 고령화율 가장 높은 시군구 찾기
    max_aging_row = df_current.loc[df_current['고령화율(%)'].idxmax()]
    
    st.markdown("#### 👵 최고 고령화 지역")
    st.info(
        f"**{max_aging_row['시도']} {max_aging_row['시군구']}**\n\n"
        f"고령화율: **{max_aging_row['고령화율(%)']}%**"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 2. 청소년 감소율 가장 높은 시군구 찾기 (최초 연도 대비)
    min_year = df_all['연도'].min()
    st.markdown(f"#### 📉 최대 청소년 감소 지역\n({min_year}년 대비)")
    
    if selected_year == min_year:
        st.warning(f"기준 연도({min_year}년)이므로 감소율을 계산할 수 없습니다.")
    else:
        # 최초 연도 데이터 추출
        df_min = df_gj_jn[df_gj_jn['연도'] == min_year]
        
        # 현재 연도와 최초 연도 데이터를 시군구 기준으로 병합하여 비교
        df_compare = pd.merge(
            df_current, df_min, 
            on=['시군구코드', '시도', '시군구'], 
            suffixes=('_현재', '_과거')
        )
        
        # 감소율 계산: (과거 인구 - 현재 인구) / 과거 인구 * 100
        df_compare['청소년감소율(%)'] = ((df_compare['청소년인구_과거'] - df_compare['청소년인구_현재']) / df_compare['청소년인구_과거'] * 100).round(1)
        
        # 가장 많이 감소한 지역 찾기
        max_dec_row = df_compare.loc[df_compare['청소년감소율(%)'].idxmax()]
        
        st.error(
            f"**{max_dec_row['시도']} {max_dec_row['시군구']}**\n\n"
            f"감소율: **{max_dec_row['청소년감소율(%)']}%**\n\n"
            f"({max_dec_row['청소년인구_과거']:,}명 ➔ {max_dec_row['청소년인구_현재']:,}명)"
        )


# -----------------------------------------------------------------------------
# 5. 표 나란히 보여주기 (선택된 지역 기준)
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader(f"📊 {selected_year}년 {selected_sido} 고령화율 현황")

df_rank = df_map.dropna(subset=['고령화율(%)'])
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
# 6. 광주·전남 청소년 인구 증가(추이) 단독 분석
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 광주·전남 청소년 인구 변화 추이")
st.markdown("광주광역시와 전라남도의 연도별 청소년(9~24세) 총 인구수 변화입니다.")

df_youth = df_all[df_all['시도'].isin(['광주광역시', '전라남도'])]
youth_trend = df_youth.groupby(['연도', '시도'])['청소년인구'].sum().reset_index()

fig_youth = px.line(
    youth_trend, 
    x='연도', 
    y='청소년인구', 
    color='시도', 
    markers=True,
    labels={'청소년인구': '청소년 인구 (명)', '연도': '연도'}
)

fig_youth.update_xaxes(type='category')
fig_youth.update_layout(
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig_youth, use_container_width=True)
