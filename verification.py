"""
스케줄 검증 모듈
- 사용자가 직접 작성한 정답 목록(EXPECTED_SCHEDULE)을 기준으로
- 실제 생성된 주차별 스케줄과 비교
- 누락/추가 항목을 보고하되, 공휴일/교수휴진이 사유면 자동 안내
"""
import re
from datetime import timedelta, datetime

# ============================================================
# 정답지 (사용자 손으로 직접 작성, 프로그램 표기 기준으로 정리)
# ============================================================
# 각 항목 형식: {"name": "task 이름", "cycle": "매주"/"홀수주"/"짝수주"}
#   - cycle: "매주"면 모든 주차에 있어야 함
#            "홀수주"면 1/3/5주차에만 있어야 함
#            "짝수주"면 2/4주차에만 있어야 함
#            "홀수주_조우현|짝수주_김계형" 같은 특수 케이스도 처리

EXPECTED_SCHEDULE = {
    "월": [
        # 공통
        {"name": "예진", "cycle": "매주"},
        {"name": "처치 (오전)", "cycle": "매주"},
        {"name": "처치 (오후)", "cycle": "매주"},
        # 판정 참관
        {"name": "Pf. 조수환 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 권혁태 판정 참관 (오전)", "cycle": "매주"},
        # 비만클리닉 참관 (권혁태)
        {"name": "Pf. 권혁태 비만클리닉 참관 (오후)", "cycle": "매주"},
        # 건증 판정
        {"name": "Pf. 박민선 건증 판정 (수)", "cycle": "매주"},
        {"name": "Pf. 민경하 건증 판정 (목)", "cycle": "매주"},
        {"name": "Pf. 전혜령 건증 판정 (목)", "cycle": "홀수주", "bw_key": "전혜령|목|오후|건증"},  # 격주(주차 사용자설정)
        # 외래/암외래 참관
        {"name": "Pf. 조비룡 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 윤재문 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 박진호 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 민경하 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김지영 암외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김하진 외래 참관 (오후)", "cycle": "매주"},
        # 차리
        {"name": "Pf. 박민선 외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 박상민 외래 차리 (수)", "cycle": "매주"},
        {"name": "Pf. 박진호 통증클리닉 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 조수환 외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 황서은 암외래 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 김지영 암외래 차리 (수)", "cycle": "매주"},
    ],
    "화": [
        {"name": "예진", "cycle": "매주"},
        {"name": "처치 (오전)", "cycle": "매주"},
        {"name": "처치 (오후)", "cycle": "매주"},
        # 판정 참관
        {"name": "Pf. 조비룡 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 황서은 판정 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김하진 판정 참관 (오후)", "cycle": "매주"},
        # 건증 판정
        {"name": "Pf. 윤재문 건증 판정 (목)", "cycle": "매주"},
        {"name": "Pf. 민경하 건증 판정 (금)", "cycle": "매주"},
        {"name": "Pf. 고아령 건증 판정 (목)", "cycle": "매주"},
        {"name": "Pf. 김하진 건증 판정 (금)", "cycle": "매주"},
        # 참관
        {"name": "Pf. 박민선 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 권혁태 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 조수환 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 김계형 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 민경하 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 민경하 암외래 참관 (오후)", "cycle": "매주"},
        # 차리
        {"name": "Pf. 박상민 외래 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 조비룡 외래 차리 (수)", "cycle": "매주"},
        {"name": "Pf. 윤재문 외래 차리 (금)", "cycle": "매주"},
        {"name": "Pf. 박진호 외래 차리 (금)", "cycle": "매주"},
        {"name": "Pf. 조수환 외래 차리 (수)", "cycle": "매주"},
        {"name": "Pf. 김지영 외래 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 황서은 외래 차리 (금)", "cycle": "매주"},
        {"name": "Pf. 김하진 외래 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 권혁태 외래 차리 (금)", "cycle": "매주"},
    ],
    "수": [
        {"name": "예진", "cycle": "매주"},
        {"name": "처치 (오전)", "cycle": "매주"},
        {"name": "처치 (오후)", "cycle": "매주"},
        # 판정 참관
        {"name": "Pf. 박민선 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 박진호 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 민경하 판정 참관 (오후)", "cycle": "매주"},
        # 조우현(홀)/김계형(짝)은 둘이 나눠 맡는 진료 → 매주 1개 합친 task로 생성
        {"name": "Pf. 조우현(홀)/김계형(짝) 판정 참관 (오후)", "cycle": "매주"},
        # 클리닉 차리/판정
        {"name": "Pf. 조비룡 클리닉 차리/판정 (목)", "cycle": "매주"},
        # 건증 판정
        {"name": "Pf. 윤재문 건증 판정 (금)", "cycle": "매주"},
        {"name": "Pf. 황서은 건증 판정 (금)", "cycle": "매주"},
        {"name": "Pf. 김지영 건증 판정 (금)", "cycle": "매주"},
        {"name": "Pf. 권혁태 건증 판정 (월)", "cycle": "매주"},
        # 참관
        {"name": "Pf. 조비룡 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 박상민 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 황서은 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 황서은 암외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 조수환 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 조우현 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 김지영 암외래 참관 (오전)", "cycle": "매주"},
        # 차리
        {"name": "Pf. 박민선 외래 차리 (목)", "cycle": "매주"},
        {"name": "Pf. 민경하 외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 김하진 암외래 차리 (금)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 차리 (목 오후)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 차리 (목 오전)", "cycle": "매주"},
        {"name": "Pf. 권혁태 비만클리닉 차리 (월)", "cycle": "매주"},
    ],
    "목": [
        {"name": "예진", "cycle": "매주"},
        {"name": "처치 (오전)", "cycle": "매주"},
        {"name": "처치 (오후)", "cycle": "매주"},
        # 판정 참관
        {"name": "Pf. 윤재문 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 고아령 판정 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 전혜령 판정 참관 (오후)", "cycle": "홀수주", "bw_key": "전혜령|목|오후|건증"},  # 격주(주차 사용자설정)
        # 클리닉 차리/판정
        {"name": "Pf. 박민선 클리닉 차리/판정 (월)", "cycle": "매주"},
        # 건증 판정
        {"name": "Pf. 박진호 건증 판정 (수)", "cycle": "매주"},
        {"name": "Pf. 조수환 건증 판정 (월)", "cycle": "매주"},
        {"name": "Pf. 김하진 건증 판정 (화)", "cycle": "매주"},
        # 참관
        {"name": "Pf. 박민선 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 박진호 통증클리닉 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 박상민 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김지영 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김하진 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 조수환 암외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 황서은 암외래 참관 (오전)", "cycle": "매주"},
        # 차리
        {"name": "Pf. 윤재문 외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 박진호 외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 김지영 암외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 민경하 외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 김하진 외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 민경하 암외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 권혁태 외래 차리 (화)", "cycle": "매주"},
    ],
    "금": [
        {"name": "예진", "cycle": "매주"},
        {"name": "처치 (오전)", "cycle": "매주"},
        {"name": "처치 (오후)", "cycle": "매주"},
        # 판정 참관
        {"name": "Pf. 윤재문 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 황서은 판정 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 민경하 판정 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김지영 판정 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김하진 판정 참관 (오후)", "cycle": "매주"},
        # 건증 판정
        {"name": "Pf. 조비룡 건증 판정 (화)", "cycle": "매주"},
        # 조우현(홀)/김계형(짝)은 둘이 나눠 맡는 진료 → 매주 1개 합친 task (건증 판정은 직전 금요일 생성)
        {"name": "Pf. 조우현(홀)/김계형(짝) 건증 판정 (수)", "cycle": "매주"},
        {"name": "Pf. 황서은 건증 판정 (화)", "cycle": "매주"},
        {"name": "Pf. 민경하 건증 판정 (수)", "cycle": "매주"},
        # 참관
        {"name": "Pf. 박진호 외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 윤재문 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 황서은 외래 참관 (오후)", "cycle": "매주"},
        {"name": "Pf. 김하진 암외래 참관 (오전)", "cycle": "매주"},
        {"name": "Pf. 권혁태 외래 참관 (오전)", "cycle": "매주"},
        # 차리
        {"name": "Pf. 조비룡 외래 차리 (월)", "cycle": "매주"},
        {"name": "Pf. 김계형 외래 차리 (화)", "cycle": "매주"},
        {"name": "Pf. 황서은 외래 차리 (수)", "cycle": "매주"},
        {"name": "Pf. 황서은 암외래 차리 (수)", "cycle": "매주"},
        {"name": "Pf. 조우현 외래 차리 (수)", "cycle": "매주"},
    ],
}


