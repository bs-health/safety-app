import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
from PIL import Image
import plotly.express as px
import plotly.graph_objects as ob

# -----------------------------------------------------------------------------
# [설정] 페이지 기본 구성 및 반응형 UI 레이아웃
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="안전보건 통합 자가진단 및 대시보드", 
    page_icon="🦺",
    layout="wide"
)

DB_FILE = "safety_management.db"
IMAGE_DIR = "uploaded_images"

if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

def init_db():
    """데이터베이스 생성 및 구조 반영"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS safety_evaluation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, company TEXT, branch TEXT, headcount INTEGER, inspector TEXT,
            q1 INT, q2 INT, q3 INT, q4 INT, q5 INT, q6 INT, q7 INT, q8 INT, q9 INT, 
            q10 INT, q11 INT, q12 INT, q13 INT, q14 INT, q15 INT, q16 INT,
            remarks TEXT, image_path TEXT, final_score REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -----------------------------------------------------------------------------
# [기준 데이터] DB.csv 연동 및 문항/배점 마스터 정의
# -----------------------------------------------------------------------------
@st.cache_data
def load_reference_data():
    try:
        df_ref = pd.read_csv('DB.csv', header=None, names=['계약법인', '사업장명'])
        df_ref['계약법인'] = df_ref['계약법인'].str.rstrip('.').str.strip()
        df_ref['사업장명'] = df_ref['사업장명'].str.strip()
        return df_ref
    except:
        return pd.DataFrame(columns=['계약법인', '사업장명'])

df_ref = load_reference_data()
company_list = sorted(df_ref['계약법인'].unique().tolist()) if not df_ref.empty else ["샘플법인"]

QUESTIONS = {
    1: {"title": "년도별 안전보건관리계획서 수립여부", "sect": "안전경영/서류", "tip": "년도별 안전보건관리계획서 수립 여부 확인 (본사 지침 및 필수사항)", "options": {"7점. 당해년도 안전보건관리계획서가 작성되어있고 내용이 충실함": 7, "5점. 안전보건관리계획서가 작성되었으나 정보 최신화 미흡 및 샘플 사용": 5, "-10점. 미작성": -10}},
    2: {"title": "안전보건 경영방침 및 목표", "sect": "안전경영/서류", "tip": "사무실, 휴게실 게시 상태 확인", "options": {"3점. 경영방침 및 당해년도 목표를 사무실, 휴게실 등 게시": 3, "0점. 미 게시": 0}},
    3: {"title": "위험성평가", "sect": "위험성평가", "tip": "최신자료 원본 및 본사 결재본(갑지) 보유 확인, 신규사업장은 최초 실시 여부 확인", "options": {"15점. 위험성 평가 실시 중": 15, "10점. 위험성 평가가 실시 되었으나 결재본이 없음": 10, "0점. 위험성 평가를 미실시하였거나 원본이 없음": 0}},
    4: {"title": "종사자의 의견청취", "sect": "안전경영/서류", "tip": "안전보건팀 카카오톡 홍보채널 게시 또는 사업장 자체 의견청취함 설치 여부", "options": {"2점. 홍보자료가 게시판에 부착되어 있거나 자체 의견청취함 설치됨": 2, "0점. 미부착": 0}},
    5: {"title": "비상대응 훈련 실시", "sect": "비상대응훈련", "tip": "최신자료 원본 및 본사 결재본(갑지) 보유 확인 (1년 이내 훈련 자료 필수)", "options": {"7점. 공종별 비상대응훈련을 실시하였음": 7, "5점. 소방훈련으로 갈음하고 있음, 신규사업장으로 미실시": 5, "0점. 최근 1년이내 훈련 미실시": 0}},
    6: {"title": "관리감독자 지정 및 교육", "sect": "안전교육훈련", "tip": "안전보건관계자 선임 및 교육수료증 보관 여부 확인", "options": {"3점. 법에 맞게 선임되어 있고 지정서 및 교육수료증을 보관하고 있음": 3, "1점. 선임되어 있으나 교육수료증 등 미보유": 1, "0점. 미선임, 야간관리감독자 미선임 등": 0}},
    7: {"title": "관리감독자 업무일지", "sect": "안전교육훈련", "tip": "관리감독자 별도 업무일지 작성 및 결재 여부 확인", "options": {"7점. 선임된 모든 자가 출근일 기준 매일 작성 중이며 결재까지 완료됨": 7, "3점. 작성 내용이 형식적(전부 양호 표시)이며 매일 작성되지 않음": 3, "-5점. 미작성": -5}},
    8: {"title": "정기안전보건교육 수행 여부", "sect": "안전교육훈련", "tip": "모든 근로자가 반기 12시간 정기안전보건교육을 이수했는지 확인", "options": {"7점. 근로자별 교육시간 충족됨": 7, "0점. 근로자별 교육시간 충족 확인이 어려움": 0}},
    9: {"title": "신규입사자안전보건교육 수행 여부", "sect": "안전교육훈련", "tip": "최근 1년 이내 신규입사자 발생 시 입사당일 8시간 이수 및 서명지 확인", "options": {"3점. 최근 1년이내 발생된 신규입사자에 대한 안전보건교육이 완료되었음": 3, "0점. 누락되었거나 실시하고 있지 않음": 0}},
    10: {"title": "특별안전보건교육 수행 여부", "sect": "안전교육훈련", "tip": "시설직 근로자 대상 밀폐, 용접, 전기 취급 특별안전보건교육 각 8시간 확인", "options": {"3점. 시설 근로자 특별안전보건교육 실시됨": 3, "1점. 해당없음 (미화, 보안 등)": 1, "0점. 미실시": 0}},
    11: {"title": "MSDS교육 수행 여부", "sect": "안전교육훈련", "tip": "MSDS 대상물질 취급 시 년 1회 교육 실시 여부 확인", "options": {"5점. 시설 근로자 특별안전보건교육 실시됨": 5, "2점. 해당없음 (보안 등)": 2, "0점. 미실시": 0}},
    12: {"title": "사업장 위험요소 확인", "sect": "현장위험요소", "tip": "그라인더, 고속절단기, 예초기, 용접기 등 방호장치 부착 확인", "options": {"7점. 각각의 기계기구에 방호장치가 전체 부착되어 있음": 7, "5점. 보안 단독 사업장 등 해당사항 없음": 5, "0점. 방호장치가 임의 해제되어 있음": 0}},
    13: {"title": "이동식 사다리의 안전조치", "sect": "현장위험요소", "tip": "1m 이상 사다리 전도방지장치 설치, 2인 1조 작업, 안전모 턱끈 착용 여부", "options": {"15점. 안전인증사다리를 사용하고 보호구 착용 및 전도방지조치가 완료된 상태임": 15, "10점. 사다리 사용하지 않음": 10, "0점. 아웃트리거가 없는 경량 사다리를 사용함": 0, "-10점. 안전조치를 이행하고 있지 않음": -10}},
    14: {"title": "MSDS최신화 및 게시", "sect": "보건관리", "tip": "제출번호가 기재된 MSDS 보유 및 소분용기 경고표지 부착 상태 확인", "options": {"6점. MSDS가 최신화 되어있고, 소분용기 경고표지 부착상태가 양호함": 6, "3점. MSDS가 최신화 되어있으나, 소분용기 경고표지 부착미흡": 3, "1점. MSDS가 최신화 되어있지않으나, 소분용기 경고표지는 부착되어있음": 1, "0점. MSDS 미확보됨": 0}},
    15: {"title": "근로자 건강진단(일반, 특수)", "sect": "보건관리", "tip": "근로자의 건강진단 이력관리 및 결과표 취합 현황 확인", "options": {"7점. 근로자의 일반검진, 특수건강진단의 이력을 관리 중이고 결과표를 취합 중임": 7, "3점. 근로자의 일반검진, 특수건강진단의 이력을 관리중임": 3, "0점. 특수건강진단을 실시하고있으나 이력확인이 안됨": 0}},
    16: {"title": "보호구 지급 및 착용", "sect": "보건관리", "tip": "KCs인증 보호구 사용 및 지급대장 작성, 현장소장 안전화 착용 확인", "options": {"3점. KCs인증 보호구를 사용 중이며 보호구 지급대장이 작성됨": 3, "2점. 보호구를 지급중이나 보호구 지급대장이 미작성": 2, "0점. 보호구를 착용하지 않음": 0, "-5점. 보호구를 지급하지 않음": -5}}
}

SECTIONS_MAP = {
    "안전경영/서류": [1, 2, 4],
    "위험성평가": [3],
    "비상대응훈련": [5],
    "안전교육훈련": [6, 7, 8, 9, 10, 11],
    "현장위험요소": [12, 13],
    "보건관리": [14, 15, 16]
}

# -----------------------------------------------------------------------------
# [사이드바] 네비게이션 제어
# -----------------------------------------------------------------------------
st.sidebar.markdown("## 🏢 안전보건 마스터 탭")
menu = st.sidebar.selectbox("메뉴 선택", ["✍️ 모바일 체크리스트 등록", "📊 PC 경영진 종합 대시보드", "🖨️ 1페이지 요약 및 PDF 출력"])

# -----------------------------------------------------------------------------
# [메뉴 1] 모바일 체크리스트 등록
# -----------------------------------------------------------------------------
if menu == "✍️ 모바일 체크리스트 등록":
    st.title("📋 모바일 안전보건 체크리스트")
    st.markdown("### 🏢 1단계: 기본 정보 입력")
    
    col_date, col_comp, col_br, col_hc, col_name = st.columns(5)
    with col_date: inspect_date = st.date_input("점검 일자", datetime.now())
    with col_comp: selected_company = st.selectbox("계약법인", company_list)
    with col_br:
        filtered_branches = sorted(df_ref[df_ref['계약법인'] == selected_company]['사업장명'].unique().tolist()) if not df_ref.empty else ["샘플사업장"]
        branch = st.selectbox("사업장명", filtered_branches)
    with col_hc: headcount = st.number_input("총 계약 인원수(명)", min_value=0, value=0, step=1)
    with col_name: inspector = st.text_input("점검자 성명", placeholder="홍길동")
    
    st.markdown("---")
    st.markdown("### 📝 2단계: 자가 진단 및 현장 보고 (총 7개 섹션)")
    
    tabs = st.tabs([
        "📄 [A] 안전경영/서류", "🎯 [B] 위험성평가", "🔥 [C] 비상대응훈련", 
        "📚 [D] 안전교육훈련", "🚧 [E] 현장위험요소", "🩺 [F] 보건관리",
        "📸 [G] 지적사항 및 개선조치 (항목 17)"
    ])
    
    answers = {}
    
    def render_tab_questions(q_indices):
        for q_id in q_indices:
            q = QUESTIONS[q_id]
            st.markdown(f"**Q{q_id:02d}. {q['title']}**")
            st.caption(f"💡 작성팁: {q['tip']}")
            try:
                img_path = f"images/{q_id}.png"
                if os.path.exists(img_path):
                    st.image(img_path, caption=f"[{q_id}번 가이드 사진]", width=280)
            except:
                pass
            answers[q_id] = st.radio("배점 항목 선택", list(q["options"].keys()), key=f"ans_{q_id}")
            st.markdown("---")

    with tabs[0]: render_tab_questions(SECTIONS_MAP["안전경영/서류"])
    with tabs[1]: render_tab_questions(SECTIONS_MAP["위험성평가"])
    with tabs[2]: render_tab_questions(SECTIONS_MAP["비상대응훈련"])
    with tabs[3]: render_tab_questions(SECTIONS_MAP["안전교육훈련"])
    with tabs[4]: render_tab_questions(SECTIONS_MAP["현장위험요소"])
    with tabs[5]: render_tab_questions(SECTIONS_MAP["보건관리"])
    
    with tabs[6]:
        st.markdown("#### **항목 17. 사업장 개선 및 지적사항 기록**")
        st.info("💡 본 항목은 최종 서술 서식입니다. 지적사항 사진 촬영과 구체적인 서술 내용을 입력해 주세요.")
        uploaded_file = st.file_uploader("📷 현장 지적사항 사진 업로드 (스마트폰 촬영 가능)", type=["png", "jpg", "jpeg"])
        remarks = st.text_area("내용 작성칸", placeholder="현장에서 발견된 구체적인 지적사항 및 개선 요구 내용을 입력하세요.")
            
    st.markdown("### 📥 3단계: 제출 확인")
    if st.button("📋 평가 결과 최종 제출하기", use_container_width=True):
        if not inspector:
            st.error("🚨 점검자 성명을 반드시 입력해 주세요.")
        else:
            final_score = sum([QUESTIONS[q_id]["options"][ans] for q_id, ans in answers.items()])
            
            saved_img_path = ""
            if uploaded_file is not None:
                saved_img_path = os.path.join(IMAGE_DIR, f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{branch}.png")
                image = Image.open(uploaded_file)
                image.save(saved_img_path)
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO safety_evaluation (
                    date, company, branch, headcount, inspector, q1, q2, q3, q4, q5, q6, q7, q8, q9, 
                    q10, q11, q12, q13, q14, q15, q16, remarks, image_path, final_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                inspect_date.strftime("%Y-%m-%d"), selected_company, branch, headcount, inspector,
                QUESTIONS[1]["options"][answers[1]], QUESTIONS[2]["options"][answers[2]], QUESTIONS[3]["options"][answers[3]],
                QUESTIONS[4]["options"][answers[4]], QUESTIONS[5]["options"][answers[5]], QUESTIONS[6]["options"][answers[6]],
                QUESTIONS[7]["options"][answers[7]], QUESTIONS[8]["options"][answers[8]], QUESTIONS[9]["options"][answers[9]],
                QUESTIONS[10]["options"][answers[10]], QUESTIONS[11]["options"][answers[11]], QUESTIONS[12]["options"][answers[12]],
                QUESTIONS[13]["options"][answers[13]], QUESTIONS[14]["options"][answers[14]], QUESTIONS[15]["options"][answers[15]],
                QUESTIONS[16]["options"][answers[16]], remarks, saved_img_path, float(final_score)
            ))
            conn.commit()
            conn.close()
            st.success(f"🎉 [{branch}]의 안전진단 데이터가 정상 제출되었습니다. 최종 점수: {final_score}점")

# -----------------------------------------------------------------------------
# [메뉴 2] PC 경영진 종합 대시보드
# -----------------------------------------------------------------------------
elif menu == "📊 PC 경영진 종합 대시보드":
    st.title("📊 전사 안전보건 경영 대시보드 (PC 보고용)")
    st.markdown("---")
    
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM safety_evaluation", conn)
    conn.close()
    
    if df.empty:
        st.warning("📥 분석할 데이터가 존재하지 않습니다. 모바일에서 먼저 데이터를 등록해 주세요.")
    else:
        total_avg = round(df['final_score'].mean(), 1)
        above_avg_df = df[df['final_score'] >= total_avg]
        below_avg_df = df[df['final_score'] < total_avg]
        
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="📈 전사 안전보건 평균 점수", value=f"{total_avg} 점")
        with kpi2:
            st.markdown(f"<div style='background-color:#e8f8f5; padding:12px; border-radius:6px; border-left:6px solid #2ecc71;'>"
                        f"<p style='margin:0; color:#16a085;'><b>🟢 전사 평균 이상 사업장 수</b></p>"
                        f"<h2 style='margin:5px 0; color:#111;'>{len(above_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
        with kpi3:
            st.markdown(f"<div style='background-color:#fdedec; padding:12px; border-radius:6px; border-left:6px solid #e74c3c;'>"
                        f"<p style='margin:0; color:#c0392b;'><b>🔴 전사 평균 미달 사업장 (집중 관리)</b></p>"
                        f"<h2 style='margin:5px 0; color:#111;'>{len(below_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
            
        st.markdown("---")
        
        st.markdown("### 🔍 심층 분석 도구")
        show_trend = st.checkbox("📈 사업장 방문 차수별 안전 흐름 추이 분석기 켜기", value=False)
        
        if show_trend:
            unique_branches = sorted(df['branch'].unique().tolist())
            target_branch = st.selectbox("분석할 사업장 선택", unique_branches)
            
            전사평균_df = df.groupby('date')['final_score'].mean().reset_index()
            전사평균_df.columns = ['date', '전사평균']
            
            지정사업장_df = df[df['branch'] == target_branch].sort_values(by='date')
            compare_df = pd.merge(지정사업장_df, 전사평균_df, on='date', how='left')
            
            fig_trend = ob.Figure()
            fig_trend.add_trace(ob.Scatter(x=compare_df['date'], y=compare_df['final_score'], name=f"{target_branch} 점수", mode='lines+markers', line=dict(color='#2ecc71', width=3)))
            fig_trend.add_trace(ob.Scatter(x=compare_df['date'], y=compare_df['전사평균'], name="전사 실시간 평균", mode='lines', line=dict(color='#e74c3c', width=2, dash='dash')))
            
            fig_trend.update_layout(
                title=f"⚖️ [{target_branch}] vs 전사 안전 평균 점수 추이 비교선",
                xaxis_title="점검일자", yaxis_title="안전보건 평가점수 (점)",
                yaxis=dict(range=[-15, 105]),
                template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white"
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            st.markdown("---")
        
        st.markdown("### 🏆 전사 사업장 안전 평가 순위 (고득점 순)")
        rank_df = df.sort_values(by="final_score", ascending=False)[['date', 'company', 'branch', 'final_score', 'inspector']]
        rank_df.columns = ['점검일자', '계약법인', '사업장명', '종합 안전점수(점)', '점검책임자']
        st.dataframe(rank_df, use_container_width=True)
        
        st.markdown("---")
        
        st.markdown("### 🚨 리스크 진단: 전사 항목별 안전 규칙 준수율")
        q_cols = [f'q{i}' for i in range(1, 17)]
        q_avg = df[q_cols].mean()
        
        q_performance = {}
        for col in q_cols:
            q_num = int(col.replace('q',''))
            max_val = max(QUESTIONS[q_num]["options"].values())
            q_performance[QUESTIONS[q_num]["title"]] = round((q_avg[col] / max_val) * 100, 1)
            
        perf_df = pd.DataFrame(list(q_performance.items()), columns=['안전점검항목', '만점 대비 준수율(%)']).sort_values(by='만점 대비 준수율(%)')
        
        fig_large = px.bar(perf_df, x='만점 대비 준수율(%)', y='안전점검항목', orientation='h', 
                           title="전사 항목별 이행도", 
                           color='만점 대비 준수율(%)',
                           color_continuous_scale=['#c0392b', '#e74c3c', '#f39c12', '#2ecc71', '#1abc9c'],
                           range_color=[0, 100], height=550)
        
        fig_large.update_layout(template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white")
        st.plotly_chart(fig_large, use_container_width=True)
        
        st.markdown("#### **🔴 전사 최하위 집중 개선 항목 Top 3 (현장 정밀 지도 대상)**")
        alert_cols = st.columns(3)
        for idx, (_, row) in enumerate(perf_df.head(3).iterrows()):
            with alert_cols[idx]:
                st.error(f"**순위 {idx+1}위 : {row['안전점검항목']}**\n\n전사 평균 준수율이 **{row['만점 대비 준수율(%)']}%**로 매우 취약합니다.")

# -----------------------------------------------------------------------------
# [메뉴 3] 1페이지 요약 및 PDF 출력 창 (마크다운 들여쓰기 100% 제거 완료)
# -----------------------------------------------------------------------------
elif menu == "🖨️ 1페이지 요약 및 PDF 출력":
    st.title("🖨️ 안전점검결과 보고서 요약본")
    
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM safety_evaluation", conn)
    conn.close()
    
    if df.empty:
        st.warning("📥 출력할 데이터가 없습니다.")
    else:
        total_avg = df['final_score'].mean()
        
        df['select_label'] = df['date'] + " | " + df['company'] + " | " + df['branch']
        selected_doc = st.selectbox("출력 대상 보고서 선택", df['select_label'].unique())
        doc_data = df[df['select_label'] == selected_doc].iloc[0]
        
        st.markdown("---")
        st.success("💡 [Ctrl + P] 단축키를 이용해 PDF 저장 시 배경 그래픽 인쇄 옵션을 켜시면 서식이 완벽하게 반영됩니다.")
        
        good_items = []
        bad_items = []
        
        for q_id, q_info in QUESTIONS.items():
            user_score = doc_data[f'q{q_id}']
            max_score = max(q_info["options"].values())
            global_avg = df[f'q{q_id}'].mean()
            
            if user_score == max_score:
                good_items.append(f"✔️ {q_info['title']} ({user_score}점 만점)")
                
            if user_score < 0 or user_score < global_avg:
                reason = "마이너스 감점 발생" if user_score < 0 else f"본 사업장 {user_score}점 vs 전사평균 {round(global_avg,1)}점"
                bad_items.append(f"❌ {q_info['title']} ({reason})")
                
        good_text = "<br>".join(good_items) if good_items else "특출난 우수 항목 없음 (기본 준수 수준)"
        bad_text = "<br>".join(bad_items) if bad_items else "지적 및 감점 항목 없음 (매우 우수)"
        
        sect_scores = []
        sect_averages = []
        sect_names = list(SECTIONS_MAP.keys())
        
        for s_name, q_ids in SECTIONS_MAP.items():
            s_max = sum([max(QUESTIONS[qid]["options"].values()) for qid in q_ids])
            s_get = sum([doc_data[f'q{qid}'] for qid in q_ids])
            sect_scores.append(round((s_get / s_max) * 100, 1) if s_max > 0 else 0)
            
            s_avg_get = sum([df[f'q{qid}'].mean() for qid in q_ids])
            sect_averages.append(round((s_avg_get / s_max) * 100, 1) if s_max > 0 else 0)
            
        fig_radar = ob.Figure()
        fig_radar.add_trace(ob.Scatterpolar(r=sect_scores, theta=sect_names, fill='toself', name='해당 사업장'))
        fig_radar.add_trace(ob.Scatterpolar(r=sect_averages, theta=sect_names, fill='toself', name='전사 평균'))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True,
            title=f"6대 섹션별 전사 평균 대비 안전 이행율 비교 (%)",
            height=380,
            margin=dict(l=40, r=40, t=40, b=40),
            template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white"
        )
        
        bg_color = "#ffffff"
        text_color = "#111111"
        box_good_bg = "#e8f8f5"
        box_bad_bg = "#fdedec"
        table_header = "#f2f2f2"
        border_color = "#333333"
        
        col_rep1, col_rep2 = st.columns([1.5, 1])
        
        with col_rep1:
            # HTML 문자열 앞의 띄어쓰기(들여쓰기)를 완전히 없애서 Streamlit 마크다운 코드 블록 버그 해결
            html_report = f"""
