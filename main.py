import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import json

# 페이지 설정
st.set_page_config(layout="wide", page_title="학생 점수 대시보드")

st.title("📚 학생 점수 대시보드")
st.write("구글 시트에서 학생 점수 데이터를 가져와 시각화합니다.")

# Google Sheets 인증
try:
    credentials_info = st.secrets["connections"]["gsheets"]["private_gsheets_credentials"]
    if isinstance(credentials_info, str):
        credentials_info = json.loads(credentials_info)
    credentials = Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(credentials)
    spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    spreadsheet = gc.open_by_url(spreadsheet_url)
except Exception as e:
    st.error(f"Google Sheets 연결에 실패했습니다: {e}")
    st.info("Google Sheets 인증 정보가 올바르게 설정되었는지 확인해주세요.")
    st.stop()

# --- 동적 시트 이름 가져오기 ---
@st.cache_data(ttl=300)  # 5분마다 갱신
def get_worksheet_names():
    try:
        return spreadsheet.worksheets()
    except Exception as e:
        st.error(f"워크시트 목록을 가져오는 데 실패했습니다: {e}")
        return []

worksheets = get_worksheet_names()
WORKSHEET_NAMES = [ws.title for ws in worksheets]

if not WORKSHEET_NAMES:
    st.warning("워크시트가 없습니다. 구글 시트에 적어도 하나의 시트를 추가해주세요.")
    st.stop()

# --- 시트 선택 기능 ---
selected_worksheet_name = st.sidebar.selectbox(
    "데이터를 가져올 시트를 선택하세요:",
    WORKSHEET_NAMES
)

@st.cache_data(ttl=300)  # 5분마다 갱신
def load_data(worksheet_name):
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        df = df.dropna(how="all")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.encode('utf-8', errors='ignore').str.decode('utf-8')
        return df
    except Exception as e:
        st.error(f"'{worksheet_name}' 시트에서 데이터를 불러오는 데 실패했습니다: {e}")
        return pd.DataFrame()

# 버튼 스타일링 CSS
st.markdown("""
    <style>
    .refresh-button {
        background-color: #DC3545;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 16px;
    }
    .refresh-button:hover {
        background-color: #DC3545;
    }
    </style>
    """, unsafe_allow_html=True)

# 버튼을 오른쪽 끝으로 배치
col1, col2 = st.columns([4, 1])  # 왼쪽 80%, 오른쪽 20% 비율
with col1:
    st.write("")  # 빈 공간
with col2:
    if st.button("데이터 새로고침", key="refresh_button"):
        st.cache_data.clear()  # 캐시 초기화
        st.rerun()  # 앱 새로고침
    # 버튼에 CSS 클래스 적용
    st.markdown(
        '<style>#refresh_button {display: none;} .stButton button {background-color: #007BFF; color: white;}</style>',
        unsafe_allow_html=True
    )

df = load_data(selected_worksheet_name)

if df.empty:
    st.info("선택된 시트에서 데이터를 찾을 수 없습니다. 시트 내용을 확인해주세요.")
    st.stop()

# 데이터 전처리 및 확인
expected_columns = ["번호", "이름", "성별"]
score_columns = [col for col in df.columns if col not in expected_columns]
if not all(col in df.columns for col in expected_columns):
    st.error(f"데이터에 예상된 열 {expected_columns}이(가) 없습니다. 구글 시트의 열 구조를 확인해주세요.")
    st.dataframe(df, hide_index=True)
    st.stop()

# 점수 데이터를 숫자로 변환
for col in score_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 전체 평균 계산
overall_averages = df[score_columns].mean().reset_index()
overall_averages.columns = ["단원", "평균 점수"]

# --- 사이드바에 이름 목록 표시 ---
st.sidebar.header("학생 선택")
student_names = [name for name in df["이름"].tolist() if pd.notna(name)]

if not student_names:
    st.sidebar.warning("학생 이름을 찾을 수 없습니다. '이름' 컬럼을 확인해주세요.")
    st.stop()

selected_student = st.sidebar.radio("학생 이름을 클릭하세요:", student_names)

# --- 선택된 학생의 데이터 미리보기 및 시각화 ---
if selected_student:
    st.header(f"{selected_student} 학생의 점수 대시보드")

    # 선택된 학생 데이터 필터링
    student_df = df[df["이름"] == selected_student]
    st.write(f"'{selected_worksheet_name}' 시트에서 '{selected_student}' 학생 데이터 미리보기:")
    st.dataframe(student_df[expected_columns + score_columns], hide_index=True)

    student_data = student_df.iloc[0]
    student_scores = pd.DataFrame({
        "단원": score_columns,
        "점수": [student_data[col] for col in score_columns]
    })

    plot_df = pd.merge(overall_averages, student_scores, on="단원", how="left")
    plot_df.columns = ["단원", "전체 평균", "내 점수"]

    fig = px.line(
        plot_df,
        x="단원",
        y=["전체 평균", "내 점수"],
        title=f"{selected_student} 학생 점수 및 전체 평균 비교",
        labels={"value": "점수", "variable": "구분"},
        markers=True
    )

    fig.update_layout(
        hovermode="x unified",
        xaxis_title="단원",
        yaxis_title="점수",
        legend_title="범례",
        font=dict(family="Arial", size=12, color="RebeccaPurple"),
        width=800,
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("세부 점수")
    st.dataframe(plot_df.set_index("단원"))  # 인덱스 숨김 제거하여 "단원" 표시

else:
    st.info("왼쪽 사이드바에서 학생을 선택하여 대시보드를 확인하세요.")