def _normalize(name):
    """공백 무시 비교를 위한 정규화"""
    return name.replace(" ", "")


def _is_expected_in_week(item, week_num, biweekly_choice=None):
    """해당 주차에 정답 항목이 있어야 하는지 판정"""
    cycle = item["cycle"]
    if cycle == "매주":
        return True
    is_odd = (week_num % 2 == 1)
    # 단독 격주: 사용자가 주차 설정 팝업에서 고른 주차를 우선 반영
    bw_key = item.get("bw_key")
    if bw_key and biweekly_choice and biweekly_choice.get(bw_key) in ("odd", "even"):
        return is_odd if biweekly_choice[bw_key] == "odd" else (not is_odd)
    if cycle == "홀수주":
        return is_odd
    if cycle == "짝수주":
        return not is_odd
    return True


def _extract_prof(task_name):
    """task 이름에서 교수명 추출 ('Pf. 조비룡 ...' → '조비룡'). 없으면 None"""
    if not task_name.startswith("Pf. "):
        return None
    rest = task_name[4:]  # "조비룡 ..."
    return rest.split(" ")[0]


def _check_exclusion_reason(item, day_date_str, day_name, holidays, off_slots, task_name):
    """
    빠진 항목에 대해 공휴일/교수 휴진 사유인지 자동 판정.
    Returns: 사유 문자열 or None (사유 못 찾으면)
    """
    # 1) 그 날짜가 공휴일?
    if day_date_str in holidays:
        return f"공휴일({day_date_str}) 사유로 제외"

    # 2) 그 task가 어느 교수의 진료 날짜에 만들어지는지 추정
    #    참관/판정 등에서 괄호 안의 요일/시간이 진료 요일을 가리킴
    #    예: "Pf. 박민선 건증 판정 (수)" → 박민선의 수요일 건증 진료가 있어야 정답이 생김
    prof = _extract_prof(task_name)
    if prof is None:
        return None  # 예진/처치 등 공통 task - 위 공휴일에서만 잡힘

    # task 이름의 괄호 안에서 진료 요일 추출
    # 형태: "...(수)", "...(목 오전)", "...(오전)"
    import re
    m = re.search(r"\(([^)]+)\)", task_name)
    if not m:
        return None
    bracket = m.group(1).strip()
    # 첫 토큰이 요일이면 진료 요일, 시간(오전/오후)이면 진료 요일 = 본인 요일과 동일
    weekday_tokens = ["월", "화", "수", "목", "금"]
    if bracket[:1] in weekday_tokens:
        clinic_day = bracket[:1]
    elif bracket in ["오전", "오후"]:
        # 참관 형태: 진료 요일이 task 본인 요일과 같음 (예: 화요일 task의 "오전"은 화요일 오전 진료 참관)
        clinic_day = day_name
    else:
        return None

    # 진료 날짜 계산: 본인(task 발생) 요일 → 진료 요일 차이
    weekday_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
    self_wd = weekday_map.get(day_name)
    clinic_wd = weekday_map.get(clinic_day)
    if self_wd is None or clinic_wd is None:
        return None

    # task 종류 판별: 차리/판정 task는 미래 진료를 준비하는 것이므로 진료 날짜는 항상 task 발생 후
    # 참관 task는 진료 당일이라 같은 주
    is_prep_task = ("차리" in task_name or "판정" in task_name) and "참관" not in task_name

    try:
        self_dt = datetime.strptime(f"2000-{day_date_str}", "%Y-%m-%d")
        delta = clinic_wd - self_wd
        # 차리/판정 task인데 진료 요일이 본인 요일과 같거나 더 빠르면 → 다음 주 진료
        if is_prep_task and delta <= 0:
            delta += 7
        clinic_dt = self_dt + timedelta(days=delta)
        clinic_date_str = clinic_dt.strftime("%m-%d")
    except:
        return None

    # 진료 날짜가 공휴일?
    if clinic_date_str in holidays:
        # 다음 주 진료인지 표시
        next_week_tag = " [다음주]" if (is_prep_task and (clinic_wd - self_wd) <= 0) else ""
        return f"{prof} 교수 {clinic_day}요일({clinic_date_str}){next_week_tag} 공휴일 사유로 제외"

    # 진료 교수 그 날짜 휴진? (반일 휴진 지원: (교수, 날짜, '오전'/'오후'))
    # 합쳐진 격주 교수명 "조우현(홀)/김계형(짝)" → 두 멤버 중 한 명이라도 휴진이면 사유 인정
    if '/' in (prof or ''):
        _members = [re.sub(r'\(.*?\)', '', x).strip() for x in prof.split('/')]
    else:
        _members = [prof]
    for _s in off_slots:
        if not _s or len(_s) < 2:
            continue
        p, d = _s[0], _s[1]
        if p not in _members or d != clinic_date_str:
            continue
        off_time = _s[2] if len(_s) >= 3 else None
        next_week_tag = " [다음주]" if (is_prep_task and (clinic_wd - self_wd) <= 0) else ""
        if off_time in (None, '', '종일'):
            return f"{prof} 교수 {clinic_day}요일({clinic_date_str}){next_week_tag} 휴진 사유로 제외"
        # 반일 휴진은 그 시간대 task만 제외 사유가 된다
        if f"({off_time})" in (task_name or ''):
            return (f"{prof} 교수 {clinic_day}요일({clinic_date_str}){next_week_tag} "
                    f"{off_time} 휴진 사유로 제외")

    return None


