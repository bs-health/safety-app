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
# [인증] 세션 관리 및 사번 로그인 (방안 B)
# -----------------------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_info = None

if 'issue_count' not in st.session_state:
    st.session_state.issue_count = 1

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
# [도구] AI 자동 요약 가상 함수
# -----------------------------------------------------------------------------
def generate_ai_summary(text):
    if not text or len(text) < 5: return "요약 불가(내용 부족)"
    words = text.split()
    return " ".join(words[:5]) + "... (AI 자동 요약)"

# -----------------------------------------------------------------------------
# [기준 데이터] 전체 문항 마스터
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
    1: {"title": "년도별 안전보건관리계획서 수립여부", "options": {"7점. 당해년도 안전보건관리계획서가 작성되어있고 내용이 충실함": 7, "5점. 안전보건관리계획서가 작성되었으나 정보 최신화 미흡 및 샘플 사용": 5, "-10점. 미작성": -10}, "tip": "년도별 안전보건관리계획서 수립 여부 확인 (본사 지침 및 필수사항)"},
    2: {"title": "안전보건 경영방침 및 목표", "options": {"3점. 경영방침 및 당해년도 목표를 사무실, 휴게실 등 게시": 3, "0점. 미 게시": 0}, "tip": "사무실, 휴게실 게시 상태 확인"},
    3: {"title": "위험성평가", "options": {"15점. 위험성 평가 실시 중": 15, "10점. 위험성 평가가 실시 되었으나 결재본이 없음": 10, "0점. 위험성 평가를 미실시하였거나 원본이 없음": 0}, "tip": "최신자료 원본 및 본사 결재본(갑지) 보유 확인, 신규사업장은 최초 실시 여부 확인"},
    4: {"title": "종사자의 의견청취", "options": {"2점. 홍보자료가 게시판에 부착되어 있거나 자체 의견청취함 설치됨": 2, "0점. 미부착": 0}, "tip": "안전보건팀 카카오톡 홍보채널 게시 또는 사업장 자체 의견청취함 설치 여부"},
    5: {"title": "비상대응 훈련 실시", "options": {"7점. 공종별 비상대응훈련을 실시하였음": 7, "5점. 소방훈련으로 갈음하고 있음, 신규사업장으로 미실시": 5, "0점. 최근 1년이내 훈련 미실시": 0}, "tip": "최신자료 원본 및 본사 결재본(갑지) 보유 확인 (1년 이내 훈련 자료 필수)"},
    6: {"title": "관리감독자 지정 및 교육", "options": {"3점. 법에 맞게 선임되어 있고 지정서 및 교육수료증을 보관하고 있음": 3, "1점. 선임되어 있으나 교육수료증 등 미보유": 1, "0점. 미선임, 야간관리감독자 미선임 등": 0}, "tip": "안전보건관계자 선임 및 교육수료증 보관 여부 확인"},
    7: {"title": "관리감독자 업무일지", "options": {"7점. 선임된 모든 자가 출근일 기준 매일 작성 중이며 결재까지 완료됨": 7, "3점. 작성 내용이 형식적(전부 양호 표시)이며 매일 작성되지 않음": 3, "-5점. 미작성": -5}, "tip": "관리감독자 별도 업무일지 작성 및 결재 여부 확인"},
    8: {"title": "정기안전보건교육 수행 여부", "options": {"7점. 근로자별 교육시간 충족됨": 7, "0점. 근로자별 교육시간 충족 확인이 어려움": 0}, "tip": "모든 근로자가 반기 12시간 정기안전보건교육을 이수했는지 확인"},
    9: {"title": "신규입사자안전보건교육 수행 여부", "options": {"3점. 최근 1년이내 발생된 신규입사자에 대한 안전보건교육이 완료되었음": 3, "0점. 누락되었거나 실시하고 있지 않음": 0}, "tip": "최근 1년 이내 신규입사자 발생 시 입사당일 8시간 이수 및 서명지 확인"},
    10: {"title": "특별안전보건교육 수행 여부", "options": {"3점. 시설 근로자 특별안전보건교육 실시됨": 3, "1점. 해당없음 (미화, 보안 등)": 1, "0점. 미실시": 0}, "tip": "시설직 근로자 대상 밀폐, 용접, 전기 취급 특별안전보건교육 각 8시간 확인"},
    11: {"title": "MSDS교육 수행 여부", "options": {"5점. 시설 근로자 특별안전보건교육 실시됨": 5, "2점. 해당없음 (보안 등)": 2, "0점. 미실시": 0}, "tip": "MSDS 대상물질 취급 시 년 1회 교육 실시 여부 확인"},
    12: {"title": "사업장 위험요소 확인", "options": {"7점. 각각의 기계기구에 방호장치가 전체 부착되어 있음": 7, "5점. 보안 단독 사업장 등 해당사항 없음": 5, "0점. 방호장치가 임의 해제되어 있음": 0}, "tip": "그라인더, 고속절단기, 예초기, 용접기 등 방호장치 부착 확인"},
    13: {"title": "이동식 사다리의 안전조치", "options": {"15점. 안전인증사다리를 사용하고 보호구 착용 및 전도방지조치가 완료된 상태임": 15, "10점. 사다리 사용하지 않음": 10, "0점. 아웃트리거가 없는 경량 사다리를 사용함": 0, "-10점. 안전조치를 이행하고 있지 않음": -10}, "tip": "1m 이상 사다리 전도방지장치 설치, 2인 1조 작업, 안전모 턱끈 착용 여부"},
    14: {"title": "MSDS최신화 및 게시", "options": {"6점. MSDS가 최신화 되어있고, 소분용기 경고표지 부착상태가 양호함": 6, "3점. MSDS가 최신화 되어있으나, 소분용기 경고표지 부착미흡": 3, "1점. MSDS가 최신화 되어있지않으나, 소분용기 경고표지는 부착되어있음": 1, "0점. MSDS 미확보됨": 0}, "tip": "제출번호가 기재된 MSDS 보유 및 소분용기 경고표지 부착 상태 확인"},
    15: {"title": "근로자 건강진단(일반, 특수)", "options": {"7점. 근로자의 일반검진, 특수건강진단의 이력을 관리 중이고 결과표를 취합 중임": 7, "3점. 근로자의 일반검진, 특수건강진단의 이력을 관리중임": 3, "0점. 특수건강진단을 실시하고있으나 이력확인이 안됨": 0}, "tip": "근로자의 건강진단 이력관리 및 결과표 취합 현황 확인"},
    16: {"title": "보호구 지급 및 착용", "options": {"3점. KCs인증 보호구를 사용 중이며 보호구 지급대장이 작성됨": 3, "2점. 보호구를 지급중이나 보호구 지급대장이 미작성": 2, "0점. 보호구를 착용하지 않음": 0, "-5점. 보호구를 지급하지 않음": -5}, "tip": "KCs인증 보호구 사용 및 지급대장 작성, 현장소장 안전화 착용 확인"}
}

