"""
CP-SAT (OR-Tools) 기반 의국 스케줄 자동 배정 솔버.

모든 룰 H1~H20 + S5(목적함수)를 수학적 제약으로 정의하여 OR-Tools CP-SAT 솔버로 정확한 해를 찾는다.

룰 명세 (사용자 합의):
  H1.  한 task = 정확히 1명 또는 미배정
  H2.  한 사람 한 세션 = task 1개
  H3.  보건소 담당자: 매주 월~금 오전 연보, 화/목 오후 연보 고정. 그 외 X
  H3-1. 보건소 휴가 시 bogeonso_substitutes 대체자 강제 배정
  H4.  영상 파견자: 1주일에 조비룡 또는 박민선 클리닉 차리/판정 1개. 그 외 X
  H5.  휴가/공휴일/메인외래/학생실습/영상파견 슬롯에 task 안 받음
  H6.  R3 본인 메인외래 요일에 일반 task X (H5에 포함)
  H7.  시간 고정 task: 조수환 건증 판정(오전), 모든 참관/처치/예진
       비고정 task: 차리, 건증 판정 (조수환 제외), 클리닉 차리/판정 등 → 오전/오후 자유
  H8.  R3 (영상 제외) 일반 판정 = 정확히 1개 (클리닉 차리/판정는 카운트 X)
  H8b. R3 (영상 제외) 판정 참관 = 정확히 1개
  H8c. R3의 판정(H8)과 판정참관(H8b)은 반드시 같은 묶음 (단독 판정/참관 금지)
  H9.  R0 + R1 의국처음 = 처치 X
  H10. 조비룡/박민선 외래 차리/참관, 예진 = R3만
  H11. Pairing 묶음 = 같은 사람 (건증·박진호 묶음은 절대 안 깸, 그 외 최대 5개까지 깨도 OK)
  H12. 처치(오전), 처치(오후)의 90% 이상 = R3 + R2
  H13. 박진호 통증클리닉 사전 신청자 우선 (신청자 중 1명에게 무조건)
  H14. R1 처치 최대 1개
  H15. 로딩 범위: 의국/교육 4.9~5.5, 학생/진료 6~7, 일반R3 6.5~7.3, R2 7.3~8, R1/R0 8~9
  H16. 그룹 내부 max-min ≤ 0.3
  H17. strict 부등호 chain: max(의국/교육) < min(학생/진료) < min(일반R3) < min(R2) < min(R1/R0)
  H18. R2 주당 판정 ~1, R1/R0 주당 판정 ~1, ±1~2 변동 허용 + 결과 표시
  H19. R3 (영상 제외) 클리닉 차리/판정 후순위 (영상 못 받은 경우만)
  H20. 빈 슬롯 < task 수 → pairing 없는 task 우선 미배정
  H21. 같은 연차 내 판정 수 max-min ≤ 2
  H22. 보건소 직전휴가로 대체된 연보 세션 수만큼 처치(오후) 배정
  S5.  교수 중복 최소화 (목적함수)
  설정값: 깨도 되는 pairing 수(max_broken_pairs, 기본 5), 차리/판정 추가 -1 이동 허용 수(extra_shift_allowance, 기본 0)

사전 진단: 해 못 찾으면 target_mult 배율 자동 상향 (1.0 → 1.5)
배율 1.5에서도 infeasible → "해가 없습니다" 알림
"""

from datetime import datetime, timedelta
import math
from ortools.sat.python import cp_model


# ============================================================
# 헬퍼 함수
# ============================================================

def _is_fixed_time_task(task_name):
    """H7: 이 task가 시간 고정 (오전/오후 변경 불가)인가?"""
    if "조수환" in task_name and "판정" in task_name:
        return True
    return any(kw in task_name for kw in ["참관", "처치", "예진"])


def _is_panjung_task(task_name):
    """일반 판정 task (참관 제외)"""
    return "판정" in task_name and "참관" not in task_name


def _is_panjung_obs_task(task_name):
    """판정 참관 task (예: 'Pf. ... 판정 참관 (오전)')"""
    return "판정" in task_name and "참관" in task_name


def _is_clinic_panjung_chari(task_name):
    """조비룡/박민선 클리닉 차리/판정 묶음"""
    return (any(p in task_name for p in ["조비룡", "박민선"])
            and "클리닉" in task_name and "차리/판정" in task_name)


def _is_r3_only_task(task_name):
    """H10: R3만 받을 수 있는 task (조비룡/박민선 외래 차리/참관, 예진)"""
    if "예진" in task_name:
        return True
    if (any(p in task_name for p in ["조비룡", "박민선"])
            and any(kw in task_name for kw in ["외래 참관", "외래 차리"])):
        return True
    return False


def _is_tx_task(task_name):
    """처치 task"""
    return "처치" in task_name


def _is_pain_clinic_task(task_name):
    """박진호 통증클리닉 차리/참관"""
    return "박진호" in task_name and "통증클리닉" in task_name


def _extract_prof(task_name):
    """task에서 교수명 추출"""
    if not task_name.startswith("Pf."):
        return None
    parts = task_name.split(" ", 2)
    if len(parts) >= 2:
        return parts[1]
    return None


def get_resident_target_mult(resident):
    """전공의의 기본 target_mult (사용자 의도 기준 로딩)"""
    year = resident['연차']
    roles = resident.get('역할', [])
    if year == "R3":
        if "의국수석" in roles or "교육수석" in roles: return 5.5
        elif "학생수석" in roles or "진료수석" in roles: return 6.5
        else: return 7.0
    elif year == "R2": return 7.8
    elif year == "R1": return 8.5
    else: return 8.5  # R0


def get_loading_group(resident, rad_days_dict):
    """전공의가 속한 로딩 그룹.
    0: 의국/교육수석 R3
    1: 학생/진료수석 R3
    2: 일반 R3 (영상 파견자 제외)
    3: R2 (보건소 제외)
    4: R1/R0
    -1: 보건소/영상 파견자 (룰 적용 X)
    """
    roles = resident.get('역할', [])
    name = resident['이름']
    if "연건 보건소" in roles: return -1
    if "본원 영상" in roles and rad_days_dict.get(name): return -1
    yr = resident['연차']
    if yr == "R3":
        if "의국수석" in roles or "교육수석" in roles: return 0
        if "학생수석" in roles or "진료수석" in roles: return 1
        return 2
    if yr == "R2": return 3
    if yr in ["R1", "R0"]: return 4
    return -1


# 로딩 범위 (target_mult_multiplier 적용 전 기본값)
# 사용자 정의: 각 그룹 사이 겹치지 않게 정의 → strict < 부등호 자연스럽게 만족
LOADING_RANGES = {
    0: (4.9, 5.5),   # 의국/교육수석
    1: (6.3, 6.8),   # 학생/진료수석
    2: (6.5, 7.2),   # 일반 R3
    3: (7.3, 7.9),   # R2
    4: (8.0, 9.0),   # R1/R0
}


# ============================================================
# 데이터 빌드
# ============================================================

