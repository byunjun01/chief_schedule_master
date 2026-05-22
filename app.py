import streamlit as st
import pandas as pd
import json
import io
import traceback
from datetime import datetime, timedelta
from utils import PROF_ORDER, RAW_SCHEDULES_INITIAL, get_task_style, get_prof_raw_style, generate_schedule, run_auto_assignment
from manual import show_manual # [추가] 사용법 모듈 불러오기
from verification import verify_schedule  # [추가] 스케줄 검증 모듈

st.set_page_config(page_title="의국 스케줄 마스터 v40", layout="wide")

# --- 초기 상태 설정 ---
if 'base_date' not in st.session_state: st.session_state.base_date = datetime(2026, 6, 1).date()
if 'week_count' not in st.session_state: st.session_state.week_count = 5
if 'user_holidays_str' not in st.session_state: st.session_state.user_holidays_str = ""
if 'off_slots' not in st.session_state: st.session_state.off_slots = []
if 'residents' not in st.session_state: st.session_state.residents = []
if 'resident_leaves' not in st.session_state: st.session_state.resident_leaves = []
if 'pain_applicants' not in st.session_state: st.session_state.pain_applicants = []
if 'student_practices' not in st.session_state: st.session_state.student_practices = []
if 'assignments' not in st.session_state: st.session_state.assignments = {}
if 'alloc_report' not in st.session_state: st.session_state.alloc_report = ""
if 'current_df_all' not in st.session_state: st.session_state.current_df_all = pd.DataFrame()
if 'res_daily_slots' not in st.session_state: st.session_state.res_daily_slots = {}
if 'bogeonso_substitutes' not in st.session_state: st.session_state.bogeonso_substitutes = {}  # {"MM-DD": [name1, name2, ...]}
if 'supplementary_schedules' not in st.session_state: st.session_state.supplementary_schedules = []  # [{"교수","날짜","시간","진료명"}, ...]
if 'use_cpsat' not in st.session_state: st.session_state.use_cpsat = True  # CP-SAT 모드 (신규, 기본값)
if 'cpsat_time_limit' not in st.session_state: st.session_state.cpsat_time_limit = 60
if 'cpsat_manual_multiplier' not in st.session_state: st.session_state.cpsat_manual_multiplier = "자동"

if 'master_schedules' not in st.session_state:
    st.session_state.master_schedules = pd.DataFrame(RAW_SCHEDULES_INITIAL, columns=["교수명", "요일", "시간", "진료명", "주기", "차리생성", "참관생성", "태그"])

def get_date_options(base_date, week_count, extended=False):
    """
    extended=False (기본): 현재 주차 범위까지의 평일만 반환
    extended=True: 다음 1주 평일도 추가 (라벨에 [다음주] 태그)
        - 휴진/보충진료처럼 표시 범위 밖이지만 차리/판정 생성에 영향을 주는 항목에서 사용
    """
    dates = []
    weekdays = ["월", "화", "수", "목", "금"]
    for w in range(week_count):
        for d in range(5):
            dt = base_date + timedelta(days=w*7 + d)
            dates.append(f"{dt.strftime('%m-%d')} ({weekdays[d]})")
    if extended:
        # 다음 1주 평일 추가
        for d in range(5):
            dt = base_date + timedelta(days=week_count*7 + d)
            dates.append(f"{dt.strftime('%m-%d')} ({weekdays[d]}) [다음주]")
    return dates

def get_sorted_residents(residents):
    def rank_score(r):
        year, roles = r['연차'], r['역할']
        yp = {"R3": 400, "R2": 300, "R1": 200, "R0": 100}.get(year, 0)
        rp = 0
        if year == "R3":
            if "의국수석" in roles: rp = 60
            elif "교육수석" in roles: rp = 50
            elif "학생수석" in roles: rp = 40
            elif "진료수석" in roles: rp = 30
            elif "본원 영상" in roles: rp = 10
            else: rp = 20
        elif year == "R2": rp = 10 if "연건 보건소" in roles else 20
        return yp + rp
    return sorted(residents, key=rank_score, reverse=True)

# --- 엑셀 생성 함수 ---
def generate_excel_data(week_count, base_date, sorted_res_list, user_holidays, res_daily_slots, assignments, df_all, task_map):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    wb = Workbook(); ws = wb.active; ws.title = "전공의 스케줄"
    font_default = Font(name='맑은 고딕', size=11); font_white = Font(name='맑은 고딕', size=11, color="FFFFFFFF")
    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    side_thin = Side(style='thin'); side_thick = Side(style='medium')
    thin_border = Border(left=side_thin, right=side_thin, top=side_thin, bottom=side_thin)
    thick_top_border = Border(left=side_thin, right=side_thin, top=side_thick, bottom=side_thin)
    ws.column_dimensions['A'].width = 10; ws.column_dimensions['B'].width = 15
    for col in ['C', 'D', 'E', 'F', 'G']: ws.column_dimensions[col].width = 28
    current_row = 1
    for w in range(1, week_count + 1):
        ws.cell(row=current_row, column=2).border = thin_border
        for d_idx, day_name in enumerate(["월", "화", "수", "목", "금"]):
            dt = base_date + timedelta(days=(w-1)*7 + d_idx)
            cell = ws.cell(row=current_row, column=3+d_idx, value=dt.strftime("%m월 %d일"))
            cell.font = font_default; cell.alignment = align_center; cell.border = thin_border; cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        start_row_for_week = current_row + 1; current_row += 1
        prev_group = None
        for res in sorted_res_list:
            res_name = res['이름']; roles = ", ".join(res['역할']) if res['역할'] else ""; r1, r2 = current_row, current_row + 1
            curr_group = "R1/R0" if res['연차'] in ["R1", "R0"] else res['연차']
            is_new_group = prev_group is not None and curr_group != prev_group
            prev_group = curr_group
            current_r1_border = thick_top_border if is_new_group else thin_border
            cell_name = ws.cell(row=r1, column=2, value=res_name); cell_role = ws.cell(row=r2, column=2, value=roles)
            cell_name.font = font_default; cell_name.alignment = align_center; cell_name.border = current_r1_border
            cell_role.font = font_default; cell_role.alignment = align_center; cell_role.border = thin_border
            for d_idx, day_name in enumerate(["월", "화", "수", "목", "금"]):
                d_str = (base_date + timedelta(days=(w-1)*7 + d_idx)).strftime("%m-%d")
                am_task, pm_task, am_bg, pm_bg, am_fg, pm_fg = "", "", "FFFFFF", "FFFFFF", "black", "black"
                if d_str in user_holidays:
                    am_task = pm_task = "공휴일"; am_bg = pm_bg = "A6A6A6"
                else:
                    a_id = res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오전')
                    if a_id:
                        if any(kw in a_id for kw in ["휴가", "Off"]): am_task = a_id; am_bg = "A6A6A6"; am_fg = "white"
                        elif a_id == "영상": am_task = a_id; am_bg = "D5E8D4"
                        elif any(kw in a_id for kw in ["메인외래", "연보"]): am_task = a_id; am_bg = "E8F8F5" if "메인" in a_id else "FF85FF"
                        else: am_task = task_map.get(a_id, a_id); am_bg, am_fg = get_task_style(am_task)
                    p_id = res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오후')
                    if p_id:
                        if any(kw in p_id for kw in ["휴가", "Off"]): pm_task = p_id; pm_bg = "A6A6A6"; pm_fg = "white"
                        elif p_id == "영상": pm_task = p_id; pm_bg = "D5E8D4"
                        elif any(kw in p_id for kw in ["메인외래", "연보"]): pm_task = p_id; pm_bg = "E8F8F5" if "메인" in p_id else "FF85FF"
                        else: pm_task = task_map.get(p_id, p_id); pm_bg, pm_fg = get_task_style(pm_task)
                am_bg_h = am_bg.replace("#", ""); pm_bg_h = pm_bg.replace("#", "")
                cell_am = ws.cell(row=r1, column=3+d_idx, value=am_task); cell_pm = ws.cell(row=r2, column=3+d_idx, value=pm_task)
                cell_am.font = font_white if am_fg == "white" else font_default; cell_pm.font = font_white if pm_fg == "white" else font_default
                cell_am.alignment = align_center; cell_pm.alignment = align_center
                cell_am.border = current_r1_border; cell_pm.border = thin_border
                if am_bg_h != "FFFFFF": cell_am.fill = PatternFill(start_color=am_bg_h, end_color=am_bg_h, fill_type="solid")
                if pm_bg_h != "FFFFFF": cell_pm.fill = PatternFill(start_color=pm_bg_h, end_color=pm_bg_h, fill_type="solid")
            current_row += 2
        ws.merge_cells(start_row=start_row_for_week-1, start_column=1, end_row=current_row-1, end_column=1)
        cw = ws.cell(row=start_row_for_week-1, column=1, value=f"{w}주차"); cw.font = font_default; cw.alignment = align_center; cw.border = thin_border
    output = io.BytesIO(); wb.save(output); return output.getvalue()


# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 기본 설정")
    new_base_date = st.date_input("시작 월요일", value=st.session_state.base_date)
    new_week_count = st.radio("주차 설정", [4, 5], index=0 if st.session_state.week_count == 4 else 1)
    st.markdown("---")
    st.header("🏖️ 교수 휴진/공휴일 관리")
    new_holidays_str = st.text_input("공휴일 (MM-DD, 쉼표 구분)", value=st.session_state.user_holidays_str)
    if st.button("📅 설정 및 공휴일 확정 적용", use_container_width=True, type="primary"):
        st.session_state.base_date = new_base_date
        st.session_state.week_count = new_week_count
        st.session_state.user_holidays_str = new_holidays_str
        u_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
        st.session_state.current_df_all = generate_schedule(new_base_date, new_week_count, u_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules)
        st.success("설정이 스케줄에 반영되었습니다."); st.rerun()
    user_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
    available_dates = get_date_options(st.session_state.base_date, st.session_state.week_count)
    # 휴진/보충진료용: 다음 1주까지 포함 (표시 범위 밖이지만 차리/판정 생성에 영향)
    available_dates_extended = get_date_options(st.session_state.base_date, st.session_state.week_count, extended=True)
    with st.form("off_form", clear_on_submit=True):
        p_select = st.selectbox("교수님", PROF_ORDER)
        d_selects = st.multiselect("휴진 날짜", options=available_dates_extended, help="[다음주] 태그가 붙은 날짜는 표시 범위 밖이지만 차리/판정 생성에 영향을 줍니다")
        if st.form_submit_button("휴진 등록"):
            for d_str in d_selects:
                # 라벨 형식: "MM-DD (요일)" 또는 "MM-DD (요일) [다음주]" → MM-DD만 추출
                date_only = d_str.split(" ")[0]
                if (p_select, date_only) not in st.session_state.off_slots: st.session_state.off_slots.append((p_select, date_only))
            st.session_state.current_df_all = generate_schedule(st.session_state.base_date, st.session_state.week_count, user_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules); st.rerun()
    if st.session_state.off_slots:
        with st.expander(f"📋 등록된 휴진 ({len(st.session_state.off_slots)}건)", expanded=True):
            # 교수별 → 날짜순 정렬하여 가독성 향상 (원래 인덱스는 삭제용으로 보존)
            indexed = sorted(
                enumerate(st.session_state.off_slots),
                key=lambda x: (PROF_ORDER.index(x[1][0]) if x[1][0] in PROF_ORDER else 999, x[1][1])
            )
            n_cols = 2
            grid_cols = st.columns(n_cols)
            for pos, (i, (p, d)) in enumerate(indexed):
                with grid_cols[pos % n_cols]:
                    cc1, cc2 = st.columns([4, 1])
                    cc1.write(f"· {p} ({d})")
                    if cc2.button("X", key=f"prof_off_{i}"):
                        st.session_state.off_slots.pop(i)
                        st.session_state.current_df_all = generate_schedule(st.session_state.base_date, st.session_state.week_count, user_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules)
                        st.rerun()
    st.markdown("---")
    st.header("➕ 보충진료 추가")
    st.caption("단발성 진료를 추가하면 차리/판정/참관이 자동 생성됩니다. (위치: 진료일 -2영업일)")
    PROFS_WITH_AMOEHRAE = ["황서은", "조수환", "민경하", "김지영", "김하진"]
    PROFS_WITH_CLINIC = ["조비룡", "박민선", "박진호"]
    with st.form("supp_form", clear_on_submit=True):
        sup_prof = st.selectbox("교수님", PROF_ORDER, key="sup_prof")
        sup_dates = st.multiselect("날짜 (복수 선택 가능)", options=available_dates_extended, key="sup_dates", help="[다음주] 태그가 붙은 날짜는 표시 범위 밖이지만 차리/판정 생성에 영향을 줍니다")
        sup_time = st.selectbox("시간", ["오전", "오후"], key="sup_time")
        # 진료종류 동적 옵션
        clinic_options = ["건증", "외래"]
        if sup_prof in PROFS_WITH_AMOEHRAE:
            clinic_options.append("암외래")
        if sup_prof in PROFS_WITH_CLINIC:
            clinic_options.append("클리닉")
        sup_clinic = st.selectbox("진료종류", clinic_options, key="sup_clinic")
        if st.form_submit_button("➕ 보충진료 등록"):
            # 박진호 클리닉 → 통증클리닉으로 저장
            clinic_to_save = "통증클리닉" if (sup_prof == "박진호" and sup_clinic == "클리닉") else sup_clinic
            error_dates = []
            added_count = 0
            for d_str_full in sup_dates:
                d_str = d_str_full.split(" ")[0]
                # 휴진 충돌 검사
                if (sup_prof, d_str) in st.session_state.off_slots:
                    error_dates.append(d_str)
                    continue
                # 중복 검사
                already_exists = any(
                    s["교수"] == sup_prof and s["날짜"] == d_str and s["시간"] == sup_time and s["진료명"] == clinic_to_save
                    for s in st.session_state.supplementary_schedules
                )
                if already_exists:
                    continue
                st.session_state.supplementary_schedules.append({
                    "교수": sup_prof, "날짜": d_str, "시간": sup_time, "진료명": clinic_to_save
                })
                added_count += 1
            if error_dates:
                st.error(f"❌ {sup_prof} 교수는 다음 날짜에 휴진 등록되어 있어 보충진료를 추가할 수 없습니다: {', '.join(error_dates)}")
            if added_count > 0:
                st.session_state.current_df_all = generate_schedule(
                    st.session_state.base_date, st.session_state.week_count, user_holidays,
                    st.session_state.master_schedules, st.session_state.off_slots,
                    supplementary_schedules=st.session_state.supplementary_schedules
                )
                st.rerun()
    if st.session_state.supplementary_schedules:
        st.caption(f"등록된 보충진료 ({len(st.session_state.supplementary_schedules)}건):")
        for i, s in enumerate(st.session_state.supplementary_schedules):
            c1, c2 = st.columns([4, 1])
            c1.write(f"· {s['교수']} ({s['날짜']} {s['시간']} {s['진료명']})")
            if c2.button("X", key=f"sup_del_{i}"):
                st.session_state.supplementary_schedules.pop(i)
                st.session_state.current_df_all = generate_schedule(
                    st.session_state.base_date, st.session_state.week_count, user_holidays,
                    st.session_state.master_schedules, st.session_state.off_slots,
                    supplementary_schedules=st.session_state.supplementary_schedules
                )
                st.rerun()
    st.markdown("---")
    st.header("💾 백업 및 복구")
    export_data = {
        "base_date": new_base_date.strftime("%Y-%m-%d"),
        "week_count": new_week_count,
        "user_holidays_str": new_holidays_str,
        "off_slots": st.session_state.off_slots,
        "residents": st.session_state.residents,
        "resident_leaves": st.session_state.resident_leaves,
        "pain_applicants": st.session_state.pain_applicants,
        "student_practices": st.session_state.student_practices,
        "assignments": st.session_state.assignments,
        "bogeonso_substitutes": st.session_state.bogeonso_substitutes,
        "supplementary_schedules": st.session_state.supplementary_schedules,
        "master_schedules": st.session_state.master_schedules.to_dict(orient="records"),
        # 디버깅용 - CP-SAT 결과의 시간/날짜 결정 정보
        "task_time_overrides": st.session_state.get("cpsat_task_time_overrides", {}),
        "task_date_overrides": st.session_state.get("cpsat_task_date_overrides", {}),
        "shifted_tasks": st.session_state.get("cpsat_shifted_tasks", []),
        "original_df_dates": st.session_state.get("cpsat_original_df_dates", {}),
    }
    st.download_button("📥 설정 저장", json.dumps(export_data, ensure_ascii=False, indent=2), f"backup_{datetime.today().strftime('%Y%m%d')}.json", "application/json", use_container_width=True)
    uploaded_file = st.file_uploader("📤 불러오기", type=["json"])
    if uploaded_file and st.button("데이터 적용"):
        data = json.load(uploaded_file)
        st.session_state.base_date = datetime.strptime(data["base_date"], "%Y-%m-%d").date()
        st.session_state.week_count = data.get("week_count", 5)
        st.session_state.user_holidays_str = data.get("user_holidays_str", "")
        st.session_state.off_slots = [tuple(x) for x in data.get("off_slots", [])]
        st.session_state.residents = data.get("residents", [])
        st.session_state.resident_leaves = data.get("resident_leaves", [])
        st.session_state.pain_applicants = data.get("pain_applicants", [])
        st.session_state.student_practices = data.get("student_practices", [])
        st.session_state.assignments = data.get("assignments", {})
        st.session_state.bogeonso_substitutes = data.get("bogeonso_substitutes", {})
        st.session_state.supplementary_schedules = data.get("supplementary_schedules", [])
        st.session_state.master_schedules = pd.DataFrame(data.get("master_schedules", RAW_SCHEDULES_INITIAL))
        u_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
        st.session_state.current_df_all = generate_schedule(st.session_state.base_date, st.session_state.week_count, u_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules)
        st.rerun()

if st.session_state.current_df_all.empty:
    user_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
    st.session_state.current_df_all = generate_schedule(st.session_state.base_date, st.session_state.week_count, user_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules)

df_all = st.session_state.current_df_all
st.markdown("<div style='font-size: 1.1rem; font-weight: 600; margin-bottom: 15px; color: #555555; text-align: left;'>👨‍💻 Made by 45기 변준혁 문의 T. 010-4937-1111</div>", unsafe_allow_html=True)

# --- 메인 탭 (순서 변경: 사용법이 가장 왼쪽) ---
tabs = st.tabs(["📖 사용법", "👨‍🏫 교수별 시간표", "📊 주차별 가이드", "⚙️ 규칙 설정", "👨‍⚕️ 전공의 명단", "🌴 전공의 휴가", "📝 스케줄 배정", "📅 전공의 개인별", "🗓️ 주차별 전체 현황(Excel양식)", "✅ 스케줄 검증"])

# 탭 인덱스 0: 사용법
with tabs[0]:
    show_manual()