SECTIONS_MAP = {"서류": [1, 2, 4], "위험성평가": [3], "비상대응": [5], "교육훈련": [6, 7, 8, 9, 10, 11], "현장위험": [12, 13], "보건관리": [14, 15, 16]}

# -----------------------------------------------------------------------------
# [사이드바] 네비게이션 제어 (권한별 메뉴 완벽 분리)
# -----------------------------------------------------------------------------
u_info = st.session_state.user_info
st.sidebar.markdown(f"### 👤 {u_info['emp_name']} 님 환영합니다.")
st.sidebar.caption(f"권한: {'경영진(Admin)' if u_info['role'] == 'admin' else '현장점검자(User)'}")

if st.sidebar.button("🚪 로그아웃", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.markdown("---")

# 관리자는 대시보드만, 일반 스탭은 실무 메뉴만 보이도록 분리
if u_info['role'] == 'admin':
    menu_options = ["📊 PC 경영진 종합 대시보드"]
else:
    menu_options = ["✍️ 모바일 체크리스트 등록", "🗂️ 내 점검 이력 관리", "🖨️ 1페이지 요약 PDF 출력"]

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
                st.markdown(f"**Q{q_id:02d}. {q['title']}**")
                st.caption(f"💡 팁: {q['tip']}")
                
                try:
                    if os.path.exists(f"images/{q_id}.png"): 
                        st.image(f"images/{q_id}.png", width=280)
                except: pass
                
                answers[q_id] = st.radio("배점 항목 선택", list(q["options"].keys()), key=f"ans_{q_id}")
                st.markdown("---")
                
    with tabs[-2]:
        st.info("🚨 갤러리 사진 업로드는 차단되었습니다. 현장에서 실시간으로 촬영해 주세요.")
        
        issues_data = []
        for i in range(st.session_state.issue_count):
            st.markdown(f"#### 📌 [{i+1}번째 지적사항]")
            cam_photo = st.camera_input(f"📸 {i+1}번 현장 지적 사진 촬영", key=f"cam_{i}")
            remarks = st.text_area(f"{i+1}번 지적사항 상세 기록", key=f"rem_{i}", placeholder="여기에 작성하신 내용은 AI가 자동으로 요약하여 추적 시스템에 등록합니다.")
            issues_data.append((cam_photo, remarks))
            st.markdown("---")
            
        if st.button("➕ 지적사항 한 건 더 추가하기", use_container_width=True):
            st.session_state.issue_count += 1
            st.rerun()
        
    with tabs[-1]:
        st.success("💡 [베타 테스트 의견 수렴] 앱 사용 중 불편했던 점이나 추가 요청사항을 자유롭게 적어주세요.")
        beta_feedback = st.text_area("개선 의견 작성", placeholder="예: 카메라 기능이 너무 느려요, 항목 12번 문구가 이해하기 어려워요 등")
            
    if st.button("📋 최종 평가 제출하기", use_container_width=True):
        final_score = sum([QUESTIONS[q_id]["options"][ans] for q_id, ans in answers.items()])
        
        combined_remarks = "\n".join([f"[{i+1}] {rem}" for i, (cam, rem) in enumerate(issues_data) if rem])
        first_img_url = ""
        
        for i, (cam, rem) in enumerate(issues_data):
            if cam or rem:
                img_url = ""
                if cam:
                    image = Image.open(cam)
                    if image.mode in ("RGBA", "P"): image = image.convert("RGB")
                    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG', optimize=True, quality=70)
                    file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{branch}_issue{i}.jpg"
                    supabase.storage.from_("safety_images").upload(file_name, img_byte_arr.getvalue(), {"content-type": "image/jpeg"})
                    img_url = supabase.storage.from_("safety_images").get_public_url(file_name)
                    
                    if not first_img_url: 
                        first_img_url = img_url
                
                ai_sum = generate_ai_summary(rem) if rem else "사진만 등록됨"
                issue_data = {
                    "emp_id": u_info['emp_id'], "branch": branch, "date": inspect_date.strftime("%Y-%m-%d"),
                    "issue_text": rem, "ai_summary": ai_sum, "image_url": img_url, "status": "미조치", "inspector": u_info['emp_name']
                }
                supabase.table("safety_issues").insert(issue_data).execute()

        eval_data = {
            "emp_id": u_info['emp_id'], "date": inspect_date.strftime("%Y-%m-%d"), 
            "company": selected_company, "branch": branch, "headcount": headcount, "inspector": u_info['emp_name'],
            **{f"q{i}": QUESTIONS[i]["options"][answers[i]] for i in range(1, 17)},
            "remarks": combined_remarks, "image_path": first_img_url, "final_score": float(final_score), "feedback": beta_feedback
        }
        supabase.table("safety_evaluation").insert(eval_data).execute()
        
        st.session_state.issue_count = 1
        st.success("🎉 점검 기록 및 지적사항이 성공적으로 서버에 등록되었습니다!")

# -----------------------------------------------------------------------------
# [메뉴 2] 내 점검 이력 관리
# -----------------------------------------------------------------------------
elif menu == "🗂️ 내 점검 이력 관리":
    st.title("🗂️ 나의 누적 점검 이력")
    st.markdown("본인이 등록한 내역만 표시되며, 기한 제한 없이 자유롭게 수정 및 삭제가 가능합니다.")
    
    res = supabase.table("safety_evaluation").select("*").eq("emp_id", u_info['emp_id']).execute()
    df_my = pd.DataFrame(res.data)
    
    if df_my.empty:
        st.info("아직 등록하신 점검 이력이 없습니다.")
    else:
        df_my = df_my.sort_values(by='date', ascending=False)
        for idx, row in df_my.iterrows():
            with st.expander(f"📍 {row['date']} | {row['branch']} (종합점수: {row['final_score']}점)"):
                st.write(f"**지적사항 종합:**\n{row['remarks'] if row['remarks'] else '없음'}")
                if st.button(f"🗑️ 이 점검기록 영구 삭제", key=f"del_{row['id']}"):
                    supabase.table("safety_evaluation").delete().eq("id", row['id']).execute()
                    st.success("삭제 완료! 새로고침 시 리스트에서 사라집니다.")

# -----------------------------------------------------------------------------
# [메뉴 3] PC 경영진 종합 대시보드
# -----------------------------------------------------------------------------
elif menu == "📊 PC 경영진 종합 대시보드":
    st.title("📊 경영진 종합 대시보드 (PC 보고용)")
    
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    df_issues = pd.DataFrame(supabase.table("safety_issues").select("*").execute().data)
    
    if df.empty:
        st.warning("분석할 클라우드 데이터가 없습니다.")
    else:
        tab_main, tab_kpi, tab_capa, tab_feedback = st.tabs([
            "🌐 전사 종합 모니터링", "🏆 스탭 성과평가(KPI)", "🚨 지적사항(CAPA) 추적 현황", "📝 베타 피드백(VoC)"
        ])
        
        with tab_main:
            total_avg = round(df['final_score'].mean(), 1)
            above_avg_df = df[df['final_score'] >= total_avg]
            below_avg_df = df[df['final_score'] < total_avg]
            
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("📈 전사 평균 점수", f"{total_avg} 점")
            kpi2.markdown(f"<div style='background-color:#e8f8f5; padding:12px; border-radius:6px; border-left:6px solid #2ecc71;'><p style='margin:0; color:#16a085;'><b>🟢 평균 이상 (우수)</b></p><h2 style='margin:5px 0; color:#111;'>{len(above_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
            kpi3.markdown(f"<div style='background-color:#fdedec; padding:12px; border-radius:6px; border-left:6px solid #e74c3c;'><p style='margin:0; color:#c0392b;'><b>🔴 평균 미달 (취약)</b></p><h2 style='margin:5px 0; color:#111;'>{len(below_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
            st.markdown("---")
            
            st.markdown("### 🔍 차수별 안전 흐름 추이 분석기")
            if st.checkbox("📈 사업장 방문 차수별 안전 흐름 추이 분석기 켜기", value=False):
                unique_branches = sorted(df['branch'].unique().tolist())
                target_branch = st.selectbox("분석할 사업장 선택", unique_branches)
                
                전사평균_df = df.groupby('date')['final_score'].mean().reset_index().rename(columns={'final_score': '전사평균'})
                지정사업장_df = df[df['branch'] == target_branch].sort_values(by='date')
                compare_df = pd.merge(지정사업장_df, 전사평균_df, on='date', how='left')
                
                fig_trend = ob.Figure()
                fig_trend.add_trace(ob.Scatter(x=compare_df['date'], y=compare_df['final_score'], name=f"{target_branch} 점수", mode='lines+markers', line=dict(color='#2ecc71', width=3)))
                fig_trend.add_trace(ob.Scatter(x=compare_df['date'], y=compare_df['전사평균'], name="전사 평균", mode='lines', line=dict(color='#e74c3c', width=2, dash='dash')))
                fig_trend.update_layout(title=f"[{target_branch}] vs 전사 평균 추이 비교", template="plotly_white", yaxis=dict(range=[-15, 105]))
                st.plotly_chart(fig_trend, use_container_width=True)
                st.markdown("---")
                
            st.markdown("### 🏆 전사 평가 순위")
            rank_df = df.sort_values(by="final_score", ascending=False)[['date', 'company', 'branch', 'final_score', 'inspector']]
            st.dataframe(rank_df, use_container_width=True)
            st.markdown("---")
            
            st.markdown("### 🚨 리스크 진단: 전사 항목별 안전 규칙 준수율")
            q_cols = [f'q{i}' for i in range(1, 17)]
            q_avg = df[q_cols].mean()
            q_perf = {QUESTIONS[int(col[1:])]["title"]: round((q_avg[col] / max(QUESTIONS[int(col[1:])]["options"].values())) * 100, 1) for col in q_cols}
            perf_df = pd.DataFrame(list(q_perf.items()), columns=['항목', '준수율(%)']).sort_values(by='준수율(%)')
            
            fig_large = px.bar(perf_df, x='준수율(%)', y='항목', orientation='h', color='준수율(%)', color_continuous_scale=['#c0392b', '#e74c3c', '#f39c12', '#2ecc71', '#1abc9c'], range_color=[0, 100], height=500)
            st.plotly_chart(fig_large, use_container_width=True)
            
            alert_cols = st.columns(3)
            for idx, (_, row) in enumerate(perf_df.head(3).iterrows()):
                alert_cols[idx].error(f"**취약 {idx+1}위 : {row['항목']}** (준수율 **{row['준수율(%)']}%**)")

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
            
            fig_kpi = px.bar(kpi_df, x="담당자", y="위험제거율(%)", color="방문횟수", title="담당자별 성과 지표", height=400)
            st.plotly_chart(fig_kpi, use_container_width=True)
            
        with tab_capa:
            st.markdown("### 🔍 전사 사업장 미조치 현황판")
            if not df_issues.empty:
                col1, col2 = st.columns(2)
                col1.metric("🔴 현재 전사 미조치 건수", len(df_issues[df_issues['status'] == '미조치']))
                col2.metric("🟢 누적 개선완료 건수", len(df_issues[df_issues['status'] == '개선완료']))
                st.dataframe(df_issues[['date', 'branch', 'ai_summary', 'status', 'inspector']].sort_values(by='status', ascending=False), use_container_width=True)
            else:
                st.info("등록된 지적사항이 없습니다.")
                
        with tab_feedback:
            st.markdown("### 💡 실무자 베타 테스트 피드백 (VoC)")
            if 'feedback' in df.columns:
                df_fb = df[df['feedback'].notna() & (df['feedback'] != "")]
                if not df_fb.empty:
                    st.dataframe(df_fb[['date', 'inspector', 'branch', 'feedback']], use_container_width=True)
                else:
                    st.info("수집된 피드백이 없습니다.")
            else:
                st.info("피드백 데이터가 존재하지 않습니다.")

# -----------------------------------------------------------------------------
# [메뉴 4] 1페이지 요약 및 PDF 출력
# -----------------------------------------------------------------------------
elif menu == "🖨️ 1페이지 요약 PDF 출력":
    st.title("🖨️ 안전점검결과 보고서 요약본")
    
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    if df.empty:
        st.warning("출력할 데이터가 없습니다.")
    else:
        df['select_label'] = df['date'] + " | " + df['company'] + " | " + df['branch']
        doc_data = df[df['select_label'] == st.selectbox("출력 대상 보고서 선택", df['select_label'].unique())].iloc[0]
        st.markdown("---")
        
        good_items, bad_items = [], []
        for q_id, q_info in QUESTIONS.items():
            u_score = doc_data[f'q{q_id}']
            m_score = max(q_info["options"].values())
            g_avg = df[f'q{q_id}'].mean()
            if u_score == m_score: good_items.append(f"✔️ {q_info['title']} ({u_score}점 만점)")
            if u_score < 0 or u_score < g_avg: bad_items.append(f"❌ {q_info['title']} ({'감점' if u_score < 0 else f'본 사업장 {u_score}점 vs 전사 {round(g_avg,1)}점'})")
                
        s_scores, s_avgs, s_names = [], [], list(SECTIONS_MAP.keys())
        for s_name, q_ids in SECTIONS_MAP.items():
            s_max = sum([max(QUESTIONS[qid]["options"].values()) for qid in q_ids])
            s_scores.append(round((sum([doc_data[f'q{qid}'] for qid in q_ids]) / s_max) * 100, 1) if s_max else 0)
            s_avgs.append(round((sum([df[f'q{qid}'].mean() for qid in q_ids]) / s_max) * 100, 1) if s_max else 0)
            
        fig_radar = ob.Figure()
        fig_radar.add_trace(ob.Scatterpolar(r=s_scores, theta=s_names, fill='toself', name='해당 사업장'))
        fig_radar.add_trace(ob.Scatterpolar(r=s_avgs, theta=s_names, fill='toself', name='전사 평균'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), template="plotly_white", height=380, margin=dict(l=40, r=40, t=40, b=40))
        
        col_rep1, col_rep2 = st.columns([1.5, 1])
        with col_rep1:
            html_report = f"""
<div style="border: 2px solid #333; padding: 20px; font-family: sans-serif; background-color:#fff; color:#111; border-radius: 8px;">
<h2 style="text-align: center; margin-bottom: 20px; text-decoration: underline; letter-spacing:3px;">안전보건 점검 결과서</h2>
<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; border: 1px solid #333;">
<tr style="background-color: #f2f2f2;"><td style="border: 1px solid #333; padding: 8px; font-weight: bold; width: 20%;">점검일자</td><td style="border: 1px solid #333; padding: 8px; background-color:#fff;">{doc_data['date']}</td><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">종합점수</td><td style="border: 1px solid #333; padding: 8px; color: #c0392b; font-weight: bold; background-color:#fff;">{int(doc_data['final_score'])} 점 / 100점</td></tr>
<tr style="background-color: #f2f2f2;"><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">계약법인</td><td style="border: 1px solid #333; padding: 8px; background-color:#fff;">{doc_data['company']}</td><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">사업장명</td><td style="border: 1px solid #333; padding: 8px; font-weight:bold; background-color:#fff;">{doc_data['branch']}</td></tr>
<tr style="background-color: #f2f2f2;"><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">계약인원</td><td style="border: 1px solid #333; padding: 8px; background-color:#fff;">{doc_data['headcount']} 명</td><td style="border: 1px solid #333; padding: 8px; font-weight: bold;">점검자</td><td style="border: 1px solid #333; padding: 8px; background-color:#fff;">{doc_data['inspector']} (인)</td></tr>
</table>
<div style="display: flex; gap: 10px; margin-bottom: 15px;">
<div style="flex: 1; border: 1px solid #2ecc71; padding: 12px; border-radius: 6px; background-color: #e8f8f5; min-height: 140px;">
<h5 style="margin: 0 0 8px 0; color: #16a085; font-size:14px; font-weight:bold;">🟢 우수 안전 항목 (Strengths)</h5><p style="font-size: 12.5px; line-height: 1.5; margin:0;">{"<br>".join(good_items) if good_items else "특출난 강점 없음"}</p></div>
<div style="flex: 1; border: 1px solid #e74c3c; padding: 12px; border-radius: 6px; background-color: #fdedec; min-height: 140px;">
<h5 style="margin: 0 0 8px 0; color: #c0392b; font-size:14px; font-weight:bold;">🔴 취약 항목 (Weaknesses)</h5><p style="font-size: 12.5px; line-height: 1.5; margin:0;">{"<br>".join(bad_items) if bad_items else "취약점 없음"}</p></div>
</div>
<h5 style="margin: 15px 0 5px 0; font-size:14px; font-weight:bold;">📌 현장 지적사항 종합 기록</h5>
<div style="border: 1px solid #333; padding: 12px; font-size: 13px; white-space: pre-wrap; background-color: #fafafa; line-height:1.5; border-radius:4px;">{doc_data['remarks'] if doc_data['remarks'] else '특이사항 없음.'}</div>
</div>
"""
            st.markdown(html_report, unsafe_allow_html=True)
            
        with col_rep2:
            st.plotly_chart(fig_radar, use_container_width=True)
            if doc_data.get('image_path') and doc_data['image_path'].startswith("http"):
                st.image(doc_data['image_path'], caption="대표 현장 지적 사진", use_container_width=True)