def build_problem_data(df_all, residents, leaves, week_count, start_date, holidays,
                       bogeonso_substitutes=None, rad_days=None, student_practices=None,
                       pain_applicants=None, shift_allowed_tids=None):
    """UI 입력을 CP-SAT 모델 입력으로 변환.
    
    shift_allowed_tids: set of task_id.
        그 task가 차리/판정이면 -1 평일 이동 옵션 추가.
        (참관은 절대 고정이므로 set에 있어도 무시)
    """
    if bogeonso_substitutes is None: bogeonso_substitutes = {}
    if rad_days is None: rad_days = {}
    if student_practices is None: student_practices = []
    if pain_applicants is None: pain_applicants = []
    if shift_allowed_tids is None: shift_allowed_tids = set()

    weekday_to_idx = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}

    def prev_weekday(date_str):
        """주어진 MM-DD의 -1 평일 (월요일 → 직전 금요일). holidays 건너뜀.
        반환: 'MM-DD' 또는 None (week_count 범위 밖이면)."""
        try:
            dt = datetime.strptime(f"{start_date.year}-{date_str}", "%Y-%m-%d").date()
        except Exception:
            return None
        curr = dt
        for _ in range(7):
            curr = curr - timedelta(days=1)
            if curr.weekday() < 5 and curr.strftime("%m-%d") not in holidays:
                first_date = start_date
                last_date = start_date + timedelta(days=week_count * 7 - 1)
                if first_date <= curr <= last_date:
                    return curr.strftime("%m-%d")
                return None
        return None

    def _is_chari_or_panjung(task_name):
        if "참관" in task_name: return False
        if "차리" in task_name: return True
        if "판정" in task_name: return True
        return False

    tasks = []
    for idx, row in df_all.iterrows():
        t = {
            'task_id': row['task_id'],
            'week': int(row['week']),
            'date': row['date'],
            'day': row['day'],
            'time': row['time'],
            'prof': row['prof'],
            'task': row['task'],
            'pair_id': row.get('pair_id', '') or '',
            'date_alt': None,
        }
        # shift_allowed_tids에 있는 차리/판정 task만 -1 평일 이동 옵션
        if row['task_id'] in shift_allowed_tids and _is_chari_or_panjung(row['task']):
            alt = prev_weekday(row['date'])
            if alt is not None:
                t['date_alt'] = alt
        tasks.append(t)

    sessions = []
    for w in range(week_count):
        for d_idx in range(5):
            dt = start_date + timedelta(days=w * 7 + d_idx)
            date_str = dt.strftime("%m-%d")
            if date_str in holidays:
                continue
            sessions.append((date_str, "오전"))
            sessions.append((date_str, "오후"))

    persons = []
    for r in residents:
        roles = r.get('역할', [])
        persons.append({
            'name': r['이름'],
            'year': r['연차'],
            'roles': roles,
            'main_clinic': r.get('메인외래', '선택안함'),
            'rad_days': rad_days.get(r['이름'], []),
            'is_bogeonso': "연건 보건소" in roles,
            'is_rad': "본원 영상" in roles and bool(rad_days.get(r['이름'])),
            'is_rookie': "의국 처음" in roles or r['연차'] == "R0",
            'group': get_loading_group(r, rad_days),
        })

    # blocked: 본인이 그 슬롯에 task 받을 수 없는 (person, date, time) 집합
    blocked = set()
    person_avail_sessions = {}  # {name: 사용 가능한 세션 수}
    # 사람별 메인외래/학생실습/영상 슬롯 추적 (forced_assignments용)
    person_main_slots = {}  # {name: [(date, time, label)]}
    person_sp_slots = {}    # {name: [(date, time, label)]}
    person_rad_slots = {}   # {name: [(date, time, label)]}

    for p in persons:
        name = p['name']
        # 총 세션 = 5일 × 주 × 2 (공휴일 제외)
        total = 0
        for w in range(week_count):
            for d_idx in range(5):
                dt = start_date + timedelta(days=w * 7 + d_idx)
                ds = dt.strftime("%m-%d")
                if ds not in holidays:
                    total += 2

        # 휴가
        leave_dates = set()
        denom_leave_dates = set()  # 분모(avail) 차감 대상. '직전휴가'는 제외(분모에서 빼지 않음)
        for l in leaves:
            if l['이름'] == name:
                blocked.add((name, l['날짜'], '오전'))
                blocked.add((name, l['날짜'], '오후'))
                leave_dates.add(l['날짜'])
                if l.get('종류') != '직전휴가':
                    denom_leave_dates.add(l['날짜'])

        # 메인외래 (R3) - 일하는 슬롯. 다른 task 못 받지만 분자/분모에 포함
        main_slots = []
        main = p['main_clinic']
        if main != '선택안함' and main in weekday_to_idx:
            d_idx = weekday_to_idx[main]
            for w in range(week_count):
                dt = start_date + timedelta(days=w * 7 + d_idx)
                ds = dt.strftime("%m-%d")
                if ds not in holidays and ds not in leave_dates:
                    # 휴가가 아니면 메인외래로 차있음 (휴가가 더 우선)
                    blocked.add((name, ds, '오전'))
                    blocked.add((name, ds, '오후'))
                    main_slots.append((ds, '오전', '메인외래'))
                    main_slots.append((ds, '오후', '메인외래'))
        person_main_slots[name] = main_slots

        # 학생실습 - 일하는 슬롯
        sp_slots = []
        for sp in student_practices:
            if sp['이름'] == name and sp['날짜'] not in holidays and sp['날짜'] not in leave_dates:
                # 메인외래에 이미 차있으면 학생실습이 아닌 메인외래 우선 (학생실습은 메인외래일 X)
                key = (name, sp['날짜'], sp['시간'])
                if key not in blocked or key in [(name, s[0], s[1]) for s in main_slots]:
                    # 메인외래도 아닌 경우만 (또는 메인외래 슬롯에 학생실습이 별개로 들어오면 학생실습으로 덮어씀)
                    if key not in [(name, s[0], s[1]) for s in main_slots]:
                        blocked.add(key)
                        sp_slots.append((sp['날짜'], sp['시간'], '학생실습'))
        person_sp_slots[name] = sp_slots

        # 영상 파견 요일 - 일하는 슬롯
        rad_slots = []
        for rd in p['rad_days']:
            if rd in weekday_to_idx:
                d_idx = weekday_to_idx[rd]
                for w in range(week_count):
                    dt = start_date + timedelta(days=w * 7 + d_idx)
                    ds = dt.strftime("%m-%d")
                    if ds not in holidays and ds not in leave_dates:
                        blocked.add((name, ds, '오전'))
                        blocked.add((name, ds, '오후'))
                        rad_slots.append((ds, '오전', '영상'))
                        rad_slots.append((ds, '오후', '영상'))
        person_rad_slots[name] = rad_slots

        # 사용 가능한 세션 수 (분모)
        # 휴가/공휴일만 차감. 메인외래/학생실습/영상은 "일하는 슬롯"이므로 분모에 포함됨.
        # 단, '직전휴가'는 분모에서 차감하지 않음 (denom_leave_dates에 미포함).
        leave_count = 0
        for ld in denom_leave_dates:
            if ld not in holidays:
                leave_count += 2
        avail = max(1, total - leave_count)
        person_avail_sessions[name] = avail

    # ===== 연보 강제 배정 (forced_assignments) =====
    # 구조: {(person_name, date, time): label} — label은 '연보(오전)' 또는 '연보(오후)'
    # 이 슬롯들은 blocked에 추가되어 다른 task 못 받음
    # 로딩 분자(person_forced_count)에 별도 카운트
    forced_assignments = {}

    # 1) 보건소 담당자: 매주 월~금 오전 연보 + 화/목 오후 연보
    #    (단, 휴가/공휴일 제외)
    for p in persons:
        if not p['is_bogeonso']:
            continue
        name = p['name']
        for w in range(week_count):
            for d_idx in range(5):
                dt = start_date + timedelta(days=w * 7 + d_idx)
                ds = dt.strftime("%m-%d")
                if ds in holidays:
                    continue
                # 오전 연보 (월~금 모두)
                if (name, ds, '오전') not in blocked:  # 휴가 아니면
                    forced_assignments[(name, ds, '오전')] = '연보(오전)'
                # 오후 연보 (화/목만)
                if d_idx in [1, 3] and (name, ds, '오후') not in blocked:
                    forced_assignments[(name, ds, '오후')] = '연보(오후)'

    # 2) 대체자 (bogeonso_substitutes): 보건소 휴가일에 지정 대체자에게 연보 강제 배정
    #    bogeonso_substitutes 형식: {'MM-DD': [name1, name2, ...]}
    #    대체자 여러 명이면 라운드로빈으로 슬롯 분배
    bogeonso_leave_dates = set()
    for bp in persons:
        if not bp['is_bogeonso']:
            continue
        for l in leaves:
            if l['이름'] == bp['name']:
                bogeonso_leave_dates.add(l['날짜'])

    for d_str, sub_list in bogeonso_substitutes.items():
        if not sub_list:
            continue
        if d_str in holidays:
            continue
        if d_str not in bogeonso_leave_dates:
            continue
        # 이 날짜의 요일 확인
        try:
            wd = datetime.strptime(f"{start_date.year}-{d_str}", "%Y-%m-%d").weekday()
        except Exception:
            continue
        # 어떤 슬롯이 연보? 월~금 오전 + 화/목 오후
        target_slots = ['오전']
        if wd in [1, 3]:  # 화/목
            target_slots.append('오후')

        valid_subs = [s for s in sub_list if any(p['name'] == s for p in persons)]
        if not valid_subs:
            continue

        # 라운드로빈으로 슬롯 분배
        rr_idx = 0
        for slot_time in target_slots:
            for tries in range(len(valid_subs)):
                sub_name = valid_subs[(rr_idx + tries) % len(valid_subs)]
                # 그 대체자가 그 슬롯에 다른 (휴가 등) 일정 없으면 강제 배정
                if (sub_name, d_str, slot_time) not in blocked and \
                   (sub_name, d_str, slot_time) not in forced_assignments:
                    label = f'연보({slot_time})'
                    forced_assignments[(sub_name, d_str, slot_time)] = label
                    rr_idx = (rr_idx + tries + 1) % len(valid_subs)
                    break

    # 3) 메인외래/학생실습/영상 파견 — 모두 "일하는 슬롯" → forced_assignments에 포함
    #    (이미 blocked에는 들어가 있음. label만 추가해서 로딩 분자에 카운트되고 UI 표시도 됨)
    for name, slots in person_main_slots.items():
        for ds, tm, label in slots:
            if (name, ds, tm) not in forced_assignments:  # 연보가 우선 (보건소가 메인외래 동시일 수는 없지만 안전)
                forced_assignments[(name, ds, tm)] = label
    for name, slots in person_sp_slots.items():
        for ds, tm, label in slots:
            if (name, ds, tm) not in forced_assignments:
                forced_assignments[(name, ds, tm)] = label
    for name, slots in person_rad_slots.items():
        for ds, tm, label in slots:
            if (name, ds, tm) not in forced_assignments:
                forced_assignments[(name, ds, tm)] = label

    # 4) forced_assignments 슬롯을 blocked에 추가 (다른 task 못 받음)
    for key in forced_assignments:
        blocked.add(key)

    # 5) 사람별 강제 배정 카운트 (로딩 분자에 포함됨)
    person_forced_count = {}
    for (pname, _, _), _ in forced_assignments.items():
        person_forced_count[pname] = person_forced_count.get(pname, 0) + 1

    # 6) 보건소 직전휴가 보충: 직전휴가로 '대체자가 지정되어' 대체된 연보 세션 수만큼
    #    그 보건소 담당자에게 처치(오후)를 배정 (H22). 세션 = 오전(항상) + 화/목 오후
    bogeonso_jikjeon_makeup = {}
    for p in persons:
        if not p['is_bogeonso']:
            continue
        name = p['name']
        n = 0
        for l in leaves:
            if l['이름'] != name or l.get('종류') != '직전휴가':
                continue
            ds = l['날짜']
            if ds in holidays:
                continue
            if not bogeonso_substitutes.get(ds):  # 대체자 지정된 날짜만 ('다른사람이 대체')
                continue
            n += 1  # 오전 연보
            try:
                wd = datetime.strptime(f"{start_date.year}-{ds}", "%Y-%m-%d").weekday()
                if wd in (1, 3):  # 화/목
                    n += 1  # 오후 연보
            except Exception:
                pass
        if n > 0:
            bogeonso_jikjeon_makeup[name] = n

    return {
        'tasks': tasks,
        'persons': persons,
        'sessions': sessions,
        'blocked': blocked,
        'person_avail_sessions': person_avail_sessions,
        'person_forced_count': person_forced_count,
        'forced_assignments': forced_assignments,
        'holidays': holidays,
        'week_count': week_count,
        'start_date': start_date,
        'residents': residents,
        'bogeonso_substitutes': bogeonso_substitutes,
        'rad_days': rad_days,
        'student_practices': student_practices,
        'pain_applicants': pain_applicants,
        'bogeonso_jikjeon_makeup': bogeonso_jikjeon_makeup,
    }


# ============================================================
# CP-SAT 모델 클래스
# ============================================================

