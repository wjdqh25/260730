import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="광주·전남 고령화 및 청소년 지표 지도", layout="wide")
st.title("🗺️ 광주·전남 고령화 지도 및 청소년 인구 추이")
st.markdown("선택한 지역의 고령화율(%)을 지도로 확인하고, 주요 인구 지표의 변화를 달리기 애니메이션으로 분석합니다.")

# -----------------------------------------------------------------------------
# 2. 데이터 불러오기 및 사전 가공 (캐싱 적용)
# -----------------------------------------------------------------------------
@st.cache_data
def load_and_preprocess_data():
    pop_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    df = pd.read_csv(pop_url, dtype={'코드': str})
    
    geo_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    geojson_data = requests.get(geo_url).json()
    
    # 행정구역 개편에 따른 코드 및 이름 일괄 보정
    df['시군구코드'] = df['코드'].str[:5]
    df.loc[df['시군구코드'].str.startswith('42'), '시군구코드'] = '51' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('강원도', '강원특별자치도')
    df.loc[df['시군구코드'].str.startswith('45'), '시군구코드'] = '52' + df['시군구코드'].str[2:]
    df['시도'] = df['시도'].replace('전라북도', '전북특별자치도')
    df.loc[df['시군구코드'] == '47720', '시군구코드'] = '27720'
    df.loc[df['시군구코드'] == '27720', '시도'] = '대구광역시'

    # 나이 열 분류 (총인구, 65세 이상, 9~24세 청소년)
    total_cols = [col for col in df.columns if col.startswith('계_') and '세' in col]
    old_cols = []
    youth_cols = []
    
    for col in total_cols:
        num_str = col.replace('계_', '').replace('세 이상', '').replace('세', '')
        if num_str.isdigit():
            age = int(num_str)
            if age >= 65: old_cols.append(col)
            if 9 <= age <= 24: youth_cols.append(col)

    # 시군구 단위 합산
    df_grouped = df.groupby(['연도', '시군구코드', '시도', '시군구'])[total_cols].sum().reset_index()
    
    df_grouped['총인구'] = df_grouped[total_cols].sum(axis=1)
    df_grouped['고령인구'] = df_grouped[old_cols].sum(axis=1)
    df_grouped['청소년인구'] = df_grouped[youth_cols].sum(axis=1)
    
    df_grouped['고령화율(%)'] = (df_grouped['고령인구'] / df_grouped['총인구'] * 100).round(1)
    
    return df_grouped, geojson_data

with st.spinner("데이터를 준비하는 중입니다..."):
    df_all, geojson_kr = load_and_preprocess_data()

# 분석용 광주/전남 데이터 미리 분리
df_gj_jn = df_all[df_all['시도'].isin(['광주광역시', '전라남도'])].copy()
min_year = df_all['연도'].min()
max_year = df_all['연도'].max()

# -----------------------------------------------------------------------------
# 3. UI: 시도 선택(드롭다운) & 연도 선택(버튼)
# -----------------------------------------------------------------------------
col_sel1, col_sel2 = st.columns([1, 2])

with col_sel1:
    sido_list = ['광주/전남 전체', '광주광역시', '전라남도']
    selected_sido = st.selectbox("🔍 지역 선택 (지도 확대)", sido_list)

with col_sel2:
    years = sorted(df_all['연도'].unique())
    selected_year = st.radio("📅 조회할 연도를 선택하세요", options=years, horizontal=True, index=len(years)-1)

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. 메인 화면 레이아웃 분할 (지도 영역 3 : 오른쪽 패널 1)
# -----------------------------------------------------------------------------
col_map, col_info = st.columns([3, 1])