# 탭 인덱스 4 (기존 3): 전공의 명단
with tabs[4]:
    st.subheader("👨‍⚕️ 전공의 명단 및 역할 관리")
    with st.container():
        cols = st.columns([1, 1.5, 3, 1.5, 1])
        with cols[0]: r_year = st.selectbox("연차", ["R3", "R2", "R1", "R0"])
        with cols[1]: r_name = st.text_input("이름")
        with cols[2]:
            if r_year == "R3": r_tags = st.multiselect("역할", ["본원 영상", "의국수석", "교육수석", "학생수석", "진료수석"])
            elif r_year == "R2": r_tags = st.multiselect("역할", ["연건 보건소"])
            elif r_year == "R1": r_tags = st.multiselect("역할", ["의국 처음"])
            else: r_tags = []
        with cols[3]: r_main = st.selectbox("메인외래", ["선택안함", "월", "화", "수", "목", "금"]) if r_year == "R3" else "선택안함"
        with cols[4]:
            if st.button("➕ 등록", use_container_width=True) and r_name.strip():
                st.session_state.residents.append({"연차": r_year, "이름": r_name.strip(), "역할": r_tags, "메인외래": r_main, "영상파견요일": []}); st.rerun()
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    for idx, year in enumerate(["R3", "R2", "R1", "R0"]):
        with [c1, c2, c3, c4][idx]:
            st.markdown(f"#### 🔹 {year}")
            for r in [res for res in st.session_state.residents if res["연차"] == year]:
                g_idx = st.session_state.residents.index(r)
                with st.container():
                    rc1, rc2 = st.columns([4, 1])
                    tag_txt = f"<br><small style='color:#1f77b4;'>{', '.join(r['역할'])}</small>" if r['역할'] else ""
                    main_txt = f"<br><small style='color:#d62728;'>메인: {r.get('메인외래', '선택안함')}</small>" if r.get('메인외래') != "선택안함" else ""
                    rad_days_now = r.get('영상파견요일', [])
                    rad_txt = f"<br><small style='color:#27ae60;'>📡 영상 파견: {', '.join(rad_days_now)}</small>" if rad_days_now else ""
                    rc1.markdown(f"**{r['이름']}**{tag_txt}{main_txt}{rad_txt}", unsafe_allow_html=True)
                    if rc2.button("X", key=f"res_del_{g_idx}"): st.session_state.residents.pop(g_idx); st.rerun()
                    # 본원 영상 역할이 있으면 영상 파견 요일 multiselect 노출
                    if "본원 영상" in r.get('역할', []):
                        new_rad = st.multiselect(
                            "영상의학과 파견 요일 (매주)",
                            options=["월", "화", "수", "목", "금"],
                            default=rad_days_now,
                            key=f"rad_days_{g_idx}",
                            help="선택한 요일에는 매주 오전+오후 모두 '영상'으로 고정됩니다."
                        )
                        if new_rad != rad_days_now:
                            st.session_state.residents[g_idx]['영상파견요일'] = new_rad
                            st.rerun()

# 탭 인덱스 5 (기존 4): 전공의 휴가
with tabs[5]:
    st.subheader("🌴 전공의 휴가 입력")
    res_names = [r["이름"] for r in st.session_state.residents]
    with st.form("leave_form", clear_on_submit=True):
        cols = st.columns([2, 3, 2, 1])
        l_name, l_dates = cols[0].selectbox("전공의", res_names if res_names else ["없음"]), cols[1].multiselect("날짜", options=available_dates)
        l_type = cols[2].selectbox("종류", ["직전휴가", "사전휴가", "Off"])
        if cols[3].form_submit_button("등록") and res_names:
            for d_str in l_dates: st.session_state.resident_leaves.append({"이름": l_name, "날짜": d_str.split(" ")[0], "종류": l_type})
            st.rerun()
    if st.session_state.resident_leaves:
        with st.expander(f"📋 등록된 휴가 ({len(st.session_state.resident_leaves)}건)", expanded=True):
            # 신청자(전공의)별로 묶어서 표시 — 원래 인덱스는 삭제용으로 보존
            from collections import defaultdict as _dd
            groups = _dd(list)
            for i, lv in enumerate(st.session_state.resident_leaves):
                groups[lv['이름']].append((i, lv))
            # 명단 순서 우선, 명단에 없는 이름은 뒤에 이름순
            ordered_names = [n for n in res_names if n in groups] + sorted(n for n in groups if n not in res_names)
            for name in ordered_names:
                items = sorted(groups[name], key=lambda x: x[1]['날짜'])
                st.markdown(f"**👤 {name}** · {len(items)}건")
                n_cols = 3
                grid_cols = st.columns(n_cols)
                for pos, (i, lv) in enumerate(items):
                    with grid_cols[pos % n_cols]:
                        cc1, cc2 = st.columns([5, 1])
                        cc1.write(f"{lv['날짜']} [{lv['종류']}]")
                        if cc2.button("X", key=f"leave_del_{i}"):
                            st.session_state.resident_leaves.pop(i)
                            st.rerun()