class CPSATScheduleSolver:
    """
    CP-SAT 모델 빌더 + 솔버.
    
    사용:
        solver = CPSATScheduleSolver(problem_data, target_mult_multiplier=1.0)
        solver.build_model()
        result = solver.solve(time_limit_sec=60)
    """

    def __init__(self, problem_data, target_mult_multiplier=1.0, loading_ranges=None, h17_ops=None,
                 max_broken_pairs=5, shortage_shift_tids=None, extra_shift_limit=0):
        self.data = problem_data
        self.target_mult_multiplier = target_mult_multiplier
        # 로딩 범위 (그룹 0~4의 (하한, 상한)). None이면 모듈 기본값 LOADING_RANGES 사용.
        self.loading_ranges = {g: tuple(loading_ranges[g]) for g in range(5)} if loading_ranges else dict(LOADING_RANGES)
        # H17 부등호: 인접 그룹 경계 0~3의 연산자 ('<', '<=', '='). None이면 모두 '<' (strict).
        self.h17_ops = dict(h17_ops) if h17_ops else {0: '<', 1: '<', 2: '<', 3: '<'}
        # H11: 깨도 되는 pairing 최대 개수 (건증/박진호 묶음은 별도로 항상 보호)
        self.max_broken_pairs = max_broken_pairs
        # 차리/판정 -1 이동: 슬롯부족(shortage)으로 허용된 task는 무제한, 그 외 추가 이동은 extra_shift_limit개까지
        self.shortage_shift_tids = set(shortage_shift_tids) if shortage_shift_tids else set()
        self.extra_shift_limit = extra_shift_limit
        self.model = cp_model.CpModel()
        self.tasks = problem_data['tasks']
        self.persons = problem_data['persons']
        self.sessions = problem_data['sessions']
        self.blocked = problem_data['blocked']
        self.person_avail_sessions = problem_data['person_avail_sessions']

        # 변수 저장소
        # x[task_id, person_name] = 1 if person 가 task 받음
        self.x = {}
        # u[task_id] = 1 if task가 미배정
        self.u = {}
        # time_choice[task_id] = 'fixed' or BoolVar (오전=1, 오후=0)
        # 비고정 task만 변수, 고정 task는 task['time'] 그대로
        self.time_var = {}  # task_id -> BoolVar (1=오전, 0=오후) for non-fixed tasks
        # date_var[task_id]: 차리/판정 task의 날짜 선택 변수 (1=원래 date, 0=date_alt)
        # date_alt가 있는 task만 (shift_allowed_dates에 포함된 task)
        self.date_var = {}
        # broken_pair[pair_id] = BoolVar (1 if 묶음 깨짐)
        self.broken_pair = {}

        # 헬퍼 매핑
        self.person_by_name = {p['name']: p for p in self.persons}
        self.task_by_id = {t['task_id']: t for t in self.tasks}

    # ----- 변수 정의 -----
    def build_variables(self):
        for t in self.tasks:
            tid = t['task_id']
            for p in self.persons:
                self.x[(tid, p['name'])] = self.model.NewBoolVar(f"x_{tid}_{p['name']}")
            self.u[tid] = self.model.NewBoolVar(f"u_{tid}")
            # 비고정 task: 오전/오후 선택 변수
            if not _is_fixed_time_task(t['task']):
                self.time_var[tid] = self.model.NewBoolVar(f"time_{tid}_AM")
            # 날짜 이동 옵션 (date_alt 있는 task만): 1=원래 날짜, 0=alt 날짜
            if t.get('date_alt'):
                self.date_var[tid] = self.model.NewBoolVar(f"date_{tid}_orig")

    # ----- H1, H2 -----
    def add_h1_h2(self):
        """
        H1: Σ x[task, p] + u[task] = 1
        H2: 한 사람 한 (date, time)에 최대 1 task
            - 고정 task: task['time']에 직접 들어감
            - 비고정 task: time_var에 따라 오전/오후 결정
        """
        # H1
        for t in self.tasks:
            tid = t['task_id']
            self.model.Add(
                sum(self.x[(tid, p['name'])] for p in self.persons) + self.u[tid] == 1
            )

        # H2 + H5: 사람별 (date, time) 슬롯당 task 합 ≤ 1
        # 각 task의 점유 슬롯은 (date, time)인데:
        #   - 고정 task: (t.date, t.time)만 점유. x[tid,p]==1이면 그 슬롯에 들어감.
        #   - 비고정 task (time_var만): (t.date, '오전') 또는 (t.date, '오후')
        #   - 날짜 이동 가능 task (date_var 있음 + 차리/판정): 4가지 옵션
        #         (orig_date, am), (orig_date, pm), (alt_date, am), (alt_date, pm)
        # H5는 이 indicator를 만들 때 동시에 처리: blocked 슬롯이면 그 옵션 변수 = 0
        for p in self.persons:
            pname = p['name']
            slot_loads = {}  # {(date, time): [vars to sum]}

            for t in self.tasks:
                tid = t['task_id']
                is_fixed = _is_fixed_time_task(t['task'])
                has_date_alt = tid in self.date_var

                if is_fixed:
                    # 고정 task: (t.date, t.time)만
                    key = (t['date'], t['time'])
                    # H5: blocked면 x = 0
                    if (pname, t['date'], t['time']) in self.blocked:
                        self.model.Add(self.x[(tid, pname)] == 0)
                    slot_loads.setdefault(key, []).append(self.x[(tid, pname)])
                elif not has_date_alt:
                    # 비고정 + 날짜 고정: time_var에 따라 (t.date, 오전) 또는 (t.date, 오후)
                    am_blocked = (pname, t['date'], '오전') in self.blocked
                    pm_blocked = (pname, t['date'], '오후') in self.blocked
                    # H5: 양쪽 다 blocked면 x = 0
                    if am_blocked and pm_blocked:
                        self.model.Add(self.x[(tid, pname)] == 0)
                    elif am_blocked:
                        # 오전 못 들어감 → time_var must be 0 (오후)
                        self.model.Add(self.time_var[tid] == 0).OnlyEnforceIf(self.x[(tid, pname)])
                    elif pm_blocked:
                        self.model.Add(self.time_var[tid] == 1).OnlyEnforceIf(self.x[(tid, pname)])
                    # indicator: x AND time_var → 오전, x AND ~time_var → 오후
                    am_ind = self.model.NewBoolVar(f"am_{tid}_{pname}")
                    pm_ind = self.model.NewBoolVar(f"pm_{tid}_{pname}")
                    self.model.AddBoolAnd([self.x[(tid, pname)], self.time_var[tid]]).OnlyEnforceIf(am_ind)
                    self.model.AddBoolOr([self.x[(tid, pname)].Not(), self.time_var[tid].Not()]).OnlyEnforceIf(am_ind.Not())
                    self.model.AddBoolAnd([self.x[(tid, pname)], self.time_var[tid].Not()]).OnlyEnforceIf(pm_ind)
                    self.model.AddBoolOr([self.x[(tid, pname)].Not(), self.time_var[tid]]).OnlyEnforceIf(pm_ind.Not())
                    # 🔥 핵심: x=1이면 정확히 하나의 슬롯 indicator가 1이어야 함
                    # (am_blocked 또는 pm_blocked로 ind=0이 강제되어 있다면 다른 ind가 1로 가야 함)
                    self.model.Add(am_ind + pm_ind == self.x[(tid, pname)])
                    slot_loads.setdefault((t['date'], '오전'), []).append(am_ind)
                    slot_loads.setdefault((t['date'], '오후'), []).append(pm_ind)
                else:
                    # 비고정 + 날짜 이동 가능 (date_var 있음): 4 옵션
                    # date_var = 1: orig 날짜, 0: alt 날짜
                    # time_var = 1: 오전, 0: 오후
                    # 4가지 indicator: (orig+am, orig+pm, alt+am, alt+pm)
                    orig_d, alt_d = t['date'], t['date_alt']

                    # H5: 각 옵션이 blocked되어 있는지 미리 알아냄
                    blk_orig_am = (pname, orig_d, '오전') in self.blocked
                    blk_orig_pm = (pname, orig_d, '오후') in self.blocked
                    blk_alt_am = (pname, alt_d, '오전') in self.blocked
                    blk_alt_pm = (pname, alt_d, '오후') in self.blocked

                    # 4가지 다 blocked면 x = 0
                    if blk_orig_am and blk_orig_pm and blk_alt_am and blk_alt_pm:
                        self.model.Add(self.x[(tid, pname)] == 0)

                    # 각 슬롯 옵션의 indicator: x AND date_var(==orig?) AND time_var(==am?)
                    all_inds = []
                    for d_choice, d_str, blk_am, blk_pm in [
                        (1, orig_d, blk_orig_am, blk_orig_pm),  # date_var=1: orig
                        (0, alt_d, blk_alt_am, blk_alt_pm),     # date_var=0: alt
                    ]:
                        for t_choice, t_str, blk in [
                            (1, '오전', blk_am),
                            (0, '오후', blk_pm),
                        ]:
                            ind = self.model.NewBoolVar(f"opt_{tid}_{pname}_{d_str}_{t_str}")
                            if blk:
                                # blocked면 이 옵션 절대 0
                                self.model.Add(ind == 0)
                            else:
                                # ind = x AND (date_var == d_choice) AND (time_var == t_choice)
                                dv = self.date_var[tid] if d_choice == 1 else self.date_var[tid].Not()
                                tv = self.time_var[tid] if t_choice == 1 else self.time_var[tid].Not()
                                self.model.AddBoolAnd([self.x[(tid, pname)], dv, tv]).OnlyEnforceIf(ind)
                                self.model.AddBoolOr([self.x[(tid, pname)].Not(),
                                                       dv.Not(), tv.Not()]).OnlyEnforceIf(ind.Not())
                            slot_loads.setdefault((d_str, t_str), []).append(ind)
                            all_inds.append(ind)
                    # 🔥 핵심: x=1이면 정확히 하나의 슬롯 indicator가 1이어야 함
                    # (blocked로 ind=0이 강제된 옵션은 못 쓰니까, 다른 가능한 옵션 중 하나가 1)
                    self.model.Add(sum(all_inds) == self.x[(tid, pname)])

            for key, var_list in slot_loads.items():
                self.model.Add(sum(var_list) <= 1)

    # ----- H5: blocked 슬롯 (이미 H2 안에서 처리됨) -----
    def add_h5_blocked(self):
        """blocked 슬롯 제약은 add_h1_h2 안에서 처리됨 (date_var 결합 때문)"""
        pass

    # ----- H3: 보건소 -----
    def add_h3_bogeonso(self):
        """
        H3: 보건소 담당자는 일반 task 받지 않음 (모든 x = 0)
        보건소 task 자체는 df_all에 없음 (별도 처리). 보건소 담당자는 그냥 일반 task에서 제외.
        예외: 직전휴가 보충(H22) 대상자는 처치(오후)는 허용 (H22가 정확히 N개로 통제).
        """
        makeup = self.data.get('bogeonso_jikjeon_makeup', {})
        for p in self.persons:
            if p['is_bogeonso']:
                pname = p['name']
                allow_tx_pm = makeup.get(pname, 0) > 0
                for t in self.tasks:
                    if allow_tx_pm and t['task'] == '처치 (오후)':
                        continue  # H22가 처치(오후)를 정확히 N개로 배정
                    self.model.Add(self.x[(t['task_id'], pname)] == 0)

    # ----- H4: 영상 파견자 -----
    def add_h4_rad(self):
        """
        H4 (e1): 영상 파견자 주당 처리
          - 클리닉 task를 받을 수 있는 슬롯이 있는 주 → 클리닉 정확히 1개 (==1), 그 외 task X
          - 클리닉 받을 슬롯이 없는 주 → 처치 또는 예진 정확히 1개 (==1), 그 외 task X
        + 클리닉 차리/판정는 영상 파견자 + R2만 받을 수 있음
        """
        # 영상 파견자별 처리
        for p in self.persons:
            if not p['is_rad']:
                continue
            pname = p['name']

            # 주차별 분류
            clinic_tasks_by_week = {}  # {week: [tid, ...]}
            tx_yejin_tasks_by_week = {}  # {week: [tid, ...]}
            for t in self.tasks:
                w = t['week']
                if _is_clinic_panjung_chari(t['task']):
                    clinic_tasks_by_week.setdefault(w, []).append(t)
                elif _is_tx_task(t['task']) or "예진" in t['task']:
                    tx_yejin_tasks_by_week.setdefault(w, []).append(t)

            # 모든 주차 확보 (range)
            all_weeks = set()
            for t in self.tasks:
                all_weeks.add(t['week'])

            # 각 주마다 영상 파견자가 받을 수 있는 클리닉 task가 있는지 사전 판별
            # (이 사람이 그 task의 어떤 슬롯에라도 들어갈 수 있나? blocked 기준)
            def can_receive(task):
                """이 영상 파견자가 task를 받을 수 있는가? (blocked 슬롯 기준)"""
                if _is_fixed_time_task(task['task']):
                    return (pname, task['date'], task['time']) not in self.blocked
                else:
                    am = (pname, task['date'], '오전') in self.blocked
                    pm = (pname, task['date'], '오후') in self.blocked
                    return not (am and pm)

            for w in sorted(all_weeks):
                clinic_in_w = clinic_tasks_by_week.get(w, [])
                txyj_in_w = tx_yejin_tasks_by_week.get(w, [])

                # 받을 수 있는 클리닉이 있나?
                receivable_clinic = [t for t in clinic_in_w if can_receive(t)]

                if receivable_clinic:
                    # 클리닉 정확히 1개. 그 주의 클리닉 외 다른 task는 모두 0.
                    self.model.Add(
                        sum(self.x[(t['task_id'], pname)] for t in clinic_in_w) == 1
                    )
                    # 그 외 task (이 주차의 모든 task 중 클리닉 제외) 모두 0
                    clinic_tids_set = set(t['task_id'] for t in clinic_in_w)
                    for t in self.tasks:
                        if t['week'] != w: continue
                        if t['task_id'] in clinic_tids_set: continue
                        self.model.Add(self.x[(t['task_id'], pname)] == 0)
                else:
                    # 클리닉 못 받음 → 처치/예진 중 정확히 1개
                    receivable_txyj = [t for t in txyj_in_w if can_receive(t)]
                    if receivable_txyj:
                        self.model.Add(
                            sum(self.x[(t['task_id'], pname)] for t in receivable_txyj) == 1
                        )
                        # 그 외 task 모두 0 (받은 처치/예진 제외)
                        receivable_tids = set(t['task_id'] for t in receivable_txyj)
                        for t in self.tasks:
                            if t['week'] != w: continue
                            if t['task_id'] in receivable_tids: continue
                            self.model.Add(self.x[(t['task_id'], pname)] == 0)
                    else:
                        # 클리닉도 처치/예진도 못 받는 주 → 어떤 task도 못 받음
                        for t in self.tasks:
                            if t['week'] != w: continue
                            self.model.Add(self.x[(t['task_id'], pname)] == 0)

        # 클리닉 차리/판정는 영상 파견자 또는 R2만 받음 (그 외 hard 제외)
        # = R3 일반(영상X) + R1/R0는 받을 수 없음
        clinic_task_ids = [t['task_id'] for t in self.tasks if _is_clinic_panjung_chari(t['task'])]
        for p in self.persons:
            if p['is_rad']:
                continue  # 영상 파견자는 위에서 처리
            if p['year'] == 'R2' and not p['is_bogeonso']:
                continue  # R2 가능 (보건소 제외)
            # 그 외 모두 hard 제외
            pname = p['name']
            for tid in clinic_task_ids:
                self.model.Add(self.x[(tid, pname)] == 0)

    # ----- H8: R3 일반 판정 정확히 1개 -----
    def add_h8_r3_panjung(self):
        """
        H8: R3 (영상 파견자 제외) 일반 판정 = 정확히 1개
            클리닉 차리/판정는 판정 카운트에서 제외
        """
        panjung_task_ids = [t['task_id'] for t in self.tasks
                            if _is_panjung_task(t['task'])
                            and not _is_clinic_panjung_chari(t['task'])]
        for p in self.persons:
            if p['year'] != 'R3' or p['is_rad']:
                continue
            pname = p['name']
            self.model.Add(sum(self.x[(tid, pname)] for tid in panjung_task_ids) == 1)

    # ----- H8b: R3 판정 참관 정확히 1개 -----
    def add_h8b_r3_panjung_obs(self):
        """
        H8b: R3 (영상 파견자 제외) 판정 참관 = 정확히 1개
        """
        panjung_obs_task_ids = [t['task_id'] for t in self.tasks
                                if _is_panjung_obs_task(t['task'])]
        for p in self.persons:
            if p['year'] != 'R3' or p['is_rad']:
                continue
            pname = p['name']
            self.model.Add(sum(self.x[(tid, pname)] for tid in panjung_obs_task_ids) == 1)

    # ----- H8c: R3의 판정과 판정참관은 반드시 같은 묶음(pair) -----
    def add_h8c_r3_panjung_pair(self):
        """
        H8c: R3가 받는 판정(H8)과 판정참관(H8b)은 반드시 짝지어진 같은 묶음이어야 함.
          - 짝(판정 또는 참관)이 데이터에 없는 '단독' task는 R3가 받지 못함
            (윈도우 경계에서 짝이 잘린 판정/참관 = orphan)
          - 같은 pair_id 안에서 R3가 받은 판정 수 == 받은 참관 수
          H8(판정=1)+H8b(참관=1)와 결합되면, R3는 정확히 하나의 완전한 (판정+참관) 묶음을 받게 됨.
        """
        from collections import defaultdict
        pair_pj = defaultdict(list)  # pid -> [판정 task_id]
        pair_ob = defaultdict(list)  # pid -> [판정참관 task_id]
        for t in self.tasks:
            pid = t['pair_id']
            if _is_panjung_task(t['task']) and not _is_clinic_panjung_chari(t['task']):
                pair_pj[pid].append(t['task_id'])
            elif _is_panjung_obs_task(t['task']):
                pair_ob[pid].append(t['task_id'])

        # 완전한 묶음: pair_id(비어있지 않음)에 판정과 참관이 모두 존재
        full_pairs = set(pid for pid in pair_pj if pid and pid in pair_ob)

        # 단독(orphan) 판정/참관 task: pair_id 없거나 짝이 데이터에 없음
        orphan_tids = []
        for pid, tids in pair_pj.items():
            if pid not in full_pairs:
                orphan_tids.extend(tids)
        for pid, tids in pair_ob.items():
            if pid not in full_pairs:
                orphan_tids.extend(tids)

        for p in self.persons:
            if p['year'] != 'R3' or p['is_rad']:
                continue
            pname = p['name']
            # 단독 판정/참관 금지
            for tid in orphan_tids:
                self.model.Add(self.x[(tid, pname)] == 0)
            # 같은 묶음 안에서 판정 수 == 참관 수
            for pid in full_pairs:
                self.model.Add(
                    sum(self.x[(tid, pname)] for tid in pair_pj[pid])
                    == sum(self.x[(tid, pname)] for tid in pair_ob[pid])
                )

    # ----- H9: R0/의국처음 처치 X -----
    def add_h9_rookie_no_tx(self):
        tx_task_ids = [t['task_id'] for t in self.tasks if _is_tx_task(t['task'])]
        for p in self.persons:
            if not p['is_rookie']:
                continue
            pname = p['name']
            for tid in tx_task_ids:
                self.model.Add(self.x[(tid, pname)] == 0)

    # ----- H10: R3 전용 task -----
    def add_h10_r3_only(self):
        """조비룡/박민선 외래 차리/참관, 예진 = R3만"""
        r3_only_task_ids = [t['task_id'] for t in self.tasks if _is_r3_only_task(t['task'])]
        for p in self.persons:
            if p['year'] == 'R3':
                continue
            pname = p['name']
            for tid in r3_only_task_ids:
                self.model.Add(self.x[(tid, pname)] == 0)

    # ----- H11: Pairing (건증 묶음 제외 최대 5개 깨도 OK) -----
    def add_h11_pairing(self):
        """
        H11: 같은 pair_id의 task는 같은 사람에게.
          - 건증 묶음(건증 판정 + 판정 참관) 및 박진호 묶음(외래/통증클리닉)은 절대 분리 안 함 (broken = 0 강제)
          - 그 외 묶음은 최대 5개까지 깨도 OK (Σ broken_pair ≤ 5)
        구현:
          - 각 pair_id의 task들에 대해 broken_pair 변수 생성
          - 묶음이 모두 같은 사람이면 broken = 0, 다르면 broken = 1
        """
        pair_groups = {}
        for t in self.tasks:
            pid = t['pair_id']
            if pid:
                pair_groups.setdefault(pid, []).append(t['task_id'])

        for pid, tids in pair_groups.items():
            if len(tids) < 2:
                continue
            bp = self.model.NewBoolVar(f"broken_{pid}")
            self.broken_pair[pid] = bp
            # 절대 분리 금지 묶음 → broken = 0 강제 (≤5 캡과 무관하게 항상 유지)
            #   - 건증 묶음 (건증 판정 + 판정 참관)
            #   - 박진호 묶음 (외래/통증클리닉 차리 + 참관)
            pair_task_names = [self.task_by_id[tid]['task'] for tid in tids]
            no_break = any(("건증" in tn or "박진호" in tn) for tn in pair_task_names)
            if no_break:
                self.model.Add(bp == 0)
            # 묶음의 모든 task가 같은 사람 → broken = 0
            # 즉 각 person별로: 한 사람이 묶음 task 다 받거나 (sum=len) 0개 받거나 (sum=0)
            # 둘 다 아니면 broken=1
            # → 다른 표현: 각 task pair (tid_i, tid_j)에 대해
            #     x[tid_i, p] == x[tid_j, p] for all p   ⟺ broken = 0
            # 너무 많은 제약이 되니까, 다른 방식:
            #   "묶음 전체가 한 사람에게 갔다" indicator를 만들고, 그 합 ≥ 1이면 broken=0
            # 더 간단: any pair (tid_i, tid_j)에서 x[tid_i,p] != x[tid_j,p] 인 p가 존재 → broken=1
            # 효율적 표현: 같은 묶음 안의 첫 task에 대해, 다른 task가 같은 사람이 받는지 체크
            tid0 = tids[0]
            for tid_other in tids[1:]:
                # for each person, x[tid0, p] - x[tid_other, p] 가 0이 아니면 broken=1
                # 즉 diff[p] = |x[tid0,p] - x[tid_other,p]| → Σ diff[p] ≥ 1이면 broken=1
                # 또는 모든 person에 대해 x[tid0,p] == x[tid_other,p]면 broken=0
                # CP-SAT 방식: 두 변수 같지 않으면 broken=1
                for p in self.persons:
                    pname = p['name']
                    # If x[tid0,p] != x[tid_other,p], then bp = 1
                    diff = self.model.NewBoolVar(f"diff_{tid0}_{tid_other}_{pname}")
                    # diff = (x[tid0,p] XOR x[tid_other,p])
                    self.model.AddBoolXOr([self.x[(tid0, pname)], self.x[(tid_other, pname)], diff.Not()])
                    # diff implies bp
                    self.model.Add(bp >= diff)

        # 총 깨진 묶음 ≤ max_broken_pairs (건증/박진호 묶음은 위에서 broken=0 강제라 합산에서 0)
        if self.broken_pair:
            self.model.Add(sum(self.broken_pair.values()) <= self.max_broken_pairs)

    # ----- H12: 처치 90% 이상 R3+R2 -----
    def add_h12_tx_90pct(self):
        tx_task_ids = [t['task_id'] for t in self.tasks if _is_tx_task(t['task'])]
        if not tx_task_ids:
            return
        # R3+R2 (영상 제외)에게 가는 처치 수 ≥ ceil(0.9 × 총 처치 수)
        # 단, 미배정 처치는 카운트 제외 (배정된 것 중 90%)
        # 간단하게: R1/R0 (영상 제외)에게 가는 처치 수 ≤ floor(0.1 × 총 처치 수)
        # → R1+R0 처치 ≤ floor(0.1 * len(tx))
        max_lower = len(tx_task_ids) // 10  # 10% (floor)
        lower_tier_names = [p['name'] for p in self.persons
                            if p['year'] in ['R1', 'R0'] and not p['is_bogeonso'] and not p['is_rad']]
        if lower_tier_names:
            self.model.Add(
                sum(self.x[(tid, pname)] for tid in tx_task_ids for pname in lower_tier_names) <= max_lower
            )

    # ----- H13: 박진호 통증클리닉 사전 신청자 -----
    def add_h13_pain_applicants(self):
        """
        H13: 박진호 통증클리닉 사전 신청자는 최소 1주 이상의 통증클리닉 묶음을 받음.
        (각 묶음을 신청자가 받아야 한다는 뜻이 아님 — 신청자가 휴가 등으로 못 받는 주는 다른 사람 OK)
        """
        applicants = self.data['pain_applicants']
        if not applicants:
            return
        valid_applicants = [a for a in applicants if a in self.person_by_name]
        if not valid_applicants:
            return

        # 모든 통증클리닉 task 수집
        pain_task_ids = [t['task_id'] for t in self.tasks if _is_pain_clinic_task(t['task'])]
        if not pain_task_ids:
            return

        # 각 신청자별로: 통증클리닉 task 중 최소 1개 받음
        # (pairing 룰 H11이 묶음 전체를 같은 사람에게 묶어주므로,
        #  최소 1개 task 받으면 그 묶음 전체를 받게 됨 = 최소 1주 받음)
        for applicant in valid_applicants:
            self.model.Add(
                sum(self.x[(tid, applicant)] for tid in pain_task_ids) >= 1
            )

    # ----- H14: R1 처치 최대 1개 -----
    def add_h14_r1_tx_max_1(self):
        tx_task_ids = [t['task_id'] for t in self.tasks if _is_tx_task(t['task'])]
        for p in self.persons:
            if p['year'] != 'R1' or p['is_rookie']:
                continue
            pname = p['name']
            self.model.Add(sum(self.x[(tid, pname)] for tid in tx_task_ids) <= 1)

    # ----- H_TX_YEJIN: 처치+예진 합 R2+R3 풀에서 max-min ≤ 2 -----
    def add_h_tx_yejin_balance(self):
        """
        처치(오전), 처치(오후), 예진 task 모두 합산.
        R2 + R3 (영상/보건소 제외) 전체 풀에서 한 사람의 합 max-min ≤ 2.
        R1/R0은 풀에 포함 안 됨.
        """
        tx_yejin_task_ids = [t['task_id'] for t in self.tasks
                             if _is_tx_task(t['task']) or "예진" in t['task']]
        if not tx_yejin_task_ids:
            return

        pool_persons = [p for p in self.persons
                        if p['year'] in ['R2', 'R3']
                        and not p['is_bogeonso']
                        and not p['is_rad']]
        if len(pool_persons) < 2:
            return

        # 각 사람의 처치+예진 합 변수
        person_tx_yejin = {}
        for p in pool_persons:
            cnt = self.model.NewIntVar(0, len(tx_yejin_task_ids), f"txy_{p['name']}")
            self.model.Add(cnt == sum(self.x[(tid, p['name'])] for tid in tx_yejin_task_ids))
            person_tx_yejin[p['name']] = cnt

        # max-min ≤ 2 ⟺ 모든 (i, j) 쌍에 대해 |cnt_i - cnt_j| ≤ 2
        names = list(person_tx_yejin.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = person_tx_yejin[names[i]]
                b = person_tx_yejin[names[j]]
                self.model.Add(a - b <= 2)
                self.model.Add(b - a <= 2)

    # ----- H15, H16, H17: 로딩 -----
    def add_h15_h16_h17_loading(self):
        """
        H15: 로딩 범위 (그룹별, self.loading_ranges)
        H16: 그룹(병합 클러스터) 내 max - min ≤ 0.3
        H17: 인접 그룹 부등호 (self.h17_ops: '<' strict / '<=' non-strict / '=' 병합)

        로딩 = (배정 task 수 × 10) / avail
        CP-SAT는 정수만 다루므로, 로딩 * 100을 정수로 (소수점 2자리 정밀도)
        loading_int = (배정 수 × 1000) / avail  (1000 = 10 × 100)
        """
        MULT = self.target_mult_multiplier
        ranges = self.loading_ranges       # {0..4: (lo, hi)}
        ops = self.h17_ops                 # {0..3: '<'/'<='/'='}
        forced_count = self.data.get('person_forced_count', {})
        # 사람별 배정 task 수 변수 (정수) + 강제 연보 슬롯 합산
        person_assigned = {}
        for p in self.persons:
            if p['group'] == -1:
                continue
            pname = p['name']
            forced = forced_count.get(pname, 0)
            count_var = self.model.NewIntVar(0, len(self.tasks) + forced, f"cnt_{pname}")
            # 일반 task 합 + 강제 연보 슬롯 수 (상수)
            self.model.Add(count_var == sum(self.x[(t['task_id'], pname)] for t in self.tasks) + forced)
            person_assigned[pname] = count_var

        # ----- '=' 로 연결된 인접 그룹은 한 클러스터로 병합 -----
        # ops[g]가 '='면 그룹 g와 g+1을 같은 클러스터로 취급 (한 그룹처럼).
        cluster_of = {0: 0}
        for g in range(1, 5):
            if ops.get(g - 1) == '=':
                cluster_of[g] = cluster_of[g - 1]
            else:
                cluster_of[g] = cluster_of[g - 1] + 1
        # 클러스터별 통합 로딩 범위 = (병합된 그룹들의 min 하한, max 상한)
        cluster_range = {}
        for g in range(5):
            c = cluster_of[g]
            lo, hi = ranges[g]
            if c not in cluster_range:
                cluster_range[c] = [lo, hi]
            else:
                cluster_range[c][0] = min(cluster_range[c][0], lo)
                cluster_range[c][1] = max(cluster_range[c][1], hi)

        # H15: 각 사람의 로딩을 자기 클러스터 범위 [lo, hi] (배율 적용) → count 범위로 환산
        # 단, R3 영상은 그룹 -1로 제외됨
        for p in self.persons:
            if p['group'] == -1:
                continue
            pname = p['name']
            avail = self.person_avail_sessions[pname]
            lo_load, hi_load = cluster_range[cluster_of[p['group']]]
            # 배율(MULT)은 '최대값'만 키움 — 최소값은 그대로 두어 범위를 위로만 확장
            hi_load *= MULT
            # 하한은 올림(ceil)해야 loading >= lo_load 보장
            count_lo = math.ceil(lo_load * avail / 10)
            # 상한은 내림(floor)해야 loading <= hi_load 보장
            count_hi = math.floor(hi_load * avail / 10)
            self.model.Add(person_assigned[pname] >= count_lo)
            self.model.Add(person_assigned[pname] <= count_hi)

        # H16: 같은 클러스터 내 두 사람의 로딩 차이 ≤ 0.3 × MULT
        #   |count1/avail1 - count2/avail2| ≤ 0.03 (로딩 단위 0.3 → 분자 10배 → 3)
        #   → |count1 × avail2 - count2 × avail1| × 10 ≤ floor(0.3 × MULT × avail1 × avail2)
        DIFF_LIMIT = 0.3 * MULT  # 로딩 차이 한도
        clusters = {}
        for p in self.persons:
            if p['group'] != -1:
                clusters.setdefault(cluster_of[p['group']], []).append(p['name'])

        for c, names in clusters.items():
            if len(names) < 2:
                continue
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    n1, n2 = names[i], names[j]
                    a1 = self.person_avail_sessions[n1]
                    a2 = self.person_avail_sessions[n2]
                    limit = int(DIFF_LIMIT * a1 * a2)
                    self.model.Add(person_assigned[n1] * a2 * 10 - person_assigned[n2] * a1 * 10 <= limit)
                    self.model.Add(person_assigned[n2] * a1 * 10 - person_assigned[n1] * a2 * 10 <= limit)

        # H17: 인접 그룹 부등호 (경계 g = 0..3)
        #   '<'  strict   : count_low × a_high × 10 + 1 ≤ count_high × a_low × 10
        #   '<=' non-strict: count_low × a_high × 10     ≤ count_high × a_low × 10
        #   '='  병합       : 부등호 없음 (H15 범위 + H16 차이로 한 그룹 처리)
        groups = {0: [], 1: [], 2: [], 3: [], 4: []}
        for p in self.persons:
            if p['group'] != -1:
                groups[p['group']].append(p['name'])

        for g in range(4):
            op = ops.get(g, '<')
            if op == '=':
                continue  # 병합 — 위 H15/H16에서 한 클러스터로 처리됨
            higher_g = g + 1
            if not groups[g] or not groups[higher_g]:
                continue
            for n_low in groups[g]:
                for n_high in groups[higher_g]:
                    a_low = self.person_avail_sessions[n_low]
                    a_high = self.person_avail_sessions[n_high]
                    if op == '<':
                        self.model.Add(
                            person_assigned[n_low] * a_high * 10 + 1
                            <= person_assigned[n_high] * a_low * 10
                        )
                    else:  # '<='
                        self.model.Add(
                            person_assigned[n_low] * a_high * 10
                            <= person_assigned[n_high] * a_low * 10
                        )

        self.person_assigned = person_assigned  # 다른 메서드에서 참조

    # ----- H18: R2/R1 주당 판정 변동 허용 + 총 판정 수 한도 ----- 
    def add_h18_weekly_panjung(self):
        """
        H18:
          - R2 주당 판정 최대 3 (변동 허용)
          - R1/R0 주당 판정 최대 3 (변동 허용)
          - R2 총 판정 수 최소 3개 (사용자 추가)
          - R1/R0 총 판정 수 최대 (week_count + 5) (사용자 추가, 4주→9, 5주→10)
          - max(R2 판정) < min(R1/R0 판정) (strict 부등호)
        """
        panjung_task_ids_by_week = {}
        for t in self.tasks:
            if _is_panjung_task(t['task']) and not _is_clinic_panjung_chari(t['task']):
                panjung_task_ids_by_week.setdefault(t['week'], []).append(t['task_id'])

        # 주당 max
        for p in self.persons:
            if p['group'] == -1:
                continue
            pname = p['name']
            if p['year'] in ['R1', 'R0']:
                max_per_week = 3
            elif p['year'] == 'R2':
                max_per_week = 3
            else:
                continue  # R3는 H8에서 총 1개로 제한
            for w, tids in panjung_task_ids_by_week.items():
                self.model.Add(sum(self.x[(tid, pname)] for tid in tids) <= max_per_week)

        # === 총 판정 수 한도 + 부등호 ===
        all_panjung_tids = [t['task_id'] for t in self.tasks
                            if _is_panjung_task(t['task']) and not _is_clinic_panjung_chari(t['task'])]
        if not all_panjung_tids:
            return

        r2_persons = [p for p in self.persons if p['group'] == 3]
        r1r0_persons = [p for p in self.persons if p['group'] == 4]

        # R2 총 판정 카운트 변수
        r2_panjung = {}
        for p in r2_persons:
            var = self.model.NewIntVar(0, len(all_panjung_tids), f"r2pj_{p['name']}")
            self.model.Add(var == sum(self.x[(tid, p['name'])] for tid in all_panjung_tids))
            r2_panjung[p['name']] = var
            # 신규: R2 최소 판정 3개
            self.model.Add(var >= 3)

        # R1/R0 총 판정 카운트 변수
        r1r0_panjung = {}
        # 신규: R1/R0 최대 판정 = week_count + 5
        r1r0_max_total = self.data['week_count'] + 5
        for p in r1r0_persons:
            var = self.model.NewIntVar(0, len(all_panjung_tids), f"r1pj_{p['name']}")
            self.model.Add(var == sum(self.x[(tid, p['name'])] for tid in all_panjung_tids))
            r1r0_panjung[p['name']] = var
            # 신규: 최대 한도
            self.model.Add(var <= r1r0_max_total)

        # 부등호 strict <: max(R2) < min(R1/R0)
        if r2_panjung and r1r0_panjung:
            for r2_name, r2_var in r2_panjung.items():
                for r1_name, r1_var in r1r0_panjung.items():
                    self.model.Add(r2_var + 1 <= r1_var)

    # ----- H19: R3 일반 클리닉 차리/판정 후순위 -----
    def add_h19_r3_clinic_soft(self):
        """
        H19 soft: 영상 파견자가 못 받은 클리닉 차리/판정는 R3 일반도 받을 수 있음
        (별도 제약 추가 없이 H4의 ≤ 1로 영상 파견자가 최대한 받고, 남은 건 자유롭게 배정됨)
        단, R3 영상 제외는 H8에서 일반 판정 1개 강제. 클리닉 차리/판정는 일반 판정 카운트 X (H8 정의대로).
        """
        # 추가 제약 없음 (H4와 H8이 이미 처리)
        pass

    # ----- 차리/판정 -1 이동 추가 허용 한도 -----
    def add_shift_allowance_limit(self):
        """
        슬롯부족(shortage)으로 허용된 task가 아닌, '추가로' -1 이동하는 차리/판정 수를
        extra_shift_limit개 이하로 제한.
        - shortage task: 무제한 (필요하면 이동)
        - 그 외 task: 합쳐서 extra_shift_limit개까지만 이동 허용
        date_var[tid]==1 (원래 날짜), ==0 (이동). 이동 수 = len - sum(date_var).
        """
        extra_tids = [tid for tid in self.date_var if tid not in self.shortage_shift_tids]
        if not extra_tids:
            return
        # 이동(=0)한 수 ≤ extra_shift_limit  ⟺  원래날짜(=1) 수 ≥ len - extra_shift_limit
        self.model.Add(
            sum(self.date_var[tid] for tid in extra_tids) >= len(extra_tids) - self.extra_shift_limit
        )

    # ----- H21: 같은 연차 내 판정 수 max-min ≤ 2 -----
    def add_h21_year_panjung_diff(self):
        """
        H21: 같은 연차(R3/R2/R1/R0) 내에서 일반 판정 개수의 최대 차이 ≤ 2.
             (영상 파견자/보건소 = group -1 제외. 일반 판정 = 참관/클리닉 차리/판정 제외)
        """
        panjung_task_ids = [t['task_id'] for t in self.tasks
                            if _is_panjung_task(t['task'])
                            and not _is_clinic_panjung_chari(t['task'])]
        if not panjung_task_ids:
            return
        # 연차별 사람 그룹 (group -1 = 영상/보건소 제외)
        year_groups = {}
        for p in self.persons:
            if p['group'] == -1:
                continue
            year_groups.setdefault(p['year'], []).append(p['name'])
        # 사람별 판정 수 변수
        pj_count = {}
        for p in self.persons:
            if p['group'] == -1:
                continue
            pname = p['name']
            cv = self.model.NewIntVar(0, len(panjung_task_ids), f"pjcnt_{pname}")
            self.model.Add(cv == sum(self.x[(tid, pname)] for tid in panjung_task_ids))
            pj_count[pname] = cv
        # 같은 연차 내 모든 쌍에 대해 |c_i - c_j| ≤ 2
        for yr, names in year_groups.items():
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    a, b = pj_count[names[i]], pj_count[names[j]]
                    self.model.Add(a - b <= 2)
                    self.model.Add(b - a <= 2)

    # ----- H22: 보건소 직전휴가 보충(처치 오후) -----
    def add_h22_bogeonso_makeup(self):
        """
        H22: 연건 보건소 담당자가 직전휴가를 써서 대체자가 대체한 연보 세션 수(N)만큼,
             그 담당자에게 처치(오후)를 정확히 N개 배정.
        """
        makeup = self.data.get('bogeonso_jikjeon_makeup', {})
        if not makeup:
            return
        tx_pm_tids = [t['task_id'] for t in self.tasks if t['task'] == '처치 (오후)']
        if not tx_pm_tids:
            return
        for name, n in makeup.items():
            self.model.Add(sum(self.x[(tid, name)] for tid in tx_pm_tids) == n)

    # ----- 목적함수 -----
    def build_objective(self):
        """
        주요 목적:
          1. 미배정 task 최소화 (가장 큰 가중치)
          2. 깨진 pairing 최소화
          3. 차리/판정 날짜 이동 최소화 (date_alt 사용)
          4. 교수 중복 최소화 (S5)
        """
        # 가중치 우선순위: 미배정 >>> 깨진 pair >>> 이동 >>> 교수 중복
        UNASSIGNED_PENALTY = 1000000
        BROKEN_PAIR_PENALTY = 10000
        SHIFT_PENALTY = 100
        PROF_REPEAT_PENALTY = 1

        unassigned_term = sum(self.u[t['task_id']] for t in self.tasks) * UNASSIGNED_PENALTY
        broken_term = sum(self.broken_pair.values()) * BROKEN_PAIR_PENALTY if self.broken_pair else 0

        # 이동 페널티: date_var == 0 (alt 날짜 사용)이면 페널티
        # 단 task가 미배정이면 이동 없음 (페널티 0)
        # date_var.Not() = alt 사용 = shifted
        shift_term = 0
        if self.date_var:
            # shifted indicator = date_var.Not() AND NOT u (배정된 경우만)
            # 더 간단: shifted = date_var == 0 AND u == 0
            # 페널티는 단순히 date_var.Not() 합 (미배정이면 date_var는 의미 없으므로 무시 OK)
            shift_vars = []
            for tid, dv in self.date_var.items():
                # shifted = (1 - date_var) - u 같은 구조보다는
                # shift_used = NewBoolVar with shift_used == (date_var == 0 AND u == 0)
                # 그냥 date_var의 not 사용 (미배정일 때 영향 적음)
                shift_ind = self.model.NewBoolVar(f"shift_used_{tid}")
                # shift_ind = NOT date_var AND NOT u
                self.model.AddBoolAnd([dv.Not(), self.u[tid].Not()]).OnlyEnforceIf(shift_ind)
                self.model.AddBoolOr([dv, self.u[tid]]).OnlyEnforceIf(shift_ind.Not())
                shift_vars.append(shift_ind)
            shift_term = sum(shift_vars) * SHIFT_PENALTY

        # S5: 같은 교수의 task를 한 사람이 여러 개 받으면 페널티
        prof_repeat_vars = []
        person_prof_tasks = {}
        for t in self.tasks:
            prof = _extract_prof(t['task'])
            if prof is None:
                continue
            for p in self.persons:
                key = (p['name'], prof)
                person_prof_tasks.setdefault(key, []).append(t['task_id'])

        for (pname, prof), tids in person_prof_tasks.items():
            count = self.model.NewIntVar(0, len(tids), f"profcount_{pname}_{prof}")
            self.model.Add(count == sum(self.x[(tid, pname)] for tid in tids))
            excess = self.model.NewIntVar(0, len(tids), f"profexcess_{pname}_{prof}")
            self.model.AddMaxEquality(excess, [count - 1, self.model.NewConstant(0)])
            prof_repeat_vars.append(excess)

        prof_term = sum(prof_repeat_vars) * PROF_REPEAT_PENALTY if prof_repeat_vars else 0

        self.model.Minimize(unassigned_term + broken_term + shift_term + prof_term)

    def build_model(self):
        """모든 제약 + 목적함수 추가"""
        self.build_variables()
        self.add_h1_h2()
        self.add_h5_blocked()
        self.add_h3_bogeonso()
        self.add_h4_rad()
        self.add_h8_r3_panjung()
        self.add_h8b_r3_panjung_obs()
        self.add_h8c_r3_panjung_pair()
        self.add_h9_rookie_no_tx()
        self.add_h10_r3_only()
        self.add_h11_pairing()
        self.add_h12_tx_90pct()
        self.add_h13_pain_applicants()
        self.add_h14_r1_tx_max_1()
        self.add_h_tx_yejin_balance()  # 신규: 처치+예진 합 R2+R3 max-min ≤ 2
        self.add_h15_h16_h17_loading()
        self.add_h18_weekly_panjung()
        self.add_h19_r3_clinic_soft()
        self.add_h21_year_panjung_diff()
        self.add_h22_bogeonso_makeup()
        self.add_shift_allowance_limit()
        self.build_objective()

    def solve(self, time_limit_sec=60):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_sec
        solver.parameters.num_search_workers = 4

        status = solver.Solve(self.model)

        result = {
            'status': solver.StatusName(status),
            'objective_value': solver.ObjectiveValue() if status in [cp_model.OPTIMAL, cp_model.FEASIBLE] else None,
            'assignments': {},
            'unassigned': [],
            'broken_pairs': [],
            'task_time_overrides': {},  # task_id → '오전' or '오후' (비고정 task 결과)
            'task_date_overrides': {},  # task_id → 새 date (date_alt로 이동된 경우)
            'shifted_tasks': [],         # date_alt로 실제 이동한 task_id 목록
            'forced_assignments': self.data.get('forced_assignments', {}),  # (name, date, time) → label (연보)
            'wall_time_sec': solver.WallTime(),
        }

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            for t in self.tasks:
                tid = t['task_id']
                if solver.Value(self.u[tid]) == 1:
                    result['unassigned'].append(tid)
                    continue
                for p in self.persons:
                    pname = p['name']
                    if solver.Value(self.x[(tid, pname)]) == 1:
                        result['assignments'][tid] = pname
                        break
                # 비고정 task의 시간 결정
                if tid in self.time_var:
                    result['task_time_overrides'][tid] = '오전' if solver.Value(self.time_var[tid]) == 1 else '오후'
                # 날짜 이동 결정 (date_var = 0이면 alt 날짜 사용)
                if tid in self.date_var:
                    if solver.Value(self.date_var[tid]) == 0:
                        result['task_date_overrides'][tid] = t['date_alt']
                        result['shifted_tasks'].append(tid)

            for pid, bp in self.broken_pair.items():
                if solver.Value(bp) == 1:
                    result['broken_pairs'].append(pid)

        return result


# ============================================================
# 사전 진단 — 해 없으면 배율 자동 상향
# ============================================================

def _compute_auto_multiplier(df_all, residents, leaves, week_count, start_date, holidays,
                              bogeonso_substitutes=None, rad_days=None, student_practices=None):
    """
    사전 진단으로 배율 자동 산출.
    
    필요 평균 로딩 = (전체 task 수 × 10) / (모든 사람의 일반 배정 가능 슬롯 합)
    사용자 지정 평균 로딩 = 각 사람의 target_mult 평균
    
    배율 = 필요 / 지정 (1.0 미만이면 1.0)
    1.0 초과면 소수 둘째 자리에서 올림 (0.1 단위로)
      예: 1.01 → 1.1, 1.05 → 1.1, 1.09 → 1.1, 1.11 → 1.2
    
    반환: float (배율)
    """
    import math as _math
    pdata = build_problem_data(
        df_all, residents, leaves, week_count, start_date, holidays,
        bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
        student_practices=student_practices
    )

    # 일반 task 수 (영상 파견자가 받는 클리닉 등은 일반 task에서 분리 X — 그냥 df_all 전체)
    # 다만 영상/보건소가 받는 task는 영상/보건소의 슬롯과 매칭되므로 분모/분자 모두 영향 동일
    total_tasks = len(pdata['tasks'])

    # 일반 배정 가능 슬롯 합 — group != -1 사람들의 avail에서 forced(메인외래/학생실습/영상/연보) 차감
    # = 일반 task가 들어갈 수 있는 실제 슬롯 수
    total_general_slots = 0
    sum_target_mult = 0.0
    target_count = 0
    forced_count = pdata.get('person_forced_count', {})
    for p in pdata['persons']:
        if p['group'] == -1:
            continue
        name = p['name']
        avail = pdata['person_avail_sessions'].get(name, 0)
        forced = forced_count.get(name, 0)
        # 일반 task가 받을 수 있는 슬롯 = avail - forced
        total_general_slots += max(0, avail - forced)
        # 사용자 지정 target_mult
        for r in residents:
            if r['이름'] == name:
                sum_target_mult += get_resident_target_mult(r)
                target_count += 1
                break

    if total_general_slots <= 0 or target_count == 0:
        return 1.0

    # 일반 task 수 = 전체 task - (영상 파견자 받는 클리닉 + 보건소 받는 task)
    # 보건소는 일반 task 안 받음 → 0
    # 영상 파견자는 클리닉/처치/예진 받음 (주당 1개) → week_count개
    rad_count_persons = sum(1 for p in pdata['persons'] if p['is_rad'])
    rad_received = rad_count_persons * week_count  # 영상이 받는 task 수
    general_tasks = total_tasks - rad_received

    needed_avg = (general_tasks * 10) / total_general_slots
    user_avg = sum_target_mult / target_count

    if needed_avg <= user_avg:
        return 1.0

    raw_mult = needed_avg / user_avg
    # 소수 둘째 자리에서 올림 (0.1 단위)
    # 1.0 초과면 무조건 0.1 단위로 올림
    mult_x10 = _math.ceil(raw_mult * 10) / 10.0
    # 최대 1.5
    return min(mult_x10, 1.5)


def diagnose_infeasibility(df_all, residents, leaves, week_count, start_date, holidays,
                            bogeonso_substitutes=None, rad_days=None, student_practices=None,
                            pain_applicants=None, target_mult_multiplier=1.0,
                            shift_allowed_tids=None, time_limit_sec=30,
                            per_solve_time=5, enable_drop_two=False,
                            loading_ranges=None, h17_ops=None, max_broken_pairs=5):
    """
    INFEASIBLE 발생 시 어떤 룰들이 충돌하는지 진단.
    
    각 단계마다 룰을 다양하게 조합해보면서 어떤 룰이 INFEASIBLE을 유발하는지 찾음.
    
    per_solve_time: 각 시도(룰 조합)의 시간 제한 (초). 기본 5초.
    enable_drop_two: 2개씩 빼서 시도하는 단계 활성화 (시간 많이 걸림). 기본 False.
    
    반환: dict
        - blocking_rules: ["H10", "H18", ...] (이 룰들이 동시에 켜져 있어서 풀이 불가)
        - rule_descriptions: 각 룰의 설명
    """
    if shift_allowed_tids is None:
        shift_allowed_tids = set()

    rule_descriptions = {
        'H4_rad': 'H4: 영상 파견자 주당 정확히 1개 (클리닉 or 처치/예진)',
        'H8_r3_panjung': 'H8: R3 (영상 제외) 일반 판정 = 정확히 1개',
        'H8b_r3_panjung_obs': 'H8b: R3 (영상 제외) 판정 참관 = 정확히 1개',
        'H8c_r3_panjung_pair': 'H8c: R3의 판정과 판정참관은 반드시 같은 묶음 (단독 판정/참관 금지)',
        'H9_rookie_no_tx': 'H9: R0/의국처음 R1 = 처치 X',
        'H10_r3_only': 'H10: 조비룡/박민선 외래 차리/참관 + 예진 = R3만',
        'H11_pairing': 'H11: 차리/판정 + 참관 묶음 = 같은 사람 (건증·박진호 묶음 절대 안 깸, 그 외 최대 5개 깨도 OK)',
        'H12_tx_90pct': 'H12: 처치(오전+오후) 90% 이상 R3+R2',
        'H13_pain_applicants': 'H13: 박진호 통증클리닉 사전 신청자 우선',
        'H14_r1_tx_max_1': 'H14: R1 처치 최대 1개',
        'H_tx_yejin_balance': 'H_TX_YEJIN: 처치+예진 합 (R2+R3 풀) max-min ≤ 2',
        'H15_h16_h17_loading': 'H15-17: 그룹별 로딩 범위 + 내부 차이 ≤ 0.3 + strict 부등호 chain',
        'H18_weekly_panjung': 'H18: R2 최소 3개 / R1/R0 최대 (week+5) / max(R2) < min(R1/R0)',
        'H21_year_panjung_diff': 'H21: 같은 연차 내 판정 수 max-min ≤ 2',
        'H22_bogeonso_makeup': 'H22: 보건소 직전휴가 대체분만큼 처치(오후) 배정',
    }

    # 임시 빌드 (clinic 차리/판정 R2 only도 H4와 묶을 룰)
    pdata = build_problem_data(
        df_all, residents, leaves, week_count, start_date, holidays,
        bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
        student_practices=student_practices, pain_applicants=pain_applicants,
        shift_allowed_tids=shift_allowed_tids
    )

    # 진단용 새 모델 — 각 룰에 assumption literal 부여
    solver = CPSATScheduleSolver(pdata, target_mult_multiplier=target_mult_multiplier,
                                 loading_ranges=loading_ranges, h17_ops=h17_ops,
                                 max_broken_pairs=max_broken_pairs)
    solver.build_variables()
    # 필수 룰 (이건 진단에서 빼면 안 됨 — 모델 자체의 핵심)
    solver.add_h1_h2()
    solver.add_h5_blocked()
    solver.add_h3_bogeonso()

    # 각 옵션 룰을 assumption 변수에 묶기
    # 방법: 별도 모델을 만들고, 각 룰을 boolean literal로 묶음
    # OR-Tools의 AddAssumption은 ProtoBufClause 단위 — 우회 방법:
    # 각 룰의 제약을 BoolVar로 implication 처리

    assumptions = {}  # {rule_name: BoolVar}

    # 헬퍼: 룰 메서드를 호출하기 전에 모든 model.Add를 hooking해서 OnlyEnforceIf(lit)로 감싸기
    # 간단하게: 각 룰을 별도 sub-model로 만들고 활성화 변수 사용
    # → 더 단순한 접근: enumerate로 룰들을 끄고 켜며 시도

    # Drop-one-at-a-time 방식: 각 룰을 빼고 풀이해서 그 때 FEASIBLE이 되면 그 룰이 충돌의 일부
    rule_methods = [
        ('H4_rad', solver.add_h4_rad),
        ('H8_r3_panjung', solver.add_h8_r3_panjung),
        ('H8b_r3_panjung_obs', solver.add_h8b_r3_panjung_obs),
        ('H8c_r3_panjung_pair', solver.add_h8c_r3_panjung_pair),
        ('H9_rookie_no_tx', solver.add_h9_rookie_no_tx),
        ('H10_r3_only', solver.add_h10_r3_only),
        ('H11_pairing', solver.add_h11_pairing),
        ('H12_tx_90pct', solver.add_h12_tx_90pct),
        ('H13_pain_applicants', solver.add_h13_pain_applicants),
        ('H14_r1_tx_max_1', solver.add_h14_r1_tx_max_1),
        ('H_tx_yejin_balance', solver.add_h_tx_yejin_balance),
        ('H15_h16_h17_loading', solver.add_h15_h16_h17_loading),
        ('H18_weekly_panjung', solver.add_h18_weekly_panjung),
        ('H21_year_panjung_diff', solver.add_h21_year_panjung_diff),
        ('H22_bogeonso_makeup', solver.add_h22_bogeonso_makeup),
    ]

    def _solve_with(rule_set, mult=target_mult_multiplier, time_limit=None):
        """rule_set만 추가하고 풀이"""
        if time_limit is None:
            time_limit = per_solve_time
        s = CPSATScheduleSolver(pdata, target_mult_multiplier=mult,
                                loading_ranges=loading_ranges, h17_ops=h17_ops,
                                max_broken_pairs=max_broken_pairs)
        s.build_variables()
        s.add_h1_h2()
        s.add_h5_blocked()
        s.add_h3_bogeonso()
        for rname in rule_set:
            for n, m in rule_methods:
                if n == rname:
                    m_new = getattr(s, m.__name__)
                    m_new()
                    break
        s.build_objective()
        cp = cp_model.CpSolver()
        cp.parameters.max_time_in_seconds = time_limit
        cp.parameters.num_search_workers = 4
        status = cp.Solve(s.model)
        return cp.StatusName(status)

    # 1) 모든 룰을 끄고 풀이 (FEASIBLE이어야 정상)
    all_off_status = _solve_with([])
    if all_off_status not in ['OPTIMAL', 'FEASIBLE']:
        # 기본 모델 자체가 INFEASIBLE → 슬롯 부족이 너무 심함
        return {
            'blocking_rules': ['BASE'],
            'rule_descriptions': {'BASE': '기본 슬롯/사람 제약(H1/H2/H3/H5) 자체로 INFEASIBLE — 인원/휴가 조정 필요'},
            'method': 'base_check',
        }

    # 2) 한 룰씩만 켜고 시도 — 어떤 룰이 단독으로 충돌하는지
    single_block = []
    for rname, _ in rule_methods:
        s = _solve_with([rname])
        if s not in ['OPTIMAL', 'FEASIBLE']:
            single_block.append(rname)

    if single_block:
        return {
            'blocking_rules': single_block,
            'rule_descriptions': {r: rule_descriptions.get(r, r) for r in single_block},
            'method': 'single_rule_block',
            'note': '이 룰들은 단독으로도 INFEASIBLE을 유발합니다. (가장 강한 충돌)',
        }

    # 3) 모든 룰을 켜고 풀이 → INFEASIBLE 확인 + 룰 하나씩 빼면서 검사
    all_rules = [r for r, _ in rule_methods]
    full_status = _solve_with(all_rules)
    if full_status in ['OPTIMAL', 'FEASIBLE']:
        return {
            'blocking_rules': [],
            'rule_descriptions': {},
            'method': 'all_feasible',
            'note': '모든 룰을 켜고 풀이했더니 FEASIBLE — 진단 중 다른 영향?',
        }

    # 4) 룰 하나씩 빼며 FEASIBLE이 되는지 확인 → 그 룰이 충돌의 핵심
    contributing = []
    for skip_rule, _ in rule_methods:
        subset = [r for r in all_rules if r != skip_rule]
        s = _solve_with(subset)
        if s in ['OPTIMAL', 'FEASIBLE']:
            contributing.append(skip_rule)

    if contributing:
        return {
            'blocking_rules': contributing,
            'rule_descriptions': {r: rule_descriptions.get(r, r) for r in contributing},
            'method': 'drop_one',
            'note': '이 룰들 중 하나만 빼도 풀이 가능. 즉 이 룰들이 다른 룰과 충돌하는 핵심.',
        }

    # 5) (선택) 룰 2개씩 빼며 시도 — 시간 많이 걸림 (enable_drop_two=True일 때만)
    if not enable_drop_two:
        return {
            'blocking_rules': all_rules,
            'rule_descriptions': rule_descriptions,
            'method': 'drop_one_no_result',
            'note': '룰 하나씩 빼서는 풀이 안 됨. 2개 이상 룰 조합 충돌 가능. "2개 빼기" 옵션 활성화하여 재시도하세요.',
        }
    pair_contributing = []
    for i, (r1, _) in enumerate(rule_methods):
        for r2, _ in rule_methods[i+1:]:
            subset = [r for r in all_rules if r not in [r1, r2]]
            s = _solve_with(subset)
            if s in ['OPTIMAL', 'FEASIBLE']:
                pair_contributing.append((r1, r2))

    if pair_contributing:
        # 최소 충돌 페어 (가장 적은 조합)
        return {
            'blocking_rules': list(set(r for pair in pair_contributing for r in pair)),
            'rule_descriptions': {
                r: rule_descriptions.get(r, r)
                for pair in pair_contributing for r in pair
            },
            'method': 'drop_two',
            'pair_combinations': pair_contributing[:5],  # 처음 5쌍만
            'note': '이 룰들 중 2개를 빼야 풀이 가능. 여러 룰이 복합적으로 충돌.',
        }

    return {
        'blocking_rules': all_rules,
        'rule_descriptions': rule_descriptions,
        'method': 'unknown',
        'note': '3개 이상 룰 조합 충돌 — 데이터 자체가 너무 빡빡한 상태',
    }


def solve_with_auto_multiplier(df_all, residents, leaves, week_count, start_date, holidays,
                                bogeonso_substitutes=None, rad_days=None, student_practices=None,
                                pain_applicants=None, time_limit_sec=60,
                                multipliers=None, manual_multiplier=None,
                                loading_ranges=None, h17_ops=None,
                                max_broken_pairs=5, extra_shift_allowance=0):
    """
    재설계:
      1) manual_multiplier가 주어지면 그 배율 사용. 아니면 사전 진단으로 자동 산출.
      2) 사전 슬롯 부족 검사: 각 날짜별 (빈 슬롯 vs task 수) 계산
         - task 수 > 빈 슬롯인 날짜 → 그 날짜의 차리/판정만 -1 평일 이동 허용
      3) CP-SAT 한 번만 실행 (배율 한 번, shift_allowed_tids 한 번)
      
      manual_multiplier: float or None (None이면 자동 산출)
      
      multipliers 인자는 호환성을 위해 받지만 사용 안 함.
    """
    # 1) 배율 결정: manual 지정 > 자동 산출
    if manual_multiplier is not None:
        auto_mult = float(manual_multiplier)
    else:
        auto_mult = _compute_auto_multiplier(
            df_all, residents, leaves, week_count, start_date, holidays,
            bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
            student_practices=student_practices
        )

    # 2) 사전 슬롯 부족 검사 — 임시 build로 blocked/forced 계산
    pdata_temp = build_problem_data(
        df_all, residents, leaves, week_count, start_date, holidays,
        bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
        student_practices=student_practices, pain_applicants=pain_applicants
    )
    # 날짜별 task 수
    tasks_per_date = {}
    for t in pdata_temp['tasks']:
        tasks_per_date[t['date']] = tasks_per_date.get(t['date'], 0) + 1
    # 날짜별 빈 슬롯 수 (task 받을 수 있는 슬롯 수: blocked 아닌 사람들)
    blocked = pdata_temp['blocked']
    empty_slots_per_date = {}
    persons = pdata_temp['persons']
    for w in range(week_count):
        for d_idx in range(5):
            dt = start_date + timedelta(days=w * 7 + d_idx)
            ds = dt.strftime("%m-%d")
            if ds in holidays:
                continue
            empty = 0
            for p in persons:
                if (p['name'], ds, '오전') not in blocked:
                    empty += 1
                if (p['name'], ds, '오후') not in blocked:
                    empty += 1
            empty_slots_per_date[ds] = empty
    # 슬롯 부족 날짜 = task 수 > 빈 슬롯
    shortage_dates = set()
    for ds, n_tasks in tasks_per_date.items():
        n_slots = empty_slots_per_date.get(ds, 0)
        if n_tasks > n_slots:
            shortage_dates.add(ds)

    # 슬롯 부족 날짜의 차리/판정 task → shortage_shift_tids (항상 이동 허용, 무제한)
    shortage_shift_tids = set()
    if shortage_dates:
        for t in pdata_temp['tasks']:
            if t['date'] not in shortage_dates:
                continue
            tn = t['task']
            if "참관" in tn:
                continue
            if "차리" in tn or "판정" in tn:
                shortage_shift_tids.add(t['task_id'])

    # 추가 -1 이동 허용(extra_shift_allowance>0): 부족이 아니어도 '차리만' 이동 후보로 등록
    # (판정은 제외 — 클리닉 차리/판정도 '판정' 포함이라 제외됨. 실제 추가 이동 수는 솔버에서 캡)
    shift_allowed_tids = set(shortage_shift_tids)
    if extra_shift_allowance and extra_shift_allowance > 0:
        for t in pdata_temp['tasks']:
            tn = t['task']
            if "참관" in tn:
                continue
            if "차리" in tn and "판정" not in tn:  # 순수 차리만 (판정/건증판정/클리닉 차리/판정 제외)
                shift_allowed_tids.add(t['task_id'])

    # 3) CP-SAT 한 번 실행
    pdata = build_problem_data(
        df_all, residents, leaves, week_count, start_date, holidays,
        bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
        student_practices=student_practices, pain_applicants=pain_applicants,
        shift_allowed_tids=shift_allowed_tids
    )
    solver = CPSATScheduleSolver(pdata, target_mult_multiplier=auto_mult,
                                 loading_ranges=loading_ranges, h17_ops=h17_ops,
                                 max_broken_pairs=max_broken_pairs,
                                 shortage_shift_tids=shortage_shift_tids,
                                 extra_shift_limit=extra_shift_allowance)
    solver.build_model()
    result = solver.solve(time_limit_sec=time_limit_sec)

    # 메타데이터 추가
    result['multiplier_used'] = auto_mult
    result['multiplier_history'] = [{
        'multiplier': auto_mult,
        'phase': 1,
        'status': result['status'],
        'unassigned': len(result.get('unassigned', [])),
        'wall_time': result['wall_time_sec'],
    }]
    result['phase_used'] = 1
    result['shortage_dates'] = sorted(shortage_dates)
    result['shortage_info'] = {
        ds: {'tasks': tasks_per_date.get(ds, 0), 'empty_slots': empty_slots_per_date.get(ds, 0)}
        for ds in shortage_dates
    }

    if result['status'] not in ['OPTIMAL', 'FEASIBLE']:
        result['status'] = 'INFEASIBLE_NO_SOLUTION'
        # 자동 진단 제거 — 사용자가 "진단 실행" 버튼으로 수동 실행
    return result


# ============================================================
# 진입점 — app.py에서 호출
# ============================================================

def solve_schedule(df_all, residents, leaves, week_count, start_date, holidays,
                   bogeonso_substitutes=None, rad_days=None, student_practices=None,
                   pain_applicants=None, time_limit_sec=60, manual_multiplier=None,
                   loading_ranges=None, h17_ops=None,
                   max_broken_pairs=5, extra_shift_allowance=0):
    """
    app.py에서 호출하는 진입점.

    manual_multiplier: float or None (None이면 자동, 값 지정하면 그 배율 사용)
    loading_ranges: {0..4: (lo, hi)} or None (None이면 기본 LOADING_RANGES)
    h17_ops: {0..3: '<'/'<='/'='} or None (None이면 모두 '<')
    max_broken_pairs: 깨도 되는 pairing 최대 개수 (기본 5)
    extra_shift_allowance: 슬롯부족이 아니어도 -1 이동 허용할 차리/판정 추가 개수 (기본 0)

    Returns: dict
        - status: "OPTIMAL", "FEASIBLE", "INFEASIBLE_NO_SOLUTION"
        - assignments: {task_id: person_name}
        - unassigned: [task_id, ...]
        - broken_pairs: [pair_id, ...]
        - task_time_overrides: {task_id: '오전' or '오후'}
        - multiplier_used: float
        - wall_time_sec: float
    """
    return solve_with_auto_multiplier(
        df_all, residents, leaves, week_count, start_date, holidays,
        bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
        student_practices=student_practices, pain_applicants=pain_applicants,
        time_limit_sec=time_limit_sec, manual_multiplier=manual_multiplier,
        loading_ranges=loading_ranges, h17_ops=h17_ops,
        max_broken_pairs=max_broken_pairs, extra_shift_allowance=extra_shift_allowance
    )