# ==========================================
# 왼쪽 영역 (지도)
# ==========================================
with col_map:
    df_map = df_all[df_all['연도'] == selected_year].copy()
    target_sido = ['광주광역시', '전라남도'] if selected_sido == '광주/전남 전체' else [selected_sido]
    df_map = df_map[df_map['시도'].isin(target_sido)]
    
    geo_info = {f['properties']['코드']: {'시도': f['properties']['시도'], '시군구': f['properties']['시군구']} for f in geojson_kr['features']}
    expected_codes = [code for code, info in geo_info.items() if info['시도'] in target_sido]
    
    missing_codes = set(expected_codes) - set(df_map['시군구코드'])
    if missing_codes:
        missing_data = [{'시군구코드': c, '시도': geo_info[c]['시도'], '시군구': geo_info[c]['시군구'], '고령화율(%)': None} for c in missing_codes]
        df_map = pd.concat([df_map, pd.DataFrame(missing_data)], ignore_index=True)
    
    bins = [0, 19, 23, 28, 38, 100]
    labels = ['19% 미만', '19%~23%', '23%~28%', '28%~38%', '38% 이상']
    df_map['고령화율 구간'] = pd.cut(df_map['고령화율(%)'], bins=bins, labels=labels, right=False)
    df_map['고령화율 구간'] = df_map['고령화율 구간'].cat.add_categories(['데이터 없음']).fillna('데이터 없음')
    
    color_scale = ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#cccccc']
    category_order = labels + ['데이터 없음']
    
    fig_map = px.choropleth(
        df_map, geojson=geojson_kr, locations='시군구코드', featureidkey='properties.코드',      
        color='고령화율 구간', color_discrete_sequence=color_scale, category_orders={'고령화율 구간': category_order},
        hover_name='시군구', hover_data={'시군구코드': False, '시도': True, '고령화율(%)': True, '고령화율 구간': False}
    )
    fig_map.update_geos(fitbounds="locations", visible=False)
    fig_map.update_layout(margin={"r":0, "t":0, "l":0, "b":0}, legend_title_text="고령화율 구간")
    st.plotly_chart(fig_map, use_container_width=True)

# ==========================================
# 오른쪽 영역 (정보 하이라이트)
# ==========================================
with col_info:
    st.markdown("### 🏆 광주/전남 주요 지표")
    df_current = df_gj_jn[df_gj_jn['연도'] == selected_year]
    
    # 1. 고령화율 1위 지역
    max_aging_row = df_current.loc[df_current['고령화율(%)'].idxmax()]
    st.markdown("#### 👵 최고 고령화 지역")
    st.info(f"**{max_aging_row['시도']} {max_aging_row['시군구']}**\n\n고령화율: **{max_aging_row['고령화율(%)']}%**")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 2. 청소년 감소율 1위 지역 (최초 연도 대비)
    st.markdown(f"#### 📉 최대 청소년 감소 지역\n({min_year}년 대비)")
    if selected_year == min_year:
        st.warning(f"기준 연도({min_year}년)이므로 감소율을 계산할 수 없습니다.")
    else:
        df_min = df_gj_jn[df_gj_jn['연도'] == min_year]
        df_compare = pd.merge(df_current, df_min, on=['시군구코드', '시도', '시군구'], suffixes=('_현재', '_과거'))
        df_compare['청소년감소율(%)'] = ((df_compare['청소년인구_과거'] - df_compare['청소년인구_현재']) / df_compare['청소년인구_과거'] * 100).round(1)
        max_dec_row = df_compare.loc[df_compare['청소년감소율(%)'].idxmax()]
        st.error(f"**{max_dec_row['시도']} {max_dec_row['시군구']}**\n\n감소율: **{max_dec_row['청소년감소율(%)']}%**\n\n({max_dec_row['청소년인구_과거']:,}명 ➔ {max_dec_row['청소년인구_현재']:,}명)")

# -----------------------------------------------------------------------------
# 5. 고령화율 분석 & 애니메이션
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader(f"📊 {selected_year}년 {selected_sido} 고령화율 현황")

df_rank = df_map.dropna(subset=['고령화율(%)'])
table_cols = ['시도', '시군구', '고령화율(%)', '총인구', '고령인구']

top10_df = df_rank.nlargest(10, '고령화율(%)')[table_cols].reset_index(drop=True)
bottom10_df = df_rank.nsmallest(10, '고령화율(%)')[table_cols].reset_index(drop=True)
top10_df.index += 1; bottom10_df.index += 1

col_t1, col_t2 = st.columns(2)
with col_t1:
    st.markdown("**🚨 고령화율 높은 지역 Top 10**")
    st.dataframe(top10_df, use_container_width=True)
with col_t2:
    st.markdown("**🌱 고령화율 낮은 지역 Top 10**")
    st.dataframe(bottom10_df, use_container_width=True)

# [추가] 고령화 달리기 애니메이션
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🏃‍♂️ 광주·전남 고령화율 변화 달리기 (2015~)")
st.markdown("연도별 지역들의 고령화율 상승 경쟁입니다. **Play(▶)** 버튼을 눌러보세요! (가장 높은 지역엔 🥇 부여)")

