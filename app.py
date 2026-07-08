import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
from PIL import Image
import plotly.express as px
import plotly.graph_objects as ob
from supabase import create_client, Client

# -----------------------------------------------------------------------------
# [설정] 페이지 기본 구성 및 Supabase 클라우드 연동
# -----------------------------------------------------------------------------
st.set_page_config(page_title="안전보건 통합 자가진단 (Beta)", page_icon="🦺", layout="wide")

@st.cache_resource
def init_connection():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        st.error("🚨 Supabase 연동 키를 찾을 수 없습니다. secrets.toml을 확인해주세요.")
        return None

supabase = init_connection()

# -----------------------------------------------------------------------------
# [인증] 세션 관리 및 사번 로그인
# -----------------------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_info = None

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center; margin-top:50px;'>🦺 안전보건 통합 점검 시스템 (Beta)</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>부여받은 사번과 PIN 번호로 로그인해 주세요.<br>(※ 테스트용 계정: 사번 admin / PIN 0000 또는 사번 1001 / PIN 0000)</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            emp_id = st.text_input("👤 사번 (ID)", placeholder="예: 1001")
            pin = st.text_input("🔑 PIN 번호", type="password", placeholder="비밀번호 4자리")
            submit = st.form_submit_button("시스템 접속", use_container_width=True)
            
            if submit:
                res = supabase.table("user_master").select("*").eq("emp_id", emp_id).eq("pin", pin).execute()
                if len(res.data) > 0:
                    st.session_state.logged_in = True
                    st.session_state.user_info = res.data[0]
                    st.rerun()
                else:
                    st.error("🚨 사번 또는 PIN 번호가 일치하지 않습니다.")
    st.stop()

# -----------------------------------------------------------------------------
# [도구] AI 자동 요약 가상 함수 (향후 OpenAI 등 연동 포인트)
# -----------------------------------------------------------------------------
def generate_ai_summary(text):
    if not text or len(text) < 5: return "요약 불가(내용 부족)"
    words = text.split()
    return " ".join(words[:5]) + "... (AI 임시 요약)"

# -----------------------------------------------------------------------------
# [기준 데이터] 문항 마스터
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
    1: {"title": "계획서 수립", "options": {"7점": 7, "5점": 5, "-10점": -10}},
    2: {"title": "경영방침 게시", "options": {"3점": 3, "0점": 0}},
    3: {"title": "위험성평가", "options": {"15점": 15, "10점": 10, "0점": 0}},
    4: {"title": "의견청취", "options": {"2점": 2, "0점": 0}},
    5: {"title": "비상훈련", "options": {"7점": 7, "5점": 5, "0점": 0}},
    6: {"title": "관리감독자 선임", "options": {"3점": 3, "1점": 1, "0점": 0}},
    7: {"title": "업무일지", "options": {"7점": 7, "3점": 3, "-5점": -5}},
    8: {"title": "정기교육", "options": {"7점": 7, "0점": 0}},
    9: {"title": "신규자교육", "options": {"3점": 3, "0점": 0}},
    10: {"title": "특별교육", "options": {"3점": 3, "1점": 1, "0점": 0}},
    11: {"title": "MSDS교육", "options": {"5점": 5, "2점": 2, "0점": 0}},
    12: {"title": "위험기계 방호장치", "options": {"7점": 7, "5점": 5, "0점": 0}},
    13: {"title": "이동식 사다리 안전", "options": {"15점": 15, "10점": 10, "0점": 0, "-10점": -10}},
    14: {"title": "MSDS 게시", "options": {"6점": 6, "3점": 3, "1점": 1, "0점": 0}},
    15: {"title": "건강진단", "options": {"7점": 7, "3점": 3, "0점": 0}},
    16: {"title": "보호구 착용", "options": {"3점": 3, "2점": 2, "0점": 0, "-5점": -5}}
}

SECTIONS_MAP = {"서류": [1, 2, 4], "위험성평가": [3], "비상대응": [5], "교육훈련": [6, 7, 8, 9, 10, 11], "현장위험": [12, 13], "보건관리": [14, 15, 16]}