<div style="border: 2px solid {border_color}; padding: 20px; font-family: 'Malgun Gothic', sans-serif; background-color:{bg_color}; color:{text_color}; border-radius: 8px;">
<h2 style="text-align: center; margin-bottom: 20px; text-decoration: underline; letter-spacing:3px; color: #111;">안전보건 정밀 점검 결과서 (요약본)</h2>
<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; color:{text_color}; border: 1px solid {border_color};">
<tr style="background-color: {table_header};">
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; width: 20%; color:#222;">점검일자</td>
<td style="border: 1px solid {border_color}; padding: 8px; width: 30%; background-color:#fff; color:#111;">{doc_data['date']}</td>
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; width: 20%; color:#222;">종합점수</td>
<td style="border: 1px solid {border_color}; padding: 8px; width: 30%; color: #c0392b; font-weight: bold; font-size: 1.2em; background-color:#fff;">{int(doc_data['final_score'])} 점 / 100점 만점</td>
</tr>
<tr style="background-color: {table_header};">
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; color:#222;">계약법인</td>
<td style="border: 1px solid {border_color}; padding: 8px; background-color:#fff; color:#111;">{doc_data['company']}</td>
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; color:#222;">사업장명</td>
<td style="border: 1px solid {border_color}; padding: 8px; font-weight:bold; background-color:#fff; color:#111;">{doc_data['branch']}</td>
</tr>
<tr style="background-color: {table_header};">
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; color:#222;">총 계약인원</td>
<td style="border: 1px solid {border_color}; padding: 8px; background-color:#fff; color:#111;">{doc_data['headcount']} 명</td>
<td style="border: 1px solid {border_color}; padding: 8px; font-weight: bold; color:#222;">점검책임자</td>
<td style="border: 1px solid {border_color}; padding: 8px; background-color:#fff; color:#111;">{doc_data['inspector']} (인)</td>
</tr>
</table>
<div style="display: flex; gap: 10px; margin-bottom: 15px;">
<div style="flex: 1; border: 1px solid #2ecc71; padding: 12px; border-radius: 6px; background-color: {box_good_bg}; min-height: 140px;">
<h5 style="margin: 0 0 8px 0; color: #16a085; font-size:14px; font-weight:bold;">🟢 사업장 우수 안전 항목 (Strengths)</h5>
<p style="font-size: 12.5px; line-height: 1.5; margin:0; color:#111;">{good_text}</p>
</div>
<div style="flex: 1; border: 1px solid #e74c3c; padding: 12px; border-radius: 6px; background-color: {box_bad_bg}; min-height: 140px;">
<h5 style="margin: 0 0 8px 0; color: #c0392b; font-size:14px; font-weight:bold;">🔴 개선 요망 취약 항목 (Weaknesses)</h5>
<p style="font-size: 12.5px; line-height: 1.5; margin:0; color:#111;">{bad_text}</p>
</div>
</div>
<h5 style="margin: 15px 0 5px 0; font-size:14px; font-weight:bold; color:#222;">📌 항목 17. 현장 주요 지적 및 조치 요구사항</h5>
<div style="border: 1px solid {border_color}; min-height: 110px; padding: 12px; font-size: 13px; white-space: pre-wrap; background-color: #fafafa; color:#111; line-height:1.5; border-radius:4px;">
{doc_data['remarks'] if doc_data['remarks'] else '특이사항 없음. 전반적인 안전보건 서류 체계 및 현장 방호 장치 상태가 전사 가이드라인에 부합함.'}
</div>
</div>
"""
            st.markdown(html_report, unsafe_allow_html=True)
            
        with col_rep2:
            st.plotly_chart(fig_radar, use_container_width=True)
            if doc_data['image_path'] and os.path.exists(doc_data['image_path']):
                st.image(doc_data['image_path'], caption="[항목 17. 현장 증적 사진]", use_container_width=True)