# 탭 인덱스 6 (기존 5): 스케줄 배정
with tabs[6]:
    st.subheader("📝 스케줄 배정 및 자동 생성")
    res_names = [r["이름"] for r in st.session_state.residents]
    
    # === [신규] 연건 보건소 휴가 대체자 설정 ===
    st.markdown("#### 🏥 연건 보건소 휴가 대체자 설정")
    # 연건 보건소 담당자 찾기
    bogeonso_residents = [r["이름"] for r in st.session_state.residents if "연건 보건소" in r.get("역할", [])]
    # 연건 보건소 담당자가 휴가인 날짜 추출
    bogeonso_leave_dates = sorted(set(
        l["날짜"] for l in st.session_state.resident_leaves if l["이름"] in bogeonso_residents
    ))
    
    if not bogeonso_residents:
        st.info("ℹ️ 연건 보건소 역할이 지정된 전공의가 없습니다. (전공의 명단 탭에서 R2에게 '연건 보건소' 역할을 부여하세요)")
    elif not bogeonso_leave_dates:
        st.info(f"ℹ️ 현재 연건 보건소 담당자({', '.join(bogeonso_residents)})의 휴가가 등록되어 있지 않습니다. 휴가가 등록되면 이 영역에서 대체자를 지정할 수 있습니다.")
    else:
        st.caption(f"💡 연건 보건소 담당자: **{', '.join(bogeonso_residents)}** — 휴가 등록된 날짜의 연보 일정을 누가 대신 갈지 지정하세요. (복수 선택 가능, 여러 명 선택 시 슬롯이 라운드로빈 분배됩니다)")
        st.caption("⚠️ 여기서 설정한 대체자는 자동 스케줄 생성 시 **무조건** 해당 날짜의 연보로 배정됩니다. 그리고 그 외 비어있는 시간에는 다른 일반 업무도 추가 배정될 수 있습니다.")
        
        # 휴가 날짜 중 더 이상 유효하지 않은 항목 정리
        st.session_state.bogeonso_substitutes = {
            d: subs for d, subs in st.session_state.bogeonso_substitutes.items() if d in bogeonso_leave_dates
        }
        
        # 대체자 후보 (연건 보건소 본인 제외)
        sub_candidates = [n for n in res_names if n not in bogeonso_residents]
        
        for d_str in bogeonso_leave_dates:
            # 해당 날짜에 휴가 낸 사람과 종류 표시
            leave_info = next((l for l in st.session_state.resident_leaves if l["날짜"] == d_str and l["이름"] in bogeonso_residents), None)
            label_extra = ""
            if leave_info:
                label_extra = f" — {leave_info['이름']} [{leave_info['종류']}]"
            
            # 요일 계산
            try:
                year = st.session_state.base_date.year
                dt = datetime.strptime(f"{year}-{d_str}", "%Y-%m-%d")
                day_name = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
                slot_info = "오전+오후" if dt.weekday() in [1, 3] else "오전만"
            except:
                day_name = "?"
                slot_info = ""
            
            current_subs = st.session_state.bogeonso_substitutes.get(d_str, [])
            # 유효하지 않은 이전 선택 정리
            current_subs = [s for s in current_subs if s in sub_candidates]
            
            selected = st.multiselect(
                f"📅 **{d_str} ({day_name})** {label_extra} — 연보 {slot_info}",
                options=sub_candidates,
                default=current_subs,
                key=f"bogeonso_sub_{d_str}",
                help="여러 명 선택 시 라운드로빈으로 슬롯을 나눠가져갑니다."
            )
            if selected:
                st.session_state.bogeonso_substitutes[d_str] = selected
            elif d_str in st.session_state.bogeonso_substitutes:
                del st.session_state.bogeonso_substitutes[d_str]
    
    st.markdown("---")
    
    st.markdown("#### 🎓 학생 실습 선입력 (로딩 +1)")
    with st.form("student_form", clear_on_submit=True):
        sc1, sc2, sc3 = st.columns(3)
        s_name = sc1.selectbox("대상자", res_names if res_names else ["없음"])
        s_date = sc2.selectbox("날짜", get_date_options(st.session_state.base_date, st.session_state.week_count))
        s_time = sc3.selectbox("시간", ["오전", "오후"])
        if st.form_submit_button("실습 등록") and res_names:
            st.session_state.student_practices.append({"이름": s_name, "날짜": s_date.split(" ")[0], "시간": s_time})
            st.rerun()
    for i, sp in enumerate(st.session_state.student_practices):
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"· **{sp['이름']}** - {sp['날짜']} {sp['시간']} 실습")
        if c2.button("삭제", key=f"sp_{i}"):
            st.session_state.student_practices.pop(i); st.rerun()
    
    st.markdown("---")
    st.markdown("#### 💉 통증클리닉 특수 배정")
    st.session_state.pain_applicants = st.multiselect(
        "박진호 통증클리닉 사전 신청자 (차리/참관 세트 최우선 배정)",
        options=res_names,
        default=[n for n in st.session_state.pain_applicants if n in res_names]
    )
    
    st.markdown("---")
    # === [신규] 사전 진단 박스 ===
    st.markdown("#### 📊 사전 진단")
    if not st.session_state.residents:
        st.caption("전공의 명단을 먼저 등록해주세요.")
        diagnosis_result = None
    else:
        try:
            u_holidays_for_diag = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
            rad_days_for_diag = {
                r['이름']: r.get('영상파견요일', [])
                for r in st.session_state.residents
                if "본원 영상" in r.get('역할', [])
            }
            from utils import pre_assignment_diagnosis
            diagnosis_result = pre_assignment_diagnosis(
                st.session_state.residents,
                st.session_state.resident_leaves,
                st.session_state.week_count,
                st.session_state.base_date,
                u_holidays_for_diag,
                st.session_state.off_slots,
                st.session_state.master_schedules,
                supplementary_schedules=st.session_state.supplementary_schedules,
                rad_days=rad_days_for_diag,
                student_practices=st.session_state.student_practices,
            )
            if diagnosis_result['status'] == "적합":
                st.markdown(f"<div style='padding:10px; background:#E8F8F5; border-left:4px solid #1abc9c; border-radius:3px;'>{diagnosis_result['message']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='padding:10px; background:#FADBD8; border-left:4px solid #e74c3c; border-radius:3px;'>{diagnosis_result['message']}</div>", unsafe_allow_html=True)
            st.caption(f"💡 사용자 지정 평균 로딩 {diagnosis_result['ideal_avg_target_mult']:.2f} | 실제 필요 평균 로딩 {diagnosis_result['required_avg_loading']:.2f} | 자동 상향 배수 {diagnosis_result['multiplier']:.2f}")
        except Exception as e:
            st.error(f"진단 중 오류: {e}")
            diagnosis_result = None

    st.markdown("---")
    # === CP-SAT 솔버 설정 (CP-SAT 모드 상시 사용) ===
    st.session_state.use_cpsat = True
    st.caption("🧮 CP-SAT 솔버로 배정합니다 (모든 룰 보장, 해가 없으면 알림).")
    mode_col2, mode_col3 = st.columns(2)
    with mode_col2:
        st.session_state.cpsat_time_limit = st.number_input(
            "제한시간(초)", min_value=10, max_value=600, value=st.session_state.cpsat_time_limit, step=10
        )
    with mode_col3:
        # 배율 옵션: 자동 또는 1.025~1.200 (0.025 단위)
        mult_options = ["자동"] + [f"{x/1000:.3f}" for x in range(1025, 1201, 25)]
        current = st.session_state.cpsat_manual_multiplier
        if current not in mult_options:
            current = "자동"
        st.session_state.cpsat_manual_multiplier = st.selectbox(
            "배율 강제 지정",
            options=mult_options,
            index=mult_options.index(current),
            help="'자동'이면 시스템이 사전 진단으로 산출. 직접 지정하면 그 배율로 풀이."
        )

    if st.button("🚀 자동 스케줄 랜덤 생성 (플랜 B 포함)", use_container_width=True, type="primary"):
        if not st.session_state.residents: st.error("전공의 명단을 등록해주세요.")
        else:
            u_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
            df_gen = generate_schedule(st.session_state.base_date, st.session_state.week_count, u_holidays, st.session_state.master_schedules, st.session_state.off_slots, supplementary_schedules=st.session_state.supplementary_schedules)
            rad_days_dict = {
                r['이름']: r.get('영상파견요일', [])
                for r in st.session_state.residents
                if "본원 영상" in r.get('역할', [])
            }

            if st.session_state.use_cpsat:
                # === CP-SAT 모드 ===
                manual_mult = None
                if st.session_state.cpsat_manual_multiplier != "자동":
                    try:
                        manual_mult = float(st.session_state.cpsat_manual_multiplier)
                    except Exception:
                        manual_mult = None
                spinner_msg = f'CP-SAT 솔버 실행 중 (최대 {st.session_state.cpsat_time_limit}초'
                if manual_mult is not None:
                    spinner_msg += f', 배율 {manual_mult:.1f} 고정'
                else:
                    spinner_msg += ', 배율 자동'
                spinner_msg += ')...'
                with st.spinner(spinner_msg):
                    from cpsat_solver import solve_schedule
                    cpsat_result = solve_schedule(
                        df_gen, st.session_state.residents, st.session_state.resident_leaves,
                        st.session_state.week_count, st.session_state.base_date, u_holidays,
                        bogeonso_substitutes=st.session_state.bogeonso_substitutes,
                        rad_days=rad_days_dict,
                        student_practices=st.session_state.student_practices,
                        pain_applicants=st.session_state.pain_applicants,
                        time_limit_sec=st.session_state.cpsat_time_limit,
                        manual_multiplier=manual_mult,
                    )

                if cpsat_result['status'] in ['OPTIMAL', 'FEASIBLE']:
                    # 이동 전 원래 날짜 기록 (검증 탭에서 '누락'이 아닌 '이동'으로 인식시키기 위해 필수)
                    _date_ovr = cpsat_result.get('task_date_overrides', {})
                    original_df_dates = {}
                    for tid in _date_ovr:
                        _row = df_gen[df_gen['task_id'] == tid]
                        if not _row.empty:
                            original_df_dates[tid] = _row.iloc[0]['date']
                    st.session_state.cpsat_original_df_dates = original_df_dates
                    # 비고정 task의 시간 결정 적용 (df_gen에 time 컬럼 업데이트)
                    for tid, t_choice in cpsat_result.get('task_time_overrides', {}).items():
                        df_gen.loc[df_gen['task_id'] == tid, 'time'] = t_choice
                    # 날짜 이동 적용 (date_alt로 이동된 차리/판정)
                    weekday_kor = ['월', '화', '수', '목', '금', '토', '일']
                    for tid, new_date in cpsat_result.get('task_date_overrides', {}).items():
                        df_gen.loc[df_gen['task_id'] == tid, 'date'] = new_date
                        # day, week도 업데이트
                        try:
                            new_dt = datetime.strptime(f"{st.session_state.base_date.year}-{new_date}", "%Y-%m-%d").date()
                            new_day = weekday_kor[new_dt.weekday()]
                            new_week = (new_dt - st.session_state.base_date).days // 7 + 1
                            df_gen.loc[df_gen['task_id'] == tid, 'day'] = new_day
                            df_gen.loc[df_gen['task_id'] == tid, 'week'] = new_week
                        except Exception:
                            pass

                    # 보건소 슬롯 표시 (CP-SAT은 일반 task만 다룸, 연건 슬롯은 별도)
                    # 보건소 담당자에게 매주 연보 슬롯 추가 표시는 res_daily_slots에서 처리
                    res_daily_slots = {}
                    weekday_to_idx = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
                    for r in st.session_state.residents:
                        name = r['이름']
                        roles = r.get('역할', [])
                        # daily_slots 초기화
                        daily = {}
                        for w in range(st.session_state.week_count):
                            for d_idx in range(5):
                                from datetime import timedelta
                                dt = st.session_state.base_date + timedelta(days=w*7+d_idx)
                                ds = dt.strftime("%m-%d")
                                daily[ds] = {'오전': None, '오후': None}

                        # 공휴일 (가장 우선)
                        for ds in daily:
                            if ds in u_holidays:
                                daily[ds]['오전'] = '공휴일'
                                daily[ds]['오후'] = '공휴일'

                        # 휴가 (사전휴가/직전휴가/Off 등 — 종류 그대로) - 공휴일 다음 우선
                        for l in st.session_state.resident_leaves:
                            if l['이름'] == name and l['날짜'] in daily:
                                # 공휴일이 아니면 휴가로 표시 (양쪽 모두)
                                if daily[l['날짜']]['오전'] != '공휴일':
                                    daily[l['날짜']]['오전'] = l['종류']
                                if daily[l['날짜']]['오후'] != '공휴일':
                                    daily[l['날짜']]['오후'] = l['종류']

                        # 메인외래 (R3 한정, 휴가/공휴일 제외)
                        main = r.get('메인외래', '선택안함')
                        if main != '선택안함' and main in weekday_to_idx:
                            d_idx = weekday_to_idx[main]
                            for w in range(st.session_state.week_count):
                                dt = st.session_state.base_date + timedelta(days=w*7+d_idx)
                                ds = dt.strftime("%m-%d")
                                if ds in daily and daily[ds]['오전'] is None:
                                    daily[ds]['오전'] = '메인외래'
                                if ds in daily and daily[ds]['오후'] is None:
                                    daily[ds]['오후'] = '메인외래'

                        # 학생실습 (휴가/공휴일/메인외래 제외)
                        for sp in st.session_state.student_practices:
                            if sp['이름'] == name and sp['날짜'] in daily:
                                if daily[sp['날짜']][sp['시간']] is None:
                                    daily[sp['날짜']][sp['시간']] = '학생실습'

                        # 보건소 + 대체자 연보 (CP-SAT의 forced_assignments에서 일괄 처리)
                        # forced_assignments: {(person, date, time): '연보(오전)' or '연보(오후)'}
                        for (fname, fdate, ftime), flabel in cpsat_result.get('forced_assignments', {}).items():
                            if fname != name: continue
                            if fdate in daily and daily[fdate][ftime] is None:
                                daily[fdate][ftime] = flabel

                        # 영상 파견
                        for rd in rad_days_dict.get(name, []):
                            if rd in weekday_to_idx:
                                d_idx = weekday_to_idx[rd]
                                for w in range(st.session_state.week_count):
                                    dt = st.session_state.base_date + timedelta(days=w*7+d_idx)
                                    ds = dt.strftime("%m-%d")
                                    if ds in daily:
                                        if daily[ds]['오전'] is None: daily[ds]['오전'] = '영상'
                                        if daily[ds]['오후'] is None: daily[ds]['오후'] = '영상'

                        # CP-SAT 배정 결과 반영
                        for tid, assignee in cpsat_result['assignments'].items():
                            if assignee != name: continue
                            task_row = df_gen[df_gen['task_id'] == tid]
                            if task_row.empty: continue
                            tr = task_row.iloc[0]
                            ds, ttime = tr['date'], tr['time']
                            if ds in daily and daily[ds].get(ttime) is None:
                                daily[ds][ttime] = tid
                        # 중요: 기존 코드는 res_daily_slots[name]['daily_slots'] 구조 사용
                        # generate_excel_data, 전공의 개인별 탭 등이 이 구조로 접근하므로 동일하게 맞춤
                        res_daily_slots[name] = {'daily_slots': daily}

                    # 리포트 생성
                    report = ["✅ **CP-SAT 배정 리포트**"]
                    report.append("")
                    phase_used = cpsat_result.get('phase_used', 1)
                    phase_tag = " (1단계: 원래 룰)" if phase_used == 1 else " (2단계: 차리/판정 -1일 이동 허용)"
                    report.append(f"🧮 **솔버 결과**: {cpsat_result['status']} (배율 {cpsat_result.get('multiplier_used'):.2f} 적용{phase_tag}, 소요시간 {cpsat_result['wall_time_sec']:.2f}초)")
                    # 배율/단계 히스토리
                    history = cpsat_result.get('multiplier_history', [])
                    if len(history) > 1:
                        history_strs = []
                        for h in history:
                            tag = f"{h['multiplier']:.2f}-{h.get('phase', 1)}단계({h['status']}, 미배정{h.get('unassigned','?')})"
                            history_strs.append(tag)
                        report.append(f"  - 시도 내역: " + " → ".join(history_strs))
                    report.append("")

                    # 사전 검사: 슬롯 부족 날짜 (차리/판정 -1 이동 허용 대상)
                    shortage_dates = cpsat_result.get('shortage_dates', [])
                    if shortage_dates:
                        report.append(f"⚠️ **사전 검사 — 슬롯 부족 날짜 ({len(shortage_dates)}개)** (그 날짜의 차리/판정 -1 평일 이동 허용)")
                        shortage_info = cpsat_result.get('shortage_info', {})
                        for ds in shortage_dates:
                            info = shortage_info.get(ds, {})
                            report.append(f"  - {ds}: task {info.get('tasks','?')}개 / 빈슬롯 {info.get('empty_slots','?')}개")
                        report.append("")

                    # 미배정
                    if cpsat_result['unassigned']:
                        report.append(f"🚨 **미배정 task ({len(cpsat_result['unassigned'])}개)** — 빈 슬롯 부족으로 미배정")
                        task_map = {r['task_id']: r for _, r in df_gen.iterrows()}
                        for tid in cpsat_result['unassigned']:
                            t = task_map.get(tid)
                            if t is not None:
                                report.append(f"  - 주{t['week']} {t['date']}({t['day']}) {t['time']} | {t['task']}")
                        report.append("")

                    # 깨진 pairing
                    if cpsat_result['broken_pairs']:
                        report.append(f"🔗 **깨진 pairing ({len(cpsat_result['broken_pairs'])}개)** (최대 5개 허용)")
                        for pid in cpsat_result['broken_pairs']:
                            report.append(f"  - {pid}")
                        report.append("")

                    # 차리/판정 날짜 이동 표시
                    shifted = cpsat_result.get('shifted_tasks', [])
                    if shifted:
                        report.append(f"📅 **날짜 이동된 차리/판정 ({len(shifted)}개)** — 미배정 줄이기 위해 -1 평일 이동")
                        task_map_orig = {r['task_id']: r for _, r in df_gen.iterrows()}
                        date_overrides = cpsat_result.get('task_date_overrides', {})
                        for tid in shifted:
                            t = task_map_orig.get(tid)
                            new_d = date_overrides.get(tid, '?')
                            if t is not None:
                                report.append(f"  - {t['task']}: 원래 → {new_d}로 이동")
                        report.append("")

                    # 사람별 통계
                    from collections import Counter
                    person_count = Counter(cpsat_result['assignments'].values())
                    task_map = {r['task_id']: r for _, r in df_gen.iterrows()}
                    from cpsat_solver import build_problem_data, get_loading_group
                    pdata = build_problem_data(df_gen, st.session_state.residents, st.session_state.resident_leaves,
                                                st.session_state.week_count, st.session_state.base_date, u_holidays,
                                                rad_days=rad_days_dict, student_practices=st.session_state.student_practices,
                                                bogeonso_substitutes=st.session_state.bogeonso_substitutes)
                    forced_per_person = pdata.get('person_forced_count', {})
                    for r in sorted(st.session_state.residents, key=lambda x: get_loading_group(x, rad_days_dict)):
                        name = r['이름']
                        avail = pdata['person_avail_sessions'].get(name, 1)
                        cnt = person_count.get(name, 0)
                        forced = forced_per_person.get(name, 0)  # 강제 연보 슬롯 수
                        total_cnt = cnt + forced  # 일반 task + 연보 (로딩 분자)
                        load = total_cnt * 10 / avail if avail > 0 else 0
                        # 판정/처치 카운트
                        pj = 0; tx = 0
                        for tid, n in cpsat_result['assignments'].items():
                            if n != name: continue
                            tt = task_map.get(tid)
                            if tt is None: continue
                            if '판정' in tt['task'] and '참관' not in tt['task']:
                                if not (any(p in tt['task'] for p in ['조비룡', '박민선']) and '클리닉' in tt['task']):
                                    pj += 1
                            if '처치' in tt['task']: tx += 1
                        report.append(f"- **{name} ({r['연차']})**: 세션 {total_cnt}/{avail} (로딩 {load:.2f}) | 🩺판정: **{pj}** | 💉처치: **{tx}**")

                    st.session_state.current_df_all = df_gen
                    st.session_state.assignments = cpsat_result['assignments']
                    st.session_state.alloc_report = "\n".join(report)
                    st.session_state.res_daily_slots = res_daily_slots
                    # 디버깅용 - 백업에 포함시키기 위해 session_state에 저장
                    st.session_state.cpsat_task_time_overrides = cpsat_result.get('task_time_overrides', {})
                    st.session_state.cpsat_task_date_overrides = cpsat_result.get('task_date_overrides', {})
                    st.session_state.cpsat_shifted_tasks = cpsat_result.get('shifted_tasks', [])
                    # FEASIBLE이니까 이전 INFEASIBLE 정보 초기화
                    st.session_state.pop('infeasible_input', None)
                    st.session_state.pop('last_diagnosis', None)
                    st.success(f"CP-SAT 배정 완료! 배율 {cpsat_result.get('multiplier_used'):.2f}, {cpsat_result['wall_time_sec']:.2f}초")
                    st.rerun()
                else:
                    # INFEASIBLE — 진단은 별도 버튼으로 사용자 명시적 실행
                    error_lines = ["❌ **CP-SAT 솔버: 해가 없습니다 (INFEASIBLE)**"]
                    error_lines.append("")
                    error_lines.append(f"배율 {cpsat_result.get('multiplier_used', '?')}로 모든 hard rule을 동시 만족하는 배정이 존재하지 않습니다.")
                    error_lines.append("")
                    error_lines.append("**가능한 해결책:**")
                    error_lines.append("- 전공의 인원 추가")
                    error_lines.append("- 휴가 조정")
                    error_lines.append("- 아래 **'INFEASIBLE 진단 실행'** 버튼으로 충돌 룰 찾기 (시간 걸림)")
                    error_lines.append("- 위 충돌 룰 완화 (개발자 문의)")
                    error_lines.append("")
                    history = cpsat_result.get('multiplier_history', [])
                    if history:
                        error_lines.append("**시도 내역:**")
                        for h in history:
                            error_lines.append(f"  - 배율 {h['multiplier']:.2f}: {h['status']} ({h['wall_time']:.2f}초)")
                    st.error("\n".join(error_lines))
                    st.session_state.alloc_report = "\n".join(error_lines)
                    # 진단 버튼을 위해 입력 데이터 보관
                    st.session_state.infeasible_input = {
                        'df_gen': df_gen,
                        'residents': st.session_state.residents,
                        'resident_leaves': st.session_state.resident_leaves,
                        'week_count': st.session_state.week_count,
                        'base_date': st.session_state.base_date,
                        'holidays': u_holidays,
                        'bogeonso_substitutes': st.session_state.bogeonso_substitutes,
                        'rad_days': rad_days_dict,
                        'student_practices': st.session_state.student_practices,
                        'pain_applicants': st.session_state.pain_applicants,
                        'auto_mult': cpsat_result.get('multiplier_used', 1.0),
                    }

            else:
                # === 기존 점수 방식 (호환성) ===
                with st.spinner('배정 중... (10회 시도 후 최적 선택)'):
                    mult = diagnosis_result['multiplier'] if diagnosis_result else 1.0
                    from utils import run_auto_assignment_multi
                    o_df, n_assign, r_txt, n_slots = run_auto_assignment_multi(
                        df_gen, st.session_state.residents, st.session_state.resident_leaves,
                        st.session_state.week_count, st.session_state.base_date, u_holidays,
                        st.session_state.pain_applicants, st.session_state.student_practices,
                        bogeonso_substitutes=st.session_state.bogeonso_substitutes,
                        rad_days=rad_days_dict,
                        target_mult_multiplier=mult,
                        num_trials=10
                    )
                    st.session_state.current_df_all, st.session_state.assignments, st.session_state.alloc_report, st.session_state.res_daily_slots = o_df, n_assign, r_txt, n_slots
                st.success("자동 배정 완료! (10회 시도 중 최적 결과 선택)")
                st.rerun()
    if st.session_state.alloc_report:
        with st.expander("📊 배정 리포트", expanded=True): st.info(st.session_state.alloc_report)

    # === INFEASIBLE 진단 버튼 ===
    if st.session_state.get('infeasible_input'):
        with st.expander("🔍 INFEASIBLE 진단", expanded=True):
            st.warning("배정 실패 (INFEASIBLE) — 어떤 룰이 충돌하는지 진단할 수 있습니다.")
            diag_col1, diag_col2, diag_col3 = st.columns([1, 1, 2])
            with diag_col1:
                diag_per_solve = st.number_input("각 시도 제한 (초)", min_value=3, max_value=30, value=5, step=1,
                                                  help="각 룰 조합 시도당 시간. 짧을수록 빠르지만 정확도 낮음.")
            with diag_col2:
                enable_drop_two = st.checkbox("2개 빼기 단계", value=False,
                                               help="단일 룰/1개 빼기로 원인 못 찾으면 2개씩 빼서 시도 (~30회 추가, 시간 많이 소요)")
            with diag_col3:
                est_time = 11 * diag_per_solve + 1 * diag_per_solve + 11 * diag_per_solve
                if enable_drop_two:
                    est_time += 55 * diag_per_solve
                st.caption(f"예상 시간: ~{est_time}초")
            if st.button("🔍 진단 실행", use_container_width=True, type="primary"):
                ii = st.session_state.infeasible_input
                with st.spinner(f"진단 중... 최대 {est_time}초"):
                    from cpsat_solver import diagnose_infeasibility
                    try:
                        diag = diagnose_infeasibility(
                            ii['df_gen'], ii['residents'], ii['resident_leaves'],
                            ii['week_count'], ii['base_date'], ii['holidays'],
                            bogeonso_substitutes=ii['bogeonso_substitutes'],
                            rad_days=ii['rad_days'],
                            student_practices=ii['student_practices'],
                            pain_applicants=ii['pain_applicants'],
                            target_mult_multiplier=ii['auto_mult'],
                            per_solve_time=diag_per_solve,
                            enable_drop_two=enable_drop_two,
                        )
                        st.session_state.last_diagnosis = diag
                    except Exception as e:
                        st.error(f"진단 실패: {e}")
                        st.session_state.last_diagnosis = None
                st.rerun()

            # 진단 결과 표시
            diag = st.session_state.get('last_diagnosis')
            if diag:
                st.markdown("---")
                st.markdown("### 🔍 진단 결과")
                method = diag.get('method', 'unknown')
                note = diag.get('note', '')
                if note:
                    st.info(note)
                blocking = diag.get('blocking_rules', [])
                descs = diag.get('rule_descriptions', {})
                if blocking == ['BASE']:
                    st.error("**기본 슬롯/사람 제약 자체로 INFEASIBLE** — 인원 부족 또는 휴가 과다")
                elif blocking:
                    st.markdown(f"**충돌 룰 ({len(blocking)}개):**")
                    for r in blocking:
                        st.markdown(f"- {descs.get(r, r)}")
                    if method == 'single_rule_block':
                        st.info("→ 각 룰이 단독으로 INFEASIBLE을 유발. 위 룰 중 하나 완화 필요.")
                    elif method == 'drop_one':
                        st.info("→ 위 룰 중 **1개만 빼도 풀이 가능**. 우선순위 낮은 룰 양보 권장.")
                    elif method == 'drop_one_no_result':
                        st.warning("→ 1개씩 빼기로는 원인 못 찾음. **'2개 빼기 단계'** 체크하고 재시도.")
                    elif method == 'drop_two':
                        pair_combos = diag.get('pair_combinations', [])
                        st.markdown("→ **2개 룰을 동시에 빼야 풀이 가능**. 예시 조합:")
                        for p in pair_combos[:3]:
                            st.markdown(f"  · {p[0]} + {p[1]}")
    assign_df = st.session_state.current_df_all.copy()
    assign_df['배정된_전공의'] = assign_df['task_id'].map(lambda x: st.session_state.assignments.get(x, ""))
    res_choices = [""] + [r["이름"] for r in st.session_state.residents]
    edited_assign = st.data_editor(assign_df[['week', 'date', 'day', 'time', 'prof', 'task', '배정된_전공의', 'task_id']], column_config={"task_id": None, "배정된_전공의": st.column_config.SelectboxColumn("배정", options=res_choices)}, use_container_width=True, hide_index=True, height=500)
    if st.button("💾 수동 배정 저장", use_container_width=True):
        st.session_state.assignments = {row['task_id']: row['배정된_전공의'] for _, row in edited_assign.iterrows() if row['배정된_전공의']}; st.success("저장 완료!")