def verify_schedule(df_all, week_count, base_date, holidays, off_slots,
                    supplementary_schedules=None, assignments=None,
                    task_date_overrides=None, task_time_overrides=None,
                    shifted_tasks=None, original_df_dates=None,
                    master_schedules=None, skipped_task_ids=None,
                    prev_month_task_ids=None, biweekly_choice=None):
    """
    실제 생성된 df_all을 정답지와 비교 + 미배정 task 탐지.
    
    이동 추적:
      - task_date_overrides: {task_id: new_date_str}  CP-SAT가 -1 평일 이동한 task
      - task_time_overrides: {task_id: '오전'|'오후'}  CP-SAT가 결정한 시간
      - shifted_tasks: [task_id, ...]  date_alt로 이동한 task_id 목록
      - original_df_dates: {task_id: original_date_str}  df_gen 업데이트 전 원래 날짜
    
    Returns: {
        주차번호: {
            요일: {
                "missing": [{"name": ..., "reason": ...}, ...],
                "extra": [{"name": ..., "reason": ...}, ...],
                "moved_in": [{"name": ..., "from_date": ..., "reason": ...}, ...],
                  # 이 날짜로 들어온 task (다른 날짜에서 이동)
                "moved_out": [{"name": ..., "to_date": ..., "reason": ...}, ...],
                  # 이 날짜에서 나간 task
                "unassigned": [task_name, ...],
                "skipped": [task_name, ...],   # 판정참관 제외룰로 '안 하기로 한' task (미배정 아님)
                "total_expected": int,
                "total_present": int,
            }
        }
    }
    """
    if supplementary_schedules is None:
        supplementary_schedules = []
    if assignments is None:
        assignments = {}
    if task_date_overrides is None:
        task_date_overrides = {}
    if task_time_overrides is None:
        task_time_overrides = {}
    if shifted_tasks is None:
        shifted_tasks = []
    if original_df_dates is None:
        original_df_dates = {}
    _skipped_ids = set(skipped_task_ids or [])
    _prev_month_ids = set(prev_month_task_ids or [])

    weekday_names = ["월", "화", "수", "목", "금"]
    result = {}

    # 보충진료 task의 task name set 만들기 (pair_id에 _SUP 포함된 task)
    sup_task_names = set()
    if "pair_id" in df_all.columns:
        sup_rows = df_all[df_all["pair_id"].astype(str).str.contains("_SUP", na=False)]
        for _, r in sup_rows.iterrows():
            sup_task_names.add((r["week"], r["day"], r["task"]))

    # ===== 이동 정보 미리 정리 =====
    # 각 task_id별로 (원래 날짜, 현재 날짜) 매핑
    # date_overrides가 있는 task는 cpsat -1 이동
    # 원래 date는 original_df_dates 또는 df_all['date']에서 추정
    weekday_kor = ['월', '화', '수', '목', '금', '토', '일']

    def _date_to_day(ds, year):
        try:
            dt = datetime.strptime(f"{year}-{ds}", "%Y-%m-%d").date()
            return weekday_kor[dt.weekday()]
        except Exception:
            return None

    # task_id → (원래 date, 현재 date, 이동 이유)
    move_info = {}  # {task_id: {'from': date_str, 'to': date_str, 'from_day': '월', 'to_day': '화', 'reason': '...'}}
    year = base_date.year
    for tid, new_date in task_date_overrides.items():
        orig = original_df_dates.get(tid)
        if orig is None or orig == new_date:
            continue
        move_info[tid] = {
            'from': orig,
            'to': new_date,
            'from_day': _date_to_day(orig, year),
            'to_day': _date_to_day(new_date, year),
            'reason': '슬롯 부족으로 -1 평일 이동',
        }

    # 추가로 df_all의 모든 차리/판정에 대해, 원래 master schedule 위치 vs 현재 date 확인
    # → 공휴일로 인한 자동 이동 (utils.generate_schedule이 이미 -2일 처리한 경우)
    # 이건 일종의 "원래 다른 날짜 정답인데 공휴일 때문에 이 날짜로 와있는 task"
    # task name에서 "(요일)" 추출해서 비교
    import re

    def _extract_target_day(task_name):
        """task name에서 (요일) 또는 (X 오전) 패턴 추출"""
        m = re.search(r'\(([월화수목금])\s*(?:오전|오후)?\)', task_name)
        if m:
            return m.group(1)
        return None

    for _, row in df_all.iterrows():
        tid = row['task_id']
        if tid in move_info:
            continue  # 이미 cpsat 이동으로 처리
        task = row['task']
        cur_day = row['day']
        cur_date = row['date']
        # 차리/판정만 (참관/처치/예진 제외)
        if "참관" in task or task in ['예진', '처치 (오전)', '처치 (오후)']:
            continue
        target_day = _extract_target_day(task)
        if target_day is None:
            continue
        # 차리: target_day 진료를 위한 차리 → 보통 target_day의 -1 평일에 생성
        # 판정: target_day 진료 → 보통 같은 날 또는 다음 평일
        # 룰: 차리 = target_day - 1평일 (월 차리는 직전 금)
        # 만약 현재 위치(cur_day)가 그 규칙 위치가 아니면 → 공휴일 이동
        if "차리" in task:
            # 원래 위치 = target_day의 -1 평일
            day_idx = {"월":0,"화":1,"수":2,"목":3,"금":4}.get(target_day)
            if day_idx is None: continue
            expected_prev_idx = (day_idx - 1) % 5
            expected_prev_day = ["월","화","수","목","금"][expected_prev_idx]
            if cur_day != expected_prev_day:
                # 공휴일 이동 추정
                move_info[tid] = {
                    'from': None,  # 원래 (cur 날짜와 같은 주의 expected_prev_day) — 정확히는 모르므로 None
                    'from_day': expected_prev_day,
                    'to': cur_date,
                    'to_day': cur_day,
                    'reason': f'공휴일로 인해 원래 {expected_prev_day}요일에서 {cur_day}요일로 이동',
                }

    # ===== 규칙 설정(master_schedules) 변경 반영 (공휴일/휴진보다 우선 확인) =====
    # 현재 규칙과 기본 규칙(RAW_SCHEDULES_INITIAL)으로 각각 스케줄을 생성(공휴일/휴진/보충 제외)하여
    # 사용자가 '규칙 설정' 탭에서 추가/제외한 진료를 (주차,요일)별 task 이름 차이로 식별.
    #   removed_by_wd[(week, day)]: 기본엔 있었으나 현재 규칙에서 빠진 task (정규화 이름) → '규칙설정 제외'
    #   added_by_wd[(week, day)]  : 기본엔 없었으나 현재 규칙에서 추가된 task          → '규칙설정 추가'
    removed_by_wd = {}
    added_by_wd = {}
    if master_schedules is not None:
        try:
            import pandas as _pd
            from utils import generate_schedule as _gen, RAW_SCHEDULES_INITIAL as _RAW
            _cols = ["교수명", "요일", "시간", "진료명", "주기", "차리생성", "참관생성", "태그"]
            _base_master = _pd.DataFrame(_RAW, columns=_cols)
            _cur_df = _gen(base_date, week_count, [], master_schedules, [], supplementary_schedules=[])
            _base_df = _gen(base_date, week_count, [], _base_master, [], supplementary_schedules=[])

            def _names_by_wd(_df):
                d = {}
                if _df is None or _df.empty:
                    return d
                for _, rr in _df.iterrows():
                    d.setdefault((rr["week"], rr["day"]), set()).add(_normalize(rr["task"]))
                return d
            _cur_names = _names_by_wd(_cur_df)
            _base_names = _names_by_wd(_base_df)
            for key in (set(_cur_names) | set(_base_names)):
                cur_s = _cur_names.get(key, set())
                base_s = _base_names.get(key, set())
                removed_by_wd[key] = base_s - cur_s
                added_by_wd[key] = cur_s - base_s
        except Exception:
            removed_by_wd = {}
            added_by_wd = {}

    for week in range(1, week_count + 1):
        result[week] = {}
        for d_idx, day_name in enumerate(weekday_names):
            day_date = base_date + timedelta(days=(week - 1) * 7 + d_idx)
            day_date_str = day_date.strftime("%m-%d")

            # 실제 생성된 task 목록 (해당 주차/요일)
            day_df = df_all[(df_all["week"] == week) & (df_all["day"] == day_name)]
            actual_tasks = day_df["task"].tolist()
            actual_set_norm = {_normalize(t): t for t in actual_tasks}

            # 정답 목록 중 이 주차에 있어야 하는 것들
            expected_items = [item for item in EXPECTED_SCHEDULE.get(day_name, []) if _is_expected_in_week(item, week, biweekly_choice)]
            expected_set_norm = {_normalize(item["name"]): item for item in expected_items}

            # 이 날짜로 들어온 task (이동) — 원래 다른 날짜에 있던 task가 여기로 옴
            moved_in = []
            moved_in_task_names = set()
            for _, row in day_df.iterrows():
                tid = row['task_id']
                if tid in move_info:
                    mi = move_info[tid]
                    if mi['to'] == day_date_str:
                        moved_in.append({
                            'name': row['task'],
                            'from_date': mi['from'],
                            'from_day': mi['from_day'],
                            'reason': mi['reason'],
                        })
                        moved_in_task_names.add(_normalize(row['task']))

            # 이 날짜에서 나간 task (이동) — 원래 정답에 있어야 하는데 다른 날짜로 옮긴 것
            moved_out = []
            moved_out_norms = set()
            # day_date_str 또는 day_name이 원래 위치인 task가 다른 곳으로 이동한 케이스
            for tid, mi in move_info.items():
                if mi['from'] == day_date_str or (mi['from'] is None and mi['from_day'] == day_name):
                    # 이 날짜가 원래 위치 — 어디로 갔는지
                    task_row = df_all[df_all['task_id'] == tid]
                    if not task_row.empty:
                        task_name = task_row.iloc[0]['task']
                        moved_out.append({
                            'name': task_name,
                            'to_date': mi['to'],
                            'to_day': mi['to_day'],
                            'reason': mi['reason'],
                        })
                        moved_out_norms.add(_normalize(task_name))

            # 빠진 항목 (정답에는 있는데 실제엔 없음)
            missing = []
            for norm, item in expected_set_norm.items():
                if norm not in actual_set_norm:
                    # 이미 이동된 task로 추적된 경우 skip
                    if norm in moved_out_norms:
                        continue
                    # (1순위) 규칙설정에서 제외된 진료인지 먼저 확인 — 공휴일/휴진보다 우선
                    if norm in removed_by_wd.get((week, day_name), set()):
                        missing.append({"name": item["name"], "reason": "규칙 설정에서 제외된 진료"})
                        continue
                    reason = _check_exclusion_reason(item, day_date_str, day_name, holidays, off_slots, item["name"])
                    missing.append({"name": item["name"], "reason": reason})

            # 추가 항목 (정답에 없는데 실제엔 있음)
            extra = []
            for norm, original in actual_set_norm.items():
                if norm not in expected_set_norm:
                    # 이미 이동된 task로 추적된 경우 skip
                    if norm in moved_in_task_names:
                        continue
                    # (1순위) 규칙설정에서 추가된 진료인지 먼저 확인
                    if norm in added_by_wd.get((week, day_name), set()):
                        extra.append({"name": original, "reason": "규칙 설정에서 추가된 진료"})
                    elif (week, day_name, original) in sup_task_names:
                        extra.append({"name": original, "reason": "보충진료 추가에 의한 task"})
                    else:
                        extra.append({"name": original, "reason": None})

            # 미배정 task 탐지:
            #   - 제외룰로 '안 하기로 한' 판정참관 → skipped
            #   - 이전 달 참관(orphan) 중 배정 안 한 것 → prev_skipped
            #   - 그 외 → unassigned (진짜 미배정)
            unassigned = []
            skipped = []
            prev_skipped = []
            for _, row in day_df.iterrows():
                tid = row["task_id"]
                assignee = assignments.get(tid, "")
                if not assignee:
                    if tid in _prev_month_ids:
                        prev_skipped.append(row["task"])
                    elif tid in _skipped_ids:
                        skipped.append(row["task"])
                    else:
                        unassigned.append(row["task"])

            result[week][day_name] = {
                "date": day_date_str,
                "missing": missing,
                "extra": extra,
                "moved_in": moved_in,
                "moved_out": moved_out,
                "unassigned": unassigned,
                "skipped": skipped,
                "prev_skipped": prev_skipped,
                "total_expected": len(expected_items),
                "total_present": len(actual_tasks),
            }

    return result