df_anim_aging = df_gj_jn.copy()
# 연도별 순위 매기기 및 1위 메달 텍스트 생성
df_anim_aging['순위'] = df_anim_aging.groupby('연도')['고령화율(%)'].rank(method='min', ascending=False)
df_anim_aging['라벨'] = df_anim_aging.apply(lambda x: f"{x['고령화율(%)']}% 🥇" if x['순위'] == 1 else f"{x['고령화율(%)']}%", axis=1)

# y축(시군구)이 애니메이션 중에 흔들리지 않게 가장 최신 연도 기준으로 순서를 고정합니다.
order_aging = df_anim_aging[df_anim_aging['연도'] == max_year].sort_values('고령화율(%)', ascending=True)['시군구'].tolist()

fig_anim_aging = px.bar(
    df_anim_aging, x='고령화율(%)', y='시군구', 
    animation_frame='연도', animation_group='시군구', orientation='h', text='라벨',
    color='고령화율(%)', color_continuous_scale='Reds', category_orders={'시군구': order_aging},
    range_x=[0, df_anim_aging['고령화율(%)'].max() * 1.15]
)
fig_anim_aging.update_traces(textposition='outside')
fig_anim_aging.update_layout(height=800, showlegend=False)
# 애니메이션 재생 속도 조정
if fig_anim_aging.layout.updatemenus:
    fig_anim_aging.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 800

st.plotly_chart(fig_anim_aging, use_container_width=True)


# -----------------------------------------------------------------------------
# 6. 청소년 분석 & 애니메이션
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 광주·전남 청소년 인구 변화 추이")
st.markdown("광주광역시와 전라남도의 연도별 청소년(9~24세) 총 인구수 변화입니다.")

youth_trend = df_gj_jn.groupby(['연도', '시도'])['청소년인구'].sum().reset_index()
fig_youth = px.line(
    youth_trend, x='연도', y='청소년인구', color='시도', markers=True,
    labels={'청소년인구': '청소년 인구 (명)', '연도': '연도'}
)
fig_youth.update_xaxes(type='category')
fig_youth.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
st.plotly_chart(fig_youth, use_container_width=True)

# [추가] 청소년 감소율 달리기 애니메이션
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🏃‍♀️ 광주·전남 청소년 인구 감소율 달리기 (2015년 대비)")
st.markdown(f"**{min_year}년 인구 기준**으로 청소년이 얼마나 빠르게 줄고 있는지 보여줍니다. (감소율 1위 지역엔 🥇 부여)")

# 2015년 기준 인구 가져오기
df_base_youth = df_gj_jn[df_gj_jn['연도'] == min_year][['시군구코드', '청소년인구']].rename(columns={'청소년인구': '기준인구'})
df_anim_youth = pd.merge(df_gj_jn, df_base_youth, on='시군구코드')

# 감소율 계산
df_anim_youth['감소율(%)'] = ((df_anim_youth['기준인구'] - df_anim_youth['청소년인구']) / df_anim_youth['기준인구'] * 100).round(1)

# 순위 매기기 (첫해는 모두 0%이므로 메달 생략)
df_anim_youth['순위'] = df_anim_youth.groupby('연도')['감소율(%)'].rank(method='min', ascending=False)
df_anim_youth['라벨'] = df_anim_youth.apply(
    lambda x: f"{x['감소율(%)']}% 🥇" if x['순위'] == 1 and x['연도'] != min_year else f"{x['감소율(%)']}%", axis=1
)

order_youth = df_anim_youth[df_anim_youth['연도'] == max_year].sort_values('감소율(%)', ascending=True)['시군구'].tolist()

fig_anim_youth = px.bar(
    df_anim_youth, x='감소율(%)', y='시군구',
    animation_frame='연도', animation_group='시군구', orientation='h', text='라벨',
    color='감소율(%)', color_continuous_scale='Blues', category_orders={'시군구': order_youth},
    range_x=[min(0, df_anim_youth['감소율(%)'].min() - 5), df_anim_youth['감소율(%)'].max() * 1.15]
)
fig_anim_youth.update_traces(textposition='outside')
fig_anim_youth.update_layout(height=800, showlegend=False)
if fig_anim_youth.layout.updatemenus:
    fig_anim_youth.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 800

st.plotly_chart(fig_anim_youth, use_container_width=True)