# 탭 인덱스 7 (기존 6): 전공의 개인별
with tabs[7]:
    sorted_res_list = get_sorted_residents(st.session_state.residents)
    task_map = st.session_state.current_df_all.set_index('task_id')['task'].to_dict()
    for i in range(0, len(sorted_res_list), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(sorted_res_list):
                res = sorted_res_list[i + j]; res_name = res['이름']
                with cols[j]:
                    st.markdown(f"#### 👤 {res['연차']} {res_name}")
                    html = "<table style='width:100%; font-size:0.7rem; text-align:center; border-collapse:collapse; table-layout:fixed;'><tr style='background-color:#444; color:white;'><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr>"
                    for w in range(1, st.session_state.week_count + 1):
                        for time in ["오전", "오후"]:
                            html += "<tr>"
                            for d_idx, day in enumerate(["월", "화", "수", "목", "금"]):
                                d_str = (st.session_state.base_date + timedelta(days=(w-1)*7 + d_idx)).strftime("%m-%d")
                                bg, fg, content = "white", "black", ""
                                if d_str in user_holidays: bg, content = "#D3D3D3", "공휴일"
                                else:
                                    a_id = st.session_state.res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get(time)
                                    if a_id:
                                        if any(kw in a_id for kw in ["휴가", "Off"]): bg, fg, content = "#A6A6A6", "white", a_id
                                        elif a_id == "영상": bg, content = "#D5E8D4", a_id
                                        elif any(kw in a_id for kw in ["메인외래", "연보"]): bg, content = "#E8F8F5" if "메인" in a_id else "#FF85FF", a_id
                                        else: content = task_map.get(a_id, a_id); bg, fg = get_task_style(content)
                                    else:
                                        at = [row['task'] for tid, name in st.session_state.assignments.items() if name == res_name for _, row in df_all[df_all['task_id'] == tid].iterrows() if row['date'] == d_str and row['time'] == time]
                                        if at: content = at[0]; bg, fg = get_task_style(content)
                                html += f"<td style='border:1px solid #ddd; padding:3px; vertical-align:top;'><div style='font-size:0.55rem; color:#888; text-align:left;'>{d_str if time=='오전' else '&nbsp;'}</div><div style='background-color:{bg}; color:{fg}; padding:2px; border-radius:3px; min-height:35px; display:flex; align-items:center; justify-content:center; font-weight:bold; line-height:1.1;'>{content}</div></td>"
                            html += "</tr>"
                    st.markdown(html + "</table><br>", unsafe_allow_html=True)

# 탭 인덱스 8 (기존 7): 주차별 전체 현황
with tabs[8]:
    st.subheader("🗓️ 주차별 전공의 전체 스케줄 (Excel 출력 양식)")
    sorted_res_list = get_sorted_residents(st.session_state.residents)
    task_map = st.session_state.current_df_all.set_index('task_id')['task'].to_dict()
    if not sorted_res_list: st.warning("등록된 전공의가 없습니다.")
    else:
        try:
            excel_data = generate_excel_data(st.session_state.week_count, st.session_state.base_date, sorted_res_list, user_holidays, st.session_state.res_daily_slots, st.session_state.assignments, st.session_state.current_df_all, task_map)
            st.download_button(label="📥 이 양식 그대로 엑셀 다운로드", data=excel_data, file_name=f"의국_스케줄_{datetime.today().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        except Exception as e:
            st.error(f"엑셀 생성 중 오류가 발생했습니다: {str(e)}"); st.code(traceback.format_exc())
    for w in range(1, st.session_state.week_count + 1):
        st.markdown(f"#### 📅 {w}주차 현황")
        html = f"<table style='width:100%; font-size:0.8rem; text-align:center; border-collapse:collapse; border: 2px solid #333; table-layout:fixed; font-family:\"맑은 고딕\";'>"
        html += "<tr style='background-color:#F2F2F2;'> <th style='border:1px solid #333; width:6%;'>주차</th> <th style='border:1px solid #333; width:10%;'>성명/역할</th>"
        for d_idx, day_name in enumerate(["월", "화", "수", "목", "금"]):
            dt = st.session_state.base_date + timedelta(days=(w-1)*7 + d_idx)
            html += f"<th style='border:1px solid #333;'>{dt.strftime('%m월 %d일')}({day_name})</th>"
        html += "</tr>"
        prev_group = None
        for res in sorted_res_list:
            res_name = res['이름']; roles = ", ".join(res['역할']) if res['역할'] else "&nbsp;"
            curr_group = "R1/R0" if res['연차'] in ["R1", "R0"] else res['연차']
            is_new_group = prev_group is not None and curr_group != prev_group
            prev_group = curr_group
            top_border = "2px solid #000" if is_new_group else "1px solid #333"
            html += f"<tr>"
            if res == sorted_res_list[0]: html += f"<td rowspan='{len(sorted_res_list)*2}' style='border:1px solid #333; background-color:#fff;'>{w}주차</td>"
            html += f"<td style='border-top:{top_border}; border-left:1px solid #333; border-right:1px solid #333; border-bottom:1px solid #333; font-weight:bold; background-color:#fff;'>{res_name}</td>"
            for d_idx in range(5):
                d_str = (st.session_state.base_date + timedelta(days=(w-1)*7 + d_idx)).strftime("%m-%d")
                am_c, pm_c, am_bg, pm_bg, am_fg, pm_fg = "", "", "white", "white", "black", "black"
                if d_str in user_holidays: am_c = pm_c = "공휴일"; am_bg = pm_bg = "#A6A6A6"
                else:
                    aid = st.session_state.res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오전')
                    if aid:
                        if any(kw in aid for kw in ["휴가", "Off"]): am_c, am_bg, am_fg = aid, "#A6A6A6", "white"
                        elif aid == "영상": am_c, am_bg = aid, "#D5E8D4"
                        elif any(kw in aid for kw in ["메인외래", "연보"]): am_c, am_bg = aid, ("#E8F8F5" if "메인" in aid else "#FF85FF")
                        else: am_c = task_map.get(aid, aid); am_bg, am_fg = get_task_style(am_c)
                    pid = st.session_state.res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오후')
                    if pid:
                        if any(kw in pid for kw in ["휴가", "Off"]): pm_c, pm_bg, pm_fg = pid, "#A6A6A6", "white"
                        elif pid == "영상": pm_c, pm_bg = pid, "#D5E8D4"
                        elif any(kw in pid for kw in ["메인외래", "연보"]): pm_c, pm_bg = pid, ("#E8F8F5" if "메인" in pid else "#FF85FF")
                        else: pm_c = task_map.get(pid, pid); pm_bg, pm_fg = get_task_style(pm_c)
                html += f"<td style='border-top:{top_border}; border-left:1px solid #333; border-right:1px solid #333; border-bottom:1px solid #333; background-color:{am_bg}; color:{am_fg}; font-weight:bold;'>{am_c}</td>"
            html += "</tr>"
            html += f"<tr><td style='border:1px solid #333; font-size:0.7rem; background-color:#fff;'>{roles}</td>"
            for d_idx in range(5):
                d_str = (st.session_state.base_date + timedelta(days=(w-1)*7 + d_idx)).strftime("%m-%d")
                am_c, pm_c, pm_bg, pm_fg = "", "", "white", "black"
                if d_str in user_holidays: am_c = pm_c = "공휴일"; pm_bg = "#A6A6A6"
                else:
                    aid = st.session_state.res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오전')
                    pid = st.session_state.res_daily_slots.get(res_name, {}).get('daily_slots', {}).get(d_str, {}).get('오후')
                    if aid: am_c = task_map.get(aid, aid) if aid not in ["휴가","Off","메인외래","연보","영상"] else aid
                    if pid:
                        if any(kw in pid for kw in ["휴가", "Off"]): pm_c, pm_bg, pm_fg = pid, "#A6A6A6", "white"
                        elif pid == "영상": pm_c, pm_bg = pid, "#D5E8D4"
                        elif any(kw in pid for kw in ["메인외래", "연보"]): pm_c, pm_bg = pid, ("#E8F8F5" if "메인" in pid else "#FF85FF")
                        else: pm_c = task_map.get(pid, pid); pm_bg, pm_fg = get_task_style(pm_c)
                html += f"<td style='border:1px solid #333; background-color:{pm_bg}; color:{pm_fg}; font-weight:bold;'>{pm_c}</td>"
            html += "</tr>"
        html += "</table><br>"
        st.write(html, unsafe_allow_html=True)

# 탭 인덱스 1 (기존 0): 교수별 시간표
with tabs[1]:
    for i in range(0, len(PROF_ORDER), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(PROF_ORDER):
                p_name = PROF_ORDER[i+j]
                with cols[j]:
                    st.markdown(f"#### 🏥 Pf. {p_name}")
                    h = "<table style='width:100%; font-size:0.75rem; text-align:center; border-collapse:collapse; table-layout:fixed;'><tr style='background-color:#333; color:white;'><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr>"
                    for w in range(1, st.session_state.week_count + 1):
                        for time in ["오전", "오후"]:
                            h += "<tr>"
                            for d_idx, day in enumerate(["월", "화", "수", "목", "금"]):
                                d_str = (st.session_state.base_date + timedelta(days=(w-1)*7 + d_idx)).strftime("%m-%d")
                                is_h, is_o = d_str in user_holidays, (p_name, d_str) in st.session_state.off_slots
                                ci = ""
                                for _, r in st.session_state.master_schedules.iterrows():
                                    # 빈 셀 방어 로직
                                    if pd.isna(r["교수명"]): continue
                                    if r["교수명"] == p_name and r["요일"] == day and r["시간"] == time:
                                        if (r["주기"]=="매주") or (r["주기"]=="홀수주" and w%2!=0) or (r["주기"]=="짝수주" and w%2==0): ci = r["진료명"]
                                # 보충진료 확인 (마스터에 없는 추가 진료)
                                if not ci:
                                    for s in st.session_state.supplementary_schedules:
                                        if s["교수"] == p_name and s["날짜"] == d_str and s["시간"] == time:
                                            ci = s["진료명"]
                                            break
                                bg, fg, bd = get_prof_raw_style(ci, is_o, is_h, False)
                                h += f"<td style='border:1px solid #ddd; padding:4px; vertical-align:top;'><div style='height:14px; font-size:0.6rem; color:#888; text-align:left;'>{d_str if time=='오전' else '&nbsp;'}</div><div style='background-color:{bg}; color:{fg}; padding:2px; border-radius:3px; min-height:38px; display:flex; align-items:center; justify-content:center; border:{bd}; font-weight:bold;'>{is_h and '공휴일' or (is_o and '휴진' or ci)}</div></td>"
                            h += "</tr>"
                    st.write(h + "</table><br>", unsafe_allow_html=True)

# 탭 인덱스 2 (기존 1): 주차별 가이드
with tabs[2]:
    for w in range(1, st.session_state.week_count + 1):
        st.subheader(f"📍 {w}주차")
        w_df = st.session_state.current_df_all[st.session_state.current_df_all['week'] == w]; cols = st.columns(5)
        for i, day in enumerate(["월", "화", "수", "목", "금"]):
            with cols[i]:
                st.markdown(f"<div style='text-align:center; font-weight:bold; border-bottom:2px solid black;'>{day}요일</div>", unsafe_allow_html=True)
                for t in ["오전", "오후"]:
                    st.markdown(f"<div style='background-color:#F2F2F2; padding:2px; font-size:0.7rem; font-weight:bold; text-align:center; margin-top:5px;'>{t}</div>", unsafe_allow_html=True)
                    tasks = w_df[(w_df['day'] == day) & (w_df['time'] == t)]
                    for _, row in tasks.iterrows():
                        bg, fg = get_task_style(row['task']); assignee = st.session_state.assignments.get(row['task_id'], "")
                        st.markdown(f"<div style='background-color:{bg}; color:{fg}; padding:3px; border-radius:3px; margin-bottom:2px; border:1px solid #ddd; font-size:0.7rem;'>{row['task']} <b>({assignee})</b></div>" if assignee else f"<div style='background-color:{bg}; color:{fg}; padding:3px; border-radius:3px; margin-bottom:2px; border:1px solid #ddd; font-size:0.7rem;'>{row['task']}</div>", unsafe_allow_html=True)

# 탭 인덱스 3 (기존 2): 규칙 설정 (수정된 st.form 적용 완료)
with tabs[3]:
    with st.form("master_schedule_form"):
        edited_df = st.data_editor(
            st.session_state.master_schedules,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic"
        )
        submitted = st.form_submit_button("🔄 규칙 적용")
        if submitted:
            st.session_state.master_schedules = edited_df
            user_holidays = [h.strip() for h in st.session_state.user_holidays_str.split(',') if h.strip()]
            st.session_state.current_df_all = generate_schedule(
                st.session_state.base_date,
                st.session_state.week_count,
                user_holidays,
                st.session_state.master_schedules,
                st.session_state.off_slots,
                supplementary_schedules=st.session_state.supplementary_schedules
            )
            st.rerun()

# 탭 인덱스 9: 스케줄 검증
with tabs[9]:
    st.subheader("✅ 스케줄 검증")
    st.caption("정답 목록과 실제 생성된 스케줄을 비교합니다. 공휴일/교수 휴진으로 인한 누락은 자동으로 사유를 표시합니다.")

    if st.session_state.current_df_all.empty:
        st.warning("먼저 사이드바에서 '설정 및 공휴일 확정 적용'을 눌러 스케줄을 생성해주세요.")
    else:
        try:
            verify_result = verify_schedule(
                st.session_state.current_df_all,
                st.session_state.week_count,
                st.session_state.base_date,
                user_holidays,
                st.session_state.off_slots,
                supplementary_schedules=st.session_state.supplementary_schedules,
                assignments=st.session_state.assignments,
                task_date_overrides=st.session_state.get("cpsat_task_date_overrides", {}),
                task_time_overrides=st.session_state.get("cpsat_task_time_overrides", {}),
                shifted_tasks=st.session_state.get("cpsat_shifted_tasks", []),
                original_df_dates=st.session_state.get("cpsat_original_df_dates", {}),
            )

            # 전체 요약
            total_days = 0
            clean_days = 0
            total_missing_real = 0  # 사유 없는 진짜 누락
            total_missing_explained = 0  # 사유 있는 누락
            total_extra_real = 0  # 사유 없는 진짜 추가
            total_extra_explained = 0  # 보충진료 등 사유 있는 추가
            total_unassigned = 0  # 미배정 task 수
            for week_num, days in verify_result.items():
                for day_name, r in days.items():
                    total_days += 1
                    if not r['missing'] and not r['extra'] and not r['unassigned']:
                        clean_days += 1
                    for m in r['missing']:
                        if m['reason']:
                            total_missing_explained += 1
                        else:
                            total_missing_real += 1
                    for e in r['extra']:
                        if e['reason']:
                            total_extra_explained += 1
                        else:
                            total_extra_real += 1
                    total_unassigned += len(r['unassigned'])

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("정상 일수", f"{clean_days}/{total_days}")
            c2.metric("진짜 누락", total_missing_real)
            c3.metric("사유 있는 누락", total_missing_explained)
            c4.metric("추가된 항목", f"{total_extra_real} (+{total_extra_explained})", help="앞: 사유 없는 진짜 추가 / 괄호: 보충진료 등 사유 있는 추가")
            c5.metric("🚨 미배정 task", total_unassigned, help="task는 생성됐으나 자동/수동 배정에서 빠진 task. 절대원칙 위반: '모든 task는 빠짐없이 배정' + '한 세션 1 task'")

            if total_unassigned > 0:
                st.error(f"🚨 **미배정 task가 {total_unassigned}개 있습니다.** 슬롯 부족으로 배정되지 못한 task입니다. 절대원칙 위반 — 수동 배정이 필요합니다.")
            if total_missing_real == 0 and total_extra_real == 0 and total_unassigned == 0:
                st.success(f"🎉 검증 결과: 모든 항목이 정답 목록과 일치하고 미배정도 없습니다! (사유 있는 누락 {total_missing_explained}건, 사유 있는 추가 {total_extra_explained}건은 정상 동작)")
            elif total_missing_real == 0 and total_unassigned == 0:
                st.info(f"ℹ️ 진짜 누락/미배정은 없지만, 정답 목록에 없는 항목이 {total_extra_real}개 추가되어 있습니다. (이동된 task일 가능성 있음)")
            elif total_missing_real > 0:
                st.error(f"❌ 정답 목록에 있어야 하는데 사유 없이 누락된 항목이 {total_missing_real}개 있습니다.")

            st.markdown("---")

            # === [신규] 미배정 task 별도 섹션 (가장 먼저, 가장 눈에 띄게) ===
            if total_unassigned > 0:
                st.markdown("### 🚨 미배정 task 목록")
                st.caption("아래 task들은 스케줄에는 생성되었지만 배정받은 전공의가 없습니다. 스케줄 배정 탭에서 수동으로 배정해주세요.")
                for week_num in sorted(verify_result.keys()):
                    week_has_unassigned = False
                    for day_name in ["월", "화", "수", "목", "금"]:
                        if verify_result[week_num][day_name]['unassigned']:
                            week_has_unassigned = True
                            break
                    if not week_has_unassigned:
                        continue
                    st.markdown(f"**📅 {week_num}주차**")
                    for day_name in ["월", "화", "수", "목", "금"]:
                        r = verify_result[week_num][day_name]
                        if r['unassigned']:
                            st.markdown(f"<div style='padding:6px 10px; margin:4px 0; background:#FDF2F2; border-left:4px solid #c0392b; border-radius:3px;'><b>{day_name}요일 ({r['date']})</b> — 미배정 {len(r['unassigned'])}개</div>", unsafe_allow_html=True)
                            for t in r['unassigned']:
                                st.markdown(f"<div style='margin-left:40px; color:#c0392b;'>🚨 {t}</div>", unsafe_allow_html=True)
                st.markdown("---")

            # 주차별 상세
            st.markdown("### 📋 주차별 상세 (누락/추가)")
            for week_num in sorted(verify_result.keys()):
                with st.expander(f"📅 {week_num}주차 상세", expanded=(total_missing_real > 0 or total_extra_real > 0)):
                    for day_name in ["월", "화", "수", "목", "금"]:
                        r = verify_result[week_num][day_name]
                        has_real_missing = any(m['reason'] is None for m in r['missing'])
                        has_real_extra = any(e['reason'] is None for e in r['extra'])
                        has_extra = len(r['extra']) > 0

                        if not r['missing'] and not has_extra and not r.get('moved_in') and not r.get('moved_out'):
                            st.markdown(f"<div style='padding:6px 10px; margin:4px 0; background:#E8F8F5; border-left:4px solid #1abc9c; border-radius:3px;'>✅ <b>{day_name}요일 ({r['date']})</b> — 정답 {r['total_expected']}개 / 실제 {r['total_present']}개, 모두 일치</div>", unsafe_allow_html=True)
                        else:
                            border_color = "#e74c3c" if has_real_missing else ("#f39c12" if has_real_extra else "#95a5a6")
                            st.markdown(f"<div style='padding:6px 10px; margin:4px 0; background:#FDF2F2; border-left:4px solid {border_color}; border-radius:3px;'><b>{day_name}요일 ({r['date']})</b> — 정답 {r['total_expected']}개 / 실제 {r['total_present']}개</div>", unsafe_allow_html=True)

                            # 진짜 누락 (사유 없음)
                            real_missing = [m for m in r['missing'] if not m['reason']]
                            if real_missing:
                                st.markdown(f"<div style='margin-left:20px; color:#c0392b;'>❌ <b>진짜 누락 ({len(real_missing)}개) — 확인 필요</b></div>", unsafe_allow_html=True)
                                for m in real_missing:
                                    st.markdown(f"<div style='margin-left:40px; color:#c0392b;'>- {m['name']}</div>", unsafe_allow_html=True)

                            # 사유 있는 누락
                            explained_missing = [m for m in r['missing'] if m['reason']]
                            if explained_missing:
                                st.markdown(f"<div style='margin-left:20px; color:#7f8c8d;'>ℹ️ 사유 있는 누락 ({len(explained_missing)}개)</div>", unsafe_allow_html=True)
                                for m in explained_missing:
                                    st.markdown(f"<div style='margin-left:40px; color:#7f8c8d;'>- {m['name']} → <i>{m['reason']}</i></div>", unsafe_allow_html=True)

                            # 진짜 추가 (사유 없음)
                            real_extra = [e for e in r['extra'] if not e['reason']]
                            if real_extra:
                                st.markdown(f"<div style='margin-left:20px; color:#d68910;'>⚠️ 추가된 항목 ({len(real_extra)}개) — 정답 목록에 없음 (이동/추적 안됨)</div>", unsafe_allow_html=True)
                                for e in real_extra:
                                    st.markdown(f"<div style='margin-left:40px; color:#d68910;'>+ {e['name']}</div>", unsafe_allow_html=True)

                            # 사유 있는 추가 (보충진료 등)
                            explained_extra = [e for e in r['extra'] if e['reason']]
                            if explained_extra:
                                st.markdown(f"<div style='margin-left:20px; color:#7f8c8d;'>ℹ️ 사유 있는 추가 ({len(explained_extra)}개)</div>", unsafe_allow_html=True)
                                for e in explained_extra:
                                    st.markdown(f"<div style='margin-left:40px; color:#7f8c8d;'>+ {e['name']} → <i>{e['reason']}</i></div>", unsafe_allow_html=True)

                            # 🔄 이동 들어옴 (다른 날짜에서 이 날짜로 옴)
                            moved_in = r.get('moved_in', [])
                            if moved_in:
                                st.markdown(f"<div style='margin-left:20px; color:#2980b9;'>🔄 다른 날짜에서 이동 들어옴 ({len(moved_in)}개)</div>", unsafe_allow_html=True)
                                for mi in moved_in:
                                    from_info = f"{mi['from_day']}요일" + (f" ({mi['from_date']})" if mi['from_date'] else "")
                                    st.markdown(f"<div style='margin-left:40px; color:#2980b9;'>← {mi['name']} (원래 {from_info}) — <i>{mi['reason']}</i></div>", unsafe_allow_html=True)

                            # 🔄 이동 나감 (이 날짜에서 다른 날짜로 감)
                            moved_out = r.get('moved_out', [])
                            if moved_out:
                                st.markdown(f"<div style='margin-left:20px; color:#16a085;'>🔄 다른 날짜로 이동 나감 ({len(moved_out)}개)</div>", unsafe_allow_html=True)
                                for mo in moved_out:
                                    to_info = f"{mo['to_day']}요일" + (f" ({mo['to_date']})" if mo['to_date'] else "")
                                    st.markdown(f"<div style='margin-left:40px; color:#16a085;'>→ {mo['name']} (→ {to_info}) — <i>{mo['reason']}</i></div>", unsafe_allow_html=True)
        except Exception as e:
            import traceback
            st.error(f"검증 중 오류 발생: {str(e)}")
            st.code(traceback.format_exc())