# -----------------------------------------------------------------------------
# [사이드바]
# -----------------------------------------------------------------------------
u_info = st.session_state.user_info
st.sidebar.markdown(f"### 👤 {u_info['emp_name']} 님 환영합니다.")
st.sidebar.caption(f"권한: {'경영진(Admin)' if u_info['role'] == 'admin' else '현장점검자(User)'}")

if st.sidebar.button("🚪 로그아웃", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.markdown("---")
menu_options = ["✍️ 모바일 체크리스트 등록", "🗂️ 내 점검 이력 관리"]
if u_info['role'] == 'admin':
    menu_options.extend(["📊 PC 경영진 종합 대시보드", "🖨️ 1페이지 요약 PDF 출력"])
menu = st.sidebar.radio("메뉴 선택", menu_options)

# -----------------------------------------------------------------------------
# [메뉴 1] 모바일 체크리스트 등록
# -----------------------------------------------------------------------------
if menu == "✍️ 모바일 체크리스트 등록":
    st.title("📋 안전보건 자가진단")
    
    col_date, col_comp, col_br, col_hc = st.columns(4)
    with col_date: inspect_date = st.date_input("점검 일자", datetime.now())
    with col_comp: selected_company = st.selectbox("계약법인", company_list)
    with col_br:
        filtered_branches = sorted(df_ref[df_ref['계약법인'] == selected_company]['사업장명'].unique().tolist()) if not df_ref.empty else ["샘플사업장"]
        branch = st.selectbox("사업장명", filtered_branches)
    with col_hc: headcount = st.number_input("인원수(명)", min_value=0, step=1)
    
    # [CAPA 모니터링] 선택된 사업장의 미조치 지적사항 팝업
    unresolved = supabase.table("safety_issues").select("*").eq("branch", branch).eq("status", "미조치").execute()
    if unresolved.data:
        st.error("🚨 **[주의] 과거 방문 시 미조치된 지적사항이 남아있습니다. 현장에서 개선 여부를 확인해 주세요!**")
        for issue in unresolved.data:
            with st.expander(f"📌 {issue['date']} 지적건: {issue['ai_summary']}"):
                st.write(f"**상세내용:** {issue['issue_text']}")
                if issue.get('image_url'): st.image(issue['image_url'], width=200)
                if st.button(f"✅ 현장 개선 확인 및 조치 완료 처리", key=f"resolve_{issue['id']}"):
                    supabase.table("safety_issues").update({"status": "개선완료"}).eq("id", issue['id']).execute()
                    st.success("개선 완료 처리되었습니다! 새로고침 시 목록에서 사라집니다.")
    
    st.markdown("---")
    tabs = st.tabs(list(SECTIONS_MAP.keys()) + ["📸 현장지적(17)", "📝 테스트 피드백(18)"])
    
    answers = {}
    for idx, (sect, q_ids) in enumerate(SECTIONS_MAP.items()):
        with tabs[idx]:
            for q_id in q_ids:
                q = QUESTIONS[q_id]
                answers[q_id] = st.radio(f"**Q{q_id}. {q['title']}**", list(q["options"].keys()), key=f"ans_{q_id}", horizontal=True)
                st.markdown("---")
                
    with tabs[-2]: # 항목 17 (카메라 강제)
        st.info("🚨 갤러리 사진 업로드는 차단되었습니다. 현장에서 실시간으로 촬영해 주세요.")
        cam_photo = st.camera_input("📸 현장 증적 사진 촬영")
        remarks = st.text_area("지적사항 상세 기록", placeholder="여기에 작성하신 내용은 AI가 자동으로 요약하여 추적 시스템에 등록합니다.")
        
    with tabs[-1]: # 항목 18 (베타 테스트 전용 피드백)
        st.success("💡 [베타 테스트 의견 수렴] 앱 사용 중 불편했던 점이나 추가 요청사항을 자유롭게 적어주세요.")
        beta_feedback = st.text_area("개선 의견 작성", placeholder="예: 카메라 기능이 너무 느려요, 항목 12번 문구가 이해하기 어려워요 등")
            
    if st.button("📋 최종 평가 제출하기", use_container_width=True):
        final_score = sum([QUESTIONS[q_id]["options"][ans] for q_id, ans in answers.items()])
        public_img_url = ""
        
        # 1. 이미지 압축 및 스토리지 업로드
        if cam_photo is not None:
            image = Image.open(cam_photo)
            if image.mode in ("RGBA", "P"): image = image.convert("RGB")
            image.thumbnail((800, 800), Image.Resampling.LANCZOS)
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', optimize=True, quality=70)
            file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{branch}_cam.jpg"
            supabase.storage.from_("safety_images").upload(file_name, img_byte_arr.getvalue(), {"content-type": "image/jpeg"})
            public_img_url = supabase.storage.from_("safety_images").get_public_url(file_name)
        
        # 2. 메인 점검 데이터 DB 인서트
        eval_data = {
            "emp_id": u_info['emp_id'], "date": inspect_date.strftime("%Y-%m-%d"), 
            "company": selected_company, "branch": branch, "headcount": headcount, "inspector": u_info['emp_name'],
            **{f"q{i}": QUESTIONS[i]["options"][answers[i]] for i in range(1, 17)},
            "remarks": remarks, "image_path": public_img_url, "final_score": float(final_score), "feedback": beta_feedback
        }
        supabase.table("safety_evaluation").insert(eval_data).execute()
        
        # 3. 지적사항(CAPA) 추적 테이블 인서트 (지적 내용이 있을 경우에만)
        if remarks:
            ai_sum = generate_ai_summary(remarks)
            issue_data = {
                "emp_id": u_info['emp_id'], "branch": branch, "date": inspect_date.strftime("%Y-%m-%d"),
                "issue_text": remarks, "ai_summary": ai_sum, "image_url": public_img_url, "status": "미조치"
            }
            supabase.table("safety_issues").insert(issue_data).execute()
            
        st.success("🎉 점검 기록 및 지적사항이 성공적으로 서버에 등록되었습니다!")

# -----------------------------------------------------------------------------
# [메뉴 2] 내 점검 이력 관리
# -----------------------------------------------------------------------------
elif menu == "🗂️ 내 점검 이력 관리":
    st.title("🗂️ 나의 누적 점검 이력")
    st.markdown("본인이 등록한 내역만 표시되며, 자유롭게 삭제가 가능합니다.")
    
    res = supabase.table("safety_evaluation").select("*").eq("emp_id", u_info['emp_id']).execute()
    df_my = pd.DataFrame(res.data)
    
    if df_my.empty:
        st.info("아직 등록하신 점검 이력이 없습니다.")
    else:
        df_my = df_my.sort_values(by='date', ascending=False)
        for idx, row in df_my.iterrows():
            with st.expander(f"📍 {row['date']} | {row['branch']} (종합점수: {row['final_score']}점)"):
                st.write(f"**지적사항:** {row['remarks'] if row['remarks'] else '없음'}")
                if st.button(f"🗑️ 이 점검기록 영구 삭제", key=f"del_{row['id']}"):
                    supabase.table("safety_evaluation").delete().eq("id", row['id']).execute()
                    st.success("삭제 완료! 다른 메뉴로 이동했다 돌아오면 목록에서 사라집니다.")

# -----------------------------------------------------------------------------
# [메뉴 3] PC 경영진 대시보드
# -----------------------------------------------------------------------------
elif menu == "📊 PC 경영진 종합 대시보드":
    st.title("📊 경영진 종합 대시보드")
    
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    df_issues = pd.DataFrame(supabase.table("safety_issues").select("*").execute().data)
    
    if df.empty:
        st.warning("분석할 데이터가 없습니다.")
    else:
        tab_kpi, tab_capa, tab_feedback = st.tabs(["🏆 스탭 성과평가(KPI)", "🚨 지적사항(CAPA) 추적 현황", "📝 베타 피드백(VoC)"])
        
        with tab_kpi:
            st.markdown("### 🎯 담당자별 방문 성실도 및 현장 위험 제거율")
            kpi_data = []
            for e_id, group in df.groupby('emp_id'):
                total_visits = len(group)
                risk_score_sum = group['q3'].sum() + group['q12'].sum() + group['q13'].sum() + group['q15'].sum()
                removal_rate = round((risk_score_sum / (total_visits * 44)) * 100, 1) if total_visits > 0 else 0
                kpi_data.append({"사번": e_id, "담당자": group['inspector'].iloc[0], "방문횟수": total_visits, "사업장수": group['branch'].nunique(), "위험제거율(%)": max(0, min(removal_rate, 100))})
                
            kpi_df = pd.DataFrame(kpi_data).sort_values(by="위험제거율(%)", ascending=False).reset_index(drop=True)
            st.dataframe(kpi_df.style.background_gradient(cmap="Blues", subset=["위험제거율(%)"]), use_container_width=True)
            
        with tab_capa:
            st.markdown("### 🔍 전사 사업장 미조치 현황판")
            if not df_issues.empty:
                col1, col2 = st.columns(2)
                col1.metric("🔴 현재 미조치 건수", len(df_issues[df_issues['status'] == '미조치']))
                col2.metric("🟢 누적 개선완료 건수", len(df_issues[df_issues['status'] == '개선완료']))
                st.dataframe(df_issues[['date', 'branch', 'ai_summary', 'status', 'inspector']].sort_values(by='status', ascending=False), use_container_width=True)
            else:
                st.info("등록된 지적사항이 없습니다.")
                
        with tab_feedback:
            st.markdown("### 💡 실무자 베타 테스트 피드백")
            df_fb = df[df['feedback'].notna() & (df['feedback'] != "")]
            if not df_fb.empty:
                st.dataframe(df_fb[['date', 'inspector', 'branch', 'feedback']], use_container_width=True)
            else:
                st.info("수집된 피드백이 없습니다.")

# -----------------------------------------------------------------------------
# [메뉴 4] 1페이지 요약 PDF 출력
# -----------------------------------------------------------------------------
elif menu == "🖨️ 1페이지 요약 PDF 출력":
    st.title("🖨️ 점검결과서 (PDF용)")
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    if df.empty:
        st.warning("출력할 데이터가 없습니다.")
    else:
        df['select_label'] = df['date'] + " | " + df['branch'] + " | " + df['inspector']
        doc = df[df['select_label'] == st.selectbox("출력 대상 선택", df['select_label'].unique())].iloc[0]
        
        html_report = f"""
        <div style="border: 2px solid #333; padding: 20px; font-family: sans-serif; background-color:#fff; color:#111; border-radius: 8px;">
        <h2 style="text-align: center; margin-bottom: 20px;">안전보건 점검 결과서</h2>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; border: 1px solid #333;">
        <tr style="background-color: #f2f2f2;"><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">사업장명</td><td style="border: 1px solid #333; padding: 8px;">{doc['branch']}</td><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">점검자</td><td style="border: 1px solid #333; padding: 8px;">{doc['inspector']}</td></tr>
        <tr style="background-color: #f2f2f2;"><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">점검일자</td><td style="border: 1px solid #333; padding: 8px;">{doc['date']}</td><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">종합점수</td><td style="border: 1px solid #333; padding: 8px; color:#c0392b; font-weight:bold;">{int(doc['final_score'])} 점</td></tr>
        </table>
        <h5 style="margin: 15px 0 5px 0;">📌 현장 지적사항 및 조치 (AI 요약)</h5>
        <div style="border: 1px solid #333; padding: 12px; font-size: 13px; white-space: pre-wrap; background-color: #fafafa;">원본: {doc['remarks'] if doc['remarks'] else '특이사항 없음.'}</div>
        </div>
        """
        col1, col2 = st.columns([1.5, 1])
        with col1: st.markdown(html_report, unsafe_allow_html=True)
        with col2: 
            if doc.get('image_path') and doc['image_path'].startswith("http"):
                st.image(doc['image_path'], caption="현장 증적 사진", use_container_width=True)