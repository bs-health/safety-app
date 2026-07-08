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
# [설정] 페이지 기본 구성, 반응형 CSS 주입 및 Supabase 연동
# -----------------------------------------------------------------------------
st.set_page_config(page_title="안전보건 통합 자가진단 (Beta)", page_icon="🦺", layout="wide")

# [요청 3 해결] 모바일 줄바꿈 방지 및 반응형 폰트 CSS 주입
st.markdown("""
<style>
    h1, h2, h3 {
        word-break: keep-all !important;
        white-space: nowrap !important;
    }
    @media (max-width: 768px) {
        h1 { font-size: 1.6rem !important; }
        h2 { font-size: 1.3rem !important; }
        h3 { font-size: 1.1rem !important; }
        /* 탭 폰트 크기 모바일 최적화 */
        button[data-baseweb="tab"] { font-size: 0.85rem !important; }
    }
</style>
""", unsafe_allow_html=True)

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

if 'issue_count' not in st.session_state:
    st.session_state.issue_count = 1

if not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center; margin-top:50px;'>🦺 안전보건 통합 점검 시스템</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>부여받은 사번과 PIN 번호로 로그인해 주세요.</p>", unsafe_allow_html=True)
    
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
# [도구] AI 요약 함수 및 DB 데이터
# -----------------------------------------------------------------------------
def generate_ai_summary(text):
    if not text or len(text) < 5: return "요약 불가(내용 부족)"
    return " ".join(text.split()[:5]) + "... (AI 자동 요약)"

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
# [사이드바] 권한 분리
# -----------------------------------------------------------------------------
u_info = st.session_state.user_info
st.sidebar.markdown(f"### 👤 {u_info['emp_name']} 님 환영합니다.")
st.sidebar.caption(f"권한: {'경영진(Admin)' if u_info['role'] == 'admin' else '현장점검자(User)'}")

if st.sidebar.button("🚪 로그아웃", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()
st.sidebar.markdown("---")

if u_info['role'] == 'admin':
    menu_options = ["📊 PC 경영진 종합 대시보드"]
else:
    menu_options = ["✍️ 모바일 체크리스트 등록", "🗂️ 내 점검 이력 관리", "📈 현장 담당자 점검현황(종합)", "🖨️ 1페이지 요약 PDF 출력"]
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
        st.error("🚨 **[주의] 과거 방문 시 미조치된 지적사항이 남아있습니다. 현장 확인 바랍니다!**")
        for issue in unresolved.data:
            with st.expander(f"📌 {issue['date']} 지적건: {issue['ai_summary']}"):
                st.write(f"**상세내용:** {issue['issue_text']}")
                if issue.get('image_url'): st.image(issue['image_url'], width=200)
                if st.button(f"✅ 현장 개선 확인 및 조치 완료 처리", key=f"resolve_{issue['id']}"):
                    supabase.table("safety_issues").update({"status": "개선완료"}).eq("id", issue['id']).execute()
                    st.success("개선 완료 처리되었습니다!")
    st.markdown("---")
    
    # [요청 1 설계] 18번 피드백을 17번(제출 탭)으로 통합하여 총 7개 탭 구성
    tabs_names = list(SECTIONS_MAP.keys()) + ["📸 최종 지적 및 제출(17)"]
    tabs = st.tabs(tabs_names)
    
    answers = {}
    item_issues_widgets = {} # 각 문항별 지적사항 위젯 데이터 저장용
    
    for idx, (sect, q_ids) in enumerate(SECTIONS_MAP.items()):
        with tabs[idx]:
            for q_id in q_ids:
                q = QUESTIONS[q_id]
                st.markdown(f"**Q{q_id:02d}. {q['title']}**")
                st.caption(f"💡 팁: {q['tip']}")
                try:
                    if os.path.exists(f"images/{q_id}.png"): st.image(f"images/{q_id}.png", width=280)
                except: pass
                
                answers[q_id] = st.radio("배점 항목 선택", list(q["options"].keys()), key=f"ans_{q_id}")
                
                # [요청 2 설계] 문항별 개별 지적사항 촬영 기능 추가
                issue_check = st.checkbox(f"⚠️ 이 항목(Q{q_id})에서 지적사항 발생 시 체크", key=f"chk_{q_id}")
                if issue_check:
                    st.warning(f"**Q{q_id:02d} 관련 위반 사항을 기록합니다.**")
                    cam = st.camera_input(f"📸 Q{q_id:02d} 현장 사진", key=f"cam_q_{q_id}")
                    rem = st.text_area(f"Q{q_id:02d} 지적 상세 내용", placeholder="위반 현황 및 조치 요구사항을 입력하세요.", key=f"rem_q_{q_id}")
                    item_issues_widgets[q_id] = (cam, rem)
                    
                st.markdown("---")
                
            # [요청 1 설계] 앞선 6개 시트에는 JS 강제 스와이프를 지원하는 '다음' 버튼 부착
            st.components.v1.html(f"""
            <script>
            function nextTab() {{
                const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"], button[role="tab"]');
                if (tabs.length > {idx} + 1) {{ tabs[{idx} + 1].click(); }}
            }}
            </script>
            <button onclick="nextTab()" style="width:100%; padding:12px; background-color:#ff4b4b; color:white; border:none; border-radius:8px; font-weight:bold; font-size:16px; cursor:pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                다음 시트로 넘어가기 ➡️
            </button>
            """, height=60)
            
    # [요청 1 설계] 제출 버튼은 오직 마지막 7번째 탭에만 존재함
    with tabs[-1]:
        st.info("🚨 위 문항(1~16번) 외에, **기타 추가적인 현장 지적사항**이 있다면 아래에 등록해주세요.")
        generic_issues_widgets = []
        for i in range(st.session_state.issue_count):
            st.markdown(f"#### 📌 [추가 현장 지적 {i+1}]")
            cam = st.camera_input(f"📸 추가 현장 사진 {i+1}", key=f"gen_cam_{i}")
            rem = st.text_area(f"추가 지적사항 {i+1} 상세 내용", key=f"gen_rem_{i}")
            generic_issues_widgets.append((cam, rem))
            st.markdown("---")
            
        if st.button("➕ 지적사항 한 건 더 추가하기", use_container_width=True):
            st.session_state.issue_count += 1
            st.rerun()
            
        st.markdown("### 📝 최종 피드백")
        beta_feedback = st.text_area("앱 사용 중 불편했던 점이나 개선 의견을 자유롭게 적어주세요.", key="beta_feed")
        st.markdown("---")
        
        # 제출 버튼
        if st.button("📋 최종 평가 제출하기", use_container_width=True, type="primary"):
            final_score = sum([QUESTIONS[q_id]["options"][ans] for q_id, ans in answers.items()])
            all_issues = []
            
            # 1. 항목별 지적사항 병합 (요청 2 연동)
            for q_id, (cam, rem) in item_issues_widgets.items():
                if cam or rem:
                    ans_val = answers[q_id].split('.')[0]
                    q_title = QUESTIONS[q_id]['title']
                    issue_text = f"[Q{q_id:02d} 지적] {q_title}\n- 선택내역: {ans_val}\n- 상세설명: {rem if rem else '사진만 등록됨'}"
                    all_issues.append((cam, issue_text))
                    
            # 2. 일반 지적사항 병합
            for i, (cam, rem) in enumerate(generic_issues_widgets):
                if cam or rem:
                    issue_text = f"[항목 외 추가 지적 {i+1}] {rem if rem else '사진만 등록됨'}"
                    all_issues.append((cam, issue_text))
                    
            combined_remarks = "\n\n".join([text for _, text in all_issues])
            first_img_url = ""
            
            # 클라우드 이미지 업로드 및 개별 지적사항(CAPA) DB 인서트
            for i, (cam, text) in enumerate(all_issues):
                img_url = ""
                if cam:
                    image = Image.open(cam)
                    if image.mode in ("RGBA", "P"): image = image.convert("RGB")
                    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG', optimize=True, quality=70)
                    file_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{branch}_issue_{i}.jpg"
                    supabase.storage.from_("safety_images").upload(file_name, img_byte_arr.getvalue(), {"content-type": "image/jpeg"})
                    img_url = supabase.storage.from_("safety_images").get_public_url(file_name)
                    if not first_img_url: first_img_url = img_url
                
                ai_sum = generate_ai_summary(text)
                issue_data = {
                    "emp_id": u_info['emp_id'], "branch": branch, "date": inspect_date.strftime("%Y-%m-%d"),
                    "issue_text": text, "ai_summary": ai_sum, "image_url": img_url, "status": "미조치", "inspector": u_info['emp_name']
                }
                supabase.table("safety_issues").insert(issue_data).execute()

            # 메인 종합 점검표 DB 인서트
            eval_data = {
                "emp_id": u_info['emp_id'], "date": inspect_date.strftime("%Y-%m-%d"), 
                "company": selected_company, "branch": branch, "headcount": headcount, "inspector": u_info['emp_name'],
                **{f"q{i}": QUESTIONS[i]["options"][answers[i]] for i in range(1, 17)},
                "remarks": combined_remarks, "image_path": first_img_url, "final_score": float(final_score), "feedback": beta_feedback
            }
            supabase.table("safety_evaluation").insert(eval_data).execute()
            
            st.session_state.issue_count = 1
            st.success("🎉 점검 기록 및 모든 지적사항이 성공적으로 서버에 등록되었습니다!")

# -----------------------------------------------------------------------------
# [메뉴 2] 내 점검 이력 관리 (지적 현황 자동 표시 연동됨)
# -----------------------------------------------------------------------------
elif menu == "🗂️ 내 점검 이력 관리":
    st.title("🗂️ 나의 누적 점검 이력")
    st.markdown("본인이 등록한 내역만 표시되며, 개별 문항에서 등록한 지적사항도 아래 종합 기록에 표기됩니다.")
    
    res = supabase.table("safety_evaluation").select("*").eq("emp_id", u_info['emp_id']).execute()
    df_my = pd.DataFrame(res.data)
    
    if df_my.empty:
        st.info("아직 등록하신 점검 이력이 없습니다.")
    else:
        df_my = df_my.sort_values(by='date', ascending=False)
        for idx, row in df_my.iterrows():
            with st.expander(f"📍 {row['date']} | {row['branch']} (종합점수: {row['final_score']}점)"):
                st.markdown(f"**지적사항 종합 내역:**\n```text\n{row['remarks'] if row['remarks'] else '지적사항 없음'}\n```")
                if st.button(f"🗑️ 이 점검기록 영구 삭제", key=f"del_{row['id']}"):
                    supabase.table("safety_evaluation").delete().eq("id", row['id']).execute()
                    st.success("삭제 완료! 새로고침 시 리스트에서 사라집니다.")

# -----------------------------------------------------------------------------
# [메뉴 3] 현장 담당자 점검현황(종합)
# -----------------------------------------------------------------------------
elif menu == "📈 현장 담당자 점검현황(종합)":
    st.title("📈 현장 담당자 점검현황(종합)")
    st.markdown("전사 담당자들의 안전 활동 현황과 나의 점검 성과를 종합적으로 비교·확인할 수 있는 메뉴입니다.")
    st.info("🌟 **[주요 지표 안내] 현장의 실질적인 안전 확보를 위해 '지적조치 개선건수'를 가장 중요하게 모니터링하고 있습니다.**")
    
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    df_issues = pd.DataFrame(supabase.table("safety_issues").select("*").execute().data)
    
    if df.empty:
        st.warning("분석할 전사 데이터가 아직 충분하지 않습니다.")
    else:
        my_id = u_info['emp_id']
        my_name = u_info['emp_name']
        
        leaderboard_data = []
        for emp_id_group, group in df.groupby('emp_id'):
            inspector_name = group['inspector'].iloc[0]
            visits = len(group)
            my_avg_score = round(group['final_score'].mean(), 1)
            
            resolved_count = 0
            if not df_issues.empty:
                resolved_count = len(df_issues[(df_issues['emp_id'] == emp_id_group) & (df_issues['status'] == '개선완료')])
                
            leaderboard_data.append({
                "사번": emp_id_group, "담당자": inspector_name,
                "지적조치 개선건수 (★중요)": resolved_count,
                "총 점검횟수": visits, "담당 사업장 평균점수": my_avg_score
            })
            
        stats_df = pd.DataFrame(leaderboard_data)
        stats_df = stats_df.sort_values(by=["지적조치 개선건수 (★중요)", "총 점검횟수", "담당 사업장 평균점수"], ascending=[False, False, False]).reset_index(drop=True)
        stats_df['순위'] = stats_df.index + 1
        
        my_row = stats_df[stats_df['사번'] == my_id]
        if not my_row.empty:
            my_rank = my_row['순위'].values[0]
            my_res = my_row['지적조치 개선건수 (★중요)'].values[0]
            my_vis = my_row['총 점검횟수'].values[0]
            my_score = my_row['담당 사업장 평균점수'].values[0]
            
            avg_res = round(stats_df['지적조치 개선건수 (★중요)'].mean(), 1)
            avg_vis = round(stats_df['총 점검횟수'].mean(), 1)
            avg_score_all = round(stats_df['담당 사업장 평균점수'].mean(), 1)
            
            st.markdown(f"### 🦺 **{my_name}님의 안전 성과 종합 현황 (전체 {len(stats_df)}명 중 {my_rank}위)**")
            
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("🔥 나의 지적조치 개선건수", f"{my_res} 건", delta=f"전체 평균 {avg_res}건 대비 {round(my_res - avg_res, 1)}건")
            with m2: st.metric("📋 나의 총 점검횟수", f"{my_vis} 회", delta=f"전체 평균 {avg_vis}회 대비 {round(my_vis - avg_vis, 1)}회")
            with m3: st.metric("⭐ 내 사업장 평균점수", f"{my_score} 점", delta=f"전체 사업장 평균 {avg_score_all}점 대비 {round(my_score - avg_score_all, 1)}점")
                
        st.markdown("---")
        st.markdown("### 📊 전사 현장 담당자 실시간 활동 현황")
        
        display_df = stats_df[['순위', '담당자', '지적조치 개선건수 (★중요)', '총 점검횟수', '담당 사업장 평균점수']]
        st.dataframe(display_df.style.background_gradient(cmap="Oranges", subset=["지적조치 개선건수 (★중요)"]), use_container_width=True)
        
        fig_comp = px.bar(stats_df, x="담당자", y="지적조치 개선건수 (★중요)", color="담당 사업장 평균점수", title="담당자별 지적조치 개선 성과 시각화", text_auto=True)
        st.plotly_chart(fig_comp, use_container_width=True)

# -----------------------------------------------------------------------------
# [메뉴 4] PC 경영진 종합 대시보드
# -----------------------------------------------------------------------------
elif menu == "📊 PC 경영진 종합 대시보드":
    st.title("📊 경영진 종합 대시보드 (PC 보고용)")
    
    df = pd.DataFrame(supabase.table("safety_evaluation").select("*").execute().data)
    df_issues = pd.DataFrame(supabase.table("safety_issues").select("*").execute().data)
    
    if df.empty:
        st.warning("분석할 클라우드 데이터가 없습니다.")
    else:
        tab_main, tab_kpi, tab_capa, tab_feedback = st.tabs(["🌐 전사 종합 모니터링", "🏆 담당자 성과평가(KPI)", "🚨 지적사항(CAPA) 추적 현황", "📝 베타 피드백(VoC)"])
        
        with tab_main:
            total_avg = round(df['final_score'].mean(), 1)
            above_avg_df = df[df['final_score'] >= total_avg]
            below_avg_df = df[df['final_score'] < total_avg]
            
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("📈 전사 평균 점수", f"{total_avg} 점")
            kpi2.markdown(f"<div style='background-color:#e8f8f5; padding:12px; border-radius:6px; border-left:6px solid #2ecc71;'><p style='margin:0; color:#16a085;'><b>🟢 평균 이상 (우수)</b></p><h2 style='margin:5px 0; color:#111;'>{len(above_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
            kpi3.markdown(f"<div style='background-color:#fdedec; padding:12px; border-radius:6px; border-left:6px solid #e74c3c;'><p style='margin:0; color:#c0392b;'><b>🔴 평균 미달 (취약)</b></p><h2 style='margin:5px 0; color:#111;'>{len(below_avg_df)} 개소</h2></div>", unsafe_allow_html=True)
            st.markdown("---")

            st.markdown("### 🎯 6대 영역별 전사 평균 안전 준수율")
            s_avgs_dash, s_names_dash = [], list(SECTIONS_MAP.keys())
            for s_name, q_ids in SECTIONS_MAP.items():
                s_max = sum([max(QUESTIONS[qid]["options"].values()) for qid in q_ids])
                avg_score = sum([df[f'q{qid}'].mean() for qid in q_ids])
                s_avgs_dash.append(round((avg_score / s_max) * 100, 1) if s_max else 0)

            fig_radar_dash = ob.Figure()
            fig_radar_dash.add_trace(ob.Scatterpolar(r=s_avgs_dash, theta=s_names_dash, fill='toself', name='전사 평균 준수율(%)', line=dict(color='#3498db')))
            fig_radar_dash.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), template="plotly_white", height=450)
            st.plotly_chart(fig_radar_dash, use_container_width=True)
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
                
            col_rank, col_risk = st.columns(2)
            with col_rank:
                st.markdown("### 🏆 전사 평가 순위")
                rank_df = df.sort_values(by="final_score", ascending=False)[['branch', 'final_score', 'inspector', 'date']]
                st.dataframe(rank_df, use_container_width=True)
            
            with col_risk:
                st.markdown("### 🚨 리스크 진단: 취약 항목 TOP 5")
                q_cols = [f'q{i}' for i in range(1, 17)]
                q_avg = df[q_cols].mean()
                q_perf = {QUESTIONS[int(col[1:])]["title"]: round((q_avg[col] / max(QUESTIONS[int(col[1:])]["options"].values())) * 100, 1) for col in q_cols}
                perf_df = pd.DataFrame(list(q_perf.items()), columns=['항목', '준수율(%)']).sort_values(by='준수율(%)')
                
                for idx, (_, row) in enumerate(perf_df.head(5).iterrows()):
                    st.error(f"**취약 {idx+1}위 : {row['항목']}** (전사 준수율: **{row['준수율(%)']}%**)")

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
# [메뉴 5] 1페이지 요약 및 PDF 출력
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