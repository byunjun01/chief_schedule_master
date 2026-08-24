import pandas as pd
import random
from datetime import timedelta, datetime

PROF_ORDER = ["조비룡", "박민선", "박진호", "권혁태", "박상민", "윤재문", "황서은", "조수환", "민경하", "김지영", "김하진", "고아령", "김계형", "조우현", "전혜령"]

def get_task_style(task_name):
    if not task_name: return "white", "black"
    if "학생실습" in task_name: return "#FDEBD0", "black"
    if any(kw in task_name for kw in ["연보", "연건 보건소"]): return "#FF85FF", "black"
    if "예진" in task_name: return "#CCCCFF", "black"
    if "처치" in task_name: return "#DDEBF7", "black"
    # 통증클리닉/비만클리닉 참관은 외래참관과 동일 색(#FBE5D7). "클리닉 참관"보다 먼저 매칭되어야 함
    if any(kw in task_name for kw in ["외래 참관", "통증클리닉 참관", "비만클리닉 참관"]): return "#FBE5D7", "black"
    if any(kw in task_name for kw in ["판정 참관", "건증 참관", "클리닉 참관"]): return "#F2CEF0", "black"
    if "건증 판정" in task_name or (any(p in task_name for p in ["조비룡", "박민선"]) and "클리닉 판정" in task_name): return "#E2F0D9", "black"
    if any(kw in task_name for kw in ["외래 차리", "통증클리닉 차리", "차리"]): return "#FFF2CC", "black"
    return "white", "black"

def get_prof_raw_style(clinic_name, is_off, is_holiday, is_skip,
                       prof=None, has_chari=True, has_chamgwan=True):
    """교수별 시간표의 셀 색.
    has_chari/has_chamgwan: master_schedules의 '차리생성'/'참관생성' 플래그.
    둘 다 False이면 task가 생성되지 않으므로 흰배경 (재택외래 등).
    """
    if is_holiday: return "#D3D3D3", "black", "none"
    if is_off: return "#FADBD8", "#C0392B", "none"
    if is_skip: return "#FFFFFF", "#AAAAAA", "1px dashed #CCCCCC"
    # 차리/참관 둘 다 미생성 → task 0개 → 흰배경
    if not has_chari and not has_chamgwan:
        return "white", "black", "none"
    # 진료명이 '클리닉'/'통증클리닉' 자체인 경우만 클리닉 색
    if "클리닉" in clinic_name or "통증" in clinic_name:
        return "#FFF2CC", "black", "none"
    if "판정" in clinic_name and "건증" not in clinic_name:
        return "#FFF2CC", "black", "none"   # 단독 판정 (민경하 등)
    if "건증" in clinic_name:
        return "#FFD966", "black", "none"
    if "암외래" in clinic_name or "외래" in clinic_name:
        if has_chari and has_chamgwan:
            return "#70AD47", "black", "none"   # 차리+참관
        return "#D9EAD3", "black", "none"        # 차리만 또는 참관만
    return "white", "black", "none"

RAW_SCHEDULES_INITIAL = [
    ("조비룡", "월", "오전", "외래", "매주", True, True, None), ("조비룡", "화", "오전", "건증", "매주", True, True, None),
    ("조비룡", "수", "오전", "외래", "매주", True, True, None), ("조비룡", "목", "오후", "클리닉", "매주", True, False, None),
    ("박민선", "월", "오후", "클리닉", "매주", True, False, None), ("박민선", "화", "오전", "외래", "매주", True, True, None),
    ("박민선", "수", "오전", "건증", "매주", True, True, None), ("박민선", "목", "오전", "외래", "매주", True, True, None),
    ("박진호", "월", "오후", "외래", "매주", True, True, None), ("박진호", "수", "오전", "건증", "매주", True, True, None),
    ("박진호", "목", "오후", "통증클리닉", "매주", True, True, None), ("박진호", "금", "오전", "외래", "매주", True, True, None),
    ("권혁태", "화", "오전", "외래", "매주", True, True, None), ("권혁태", "금", "오전", "외래", "매주", True, True, None),
    ("권혁태", "월", "오전", "건증", "매주", True, True, None), ("권혁태", "월", "오후", "비만클리닉", "매주", True, True, None),
    ("박상민", "수", "오후", "외래", "매주", True, True, None), ("박상민", "목", "오전", "외래", "매주", True, True, None),
    ("윤재문", "월", "오전", "외래", "매주", True, True, None), ("윤재문", "목", "오전", "건증", "매주", True, True, None),
    ("윤재문", "금", "오전", "건증", "매주", True, True, None), ("윤재문", "금", "오후", "외래", "매주", True, True, None),
    ("황서은", "화", "오후", "건증", "매주", True, True, None), ("황서은", "수", "오전", "외래", "매주", True, True, None),
    ("황서은", "수", "오후", "암외래", "매주", True, True, None), ("황서은", "목", "오전", "암외래", "매주", True, True, None),
    ("황서은", "금", "오전", "건증", "매주", True, True, None), ("황서은", "금", "오후", "외래", "매주", True, True, None),
    ("조수환", "월", "오전", "건증", "매주", True, True, None), ("조수환", "화", "오전", "암외래", "매주", True, True, None),
    ("조수환", "화", "오후", "외래", "매주", True, True, None), ("조수환", "수", "오후", "외래", "매주", True, True, None),
    ("조수환", "목", "오전", "암외래", "매주", True, True, None), ("조수환", "목", "오후", "암외래", "매주", True, True, None),
    ("민경하", "월", "오후", "외래", "매주", True, True, None), ("민경하", "화", "오전", "외래", "매주", True, True, None),
    ("민경하", "화", "오후", "암외래", "매주", True, True, None), ("민경하", "수", "오후", "건증", "매주", True, True, None),
    ("민경하", "목", "오전", "건증", "매주", True, False, "민경하_특수"), ("민경하", "금", "오후", "건증", "매주", True, True, None),
    ("김지영", "월", "오후", "암외래", "매주", True, True, None), ("김지영", "화", "오전", "관악", "매주", False, False, None),
    ("김지영", "화", "오후", "관악", "매주", False, False, None), ("김지영", "수", "오전", "암외래", "매주", True, True, None),
    ("김지영", "목", "오후", "외래", "매주", True, True, None), ("김지영", "금", "오후", "건증", "매주", True, True, None),
    ("김하진", "월", "오후", "외래", "매주", True, True, None),
    ("김하진", "화", "오후", "건증", "매주", True, True, None), ("김하진", "목", "오후", "외래", "매주", True, True, None),
    ("김하진", "금", "오전", "암외래", "매주", True, True, None), ("김하진", "금", "오후", "건증", "매주", True, True, None),
    ("고아령", "목", "오후", "건증", "매주", True, True, None), ("고아령", "금", "오전", "외래", "매주", False, False, None),
    ("김계형", "월", "오후", "재택외래", "매주", False, False, None), ("김계형", "화", "오후", "외래", "매주", True, True, None),
    ("김계형", "수", "오후", "건증", "짝수주", True, True, None), ("김계형", "목", "오전", "재택외래", "매주", False, False, None),
    ("김계형", "목", "오후", "재택외래", "매주", False, False, None),
    ("조우현", "화", "오후", "재택외래", "매주", False, False, None), ("조우현", "수", "오전", "외래", "매주", True, True, None),
    ("조우현", "수", "오후", "건증", "홀수주", True, True, None), ("조우현", "금", "오전", "재택외래", "매주", False, False, None),
    ("전혜령", "화", "오후", "외래", "매주", False, False, None), ("전혜령", "목", "오전", "재택외래", "매주", False, False, None),
    ("전혜령", "목", "오후", "건증", "홀수주", True, True, None), ("전혜령", "금", "오후", "재택외래", "매주", False, False, None)
]

def find_nearest_working_day(dt, holidays):
    curr = dt
    while curr.weekday() >= 5 or curr.strftime("%m-%d") in holidays:
        curr -= timedelta(days=1)
    return curr

def get_prep_dt(target_date, prof, t_name, clinic, orig_day, holidays):
    def sub_days_skip_weekends(dt, d):
        curr = dt
        while d > 0:
            curr -= timedelta(days=1)
            if curr.weekday() < 5: d -= 1
        return curr
    forced_time, shift = None, 0
    if prof == "박진호":
        if orig_day == "월" and "외래" in clinic: target_prep = target_date - timedelta(days=4)
        elif orig_day == "목" and "통증" in clinic: target_prep = target_date - timedelta(days=3)
        elif orig_day == "금" and "외래" in clinic: target_prep = target_date - timedelta(days=3)
        elif orig_day == "수" and "건증" in clinic: target_prep = target_date - timedelta(days=6)
        else: target_prep = target_date
    elif prof == "권혁태":
        # 화(오전) 참관 → 그 전주 목요일 차리 (5일 전)
        # 금(오전) 참관 → 같은 주 화요일 차리 (3일 전)
        # 월(오전) 건증 참관 → 그 전주 수요일 판정 (5일 전)
        # 월(오후) 비만클리닉 참관 → 그 전주 수요일 차리 (5일 전)
        if orig_day == "화" and "외래" in clinic: target_prep = target_date - timedelta(days=5)
        elif orig_day == "금" and "외래" in clinic: target_prep = target_date - timedelta(days=3)
        elif orig_day == "월" and "건증" in clinic: target_prep = target_date - timedelta(days=5)
        elif orig_day == "월" and "비만" in clinic: target_prep = target_date - timedelta(days=5)
        else: target_prep = target_date
    elif prof in ["고아령", "김지영", "박상민"]: shift = 2
    elif prof == "윤재문":
        # 외래 차리 + 금요일 진료 조합만 shift=3 (금→화), 그 외는 모두 shift=2
        if "차리" in t_name and orig_day == "금": shift = 3
        else: shift = 2
    elif prof == "민경하": shift = 3
    elif prof == "황서은": shift = 3 if "차리" in t_name else 2
    elif prof == "김하진": shift = 2 if "차리" in t_name else 3
    elif prof == "조수환": shift, forced_time = (2, "오전") if "판정" in t_name else (1, None)
    elif prof == "김계형":
        # 판정+수요일은 shift=3 (건증 판정 (수→직전주 금)), 외래 차리(화→직전주 금)는 shift=2, 나머지는 1
        if "판정" in t_name and orig_day == "수": shift = 3
        elif "차리" in t_name and orig_day == "화": shift = 2
        else: shift = 1
    elif prof in ["조비룡", "박민선"]:
        if prof == "조비룡" and "판정" in t_name and orig_day == "화": shift = 2
        elif prof == "박민선" and "판정" in t_name and "건증" in clinic and orig_day == "수": shift = 2
        elif prof == "박민선" and "클리닉" in clinic and orig_day == "월": shift = 2  # 클리닉 차리/판정 (월→직전주 목)
        else: shift = 1
    elif prof == "조우현": shift = 3
    elif prof == "전혜령": shift = 3 if "판정" in t_name else 2
    else: shift = 0
    if shift > 0: target_prep = sub_days_skip_weekends(target_date, shift)
    elif prof not in ("박진호", "권혁태"): target_prep = target_date
    return find_nearest_working_day(target_prep, holidays), forced_time

def is_prof_off(off_slots, prof, date_str, time=None):
    """교수 휴진 여부. off_slots 항목은 두 가지 형태를 모두 허용한다.
      (교수, 'MM-DD')            → 그날 종일 휴진 (기존 형식, 하위호환)
      (교수, 'MM-DD', '오전')     → 그날 오전만 휴진
      (교수, 'MM-DD', '종일')     → 그날 종일 휴진
    time=None이면 '종일 휴진일 때만' True (반일 휴진은 해당 시간대를 물어봐야 알 수 있음).
    """
    if not off_slots:
        return False
    for s in off_slots:
        if not s or len(s) < 2:
            continue
        if s[0] != prof or s[1] != date_str:
            continue
        slot_time = s[2] if len(s) >= 3 else None
        if slot_time in (None, '', '종일'):
            return True                 # 종일 휴진
        if time is not None and slot_time == time:
            return True                 # 해당 반일만 휴진
    return False


def biweekly_week_active(cycle, week_num, bw_key=None, biweekly_choice=None):
    """격주(홀수주/짝수주) 진료가 해당 주차에 활성인지 판정.
    - 단독 격주: biweekly_choice[bw_key]('odd'/'even')가 있으면 그 선택을 우선.
    - 둘이 나눠 맡는 슬롯(합친 진료)의 bw_key는 biweekly_choice에 없으므로 라벨 기본값 사용.
    """
    if cycle == "매주":
        return True
    is_odd = (week_num % 2 == 1)
    if bw_key and biweekly_choice and biweekly_choice.get(bw_key) in ("odd", "even"):
        return is_odd if biweekly_choice[bw_key] == "odd" else (not is_odd)
    if cycle == "홀수주":
        return is_odd
    if cycle == "짝수주":
        return not is_odd
    return True


def generate_schedule(start_date, total_weeks, holidays, master_df, off_slots, supplementary_schedules=None,
                      biweekly_choice=None):
    """
    supplementary_schedules: list of dict
        [{"교수": "박상민", "날짜": "06-15", "시간": "오전", "진료명": "외래"}, ...]
        단발성 보충진료. 마스터 스케줄의 매주 진료와 동일한 방식으로 차리/판정/참관이 자동 생성됨.
    biweekly_choice: dict, 단독 격주 진료의 생성 주차 선택.
        key = "교수|요일|시간|진료명", value = 'odd'(1·3·5주차) / 'even'(2·4주차).
        없으면 라벨 기본값(홀수주→odd, 짝수주→even) 사용.
    """
    if supplementary_schedules is None:
        supplementary_schedules = []
    if biweekly_choice is None:
        biweekly_choice = {}
    weekday_names = ["월", "화", "수", "목", "금"]

    # === 격주(홀수주/짝수주) 진료 사전 분석 ===
    #  - 같은 (요일,시간,진료명) 슬롯에 홀수주+짝수주 서로 다른 교수가 있으면 → 둘이 나눠 맡는 진료.
    #    매주 1개의 합친 task로 생성하고 이름에 (홀)/(짝) 라벨을 붙임 (사용자가 주차 보고 담당 확인).
    #    준비일(판정)은 홀수주 대표교수 기준으로 계산 → get_prep_dt 그대로 사용.
    #  - 짝이 없는 단독 격주는 biweekly_choice로 생성 주차를 정함 (없으면 라벨 기본값).
    _biweekly_groups = {}
    for _, _r in master_df.iterrows():
        if pd.isna(_r.get("교수명")) or not str(_r.get("교수명")).strip():
            continue
        _cyc = str(_r["주기"])
        if _cyc in ("홀수주", "짝수주"):
            _k = (str(_r["요일"]), str(_r["시간"]), str(_r["진료명"]) if pd.notna(_r["진료명"]) else "")
            _biweekly_groups.setdefault(_k, {})[_cyc] = str(_r["교수명"])
    # 둘이 나눠 맡는 슬롯: 홀·짝 둘 다 존재
    _shared_slots = {k: v for k, v in _biweekly_groups.items() if "홀수주" in v and "짝수주" in v}
    display_end_date = start_date + timedelta(days=total_weeks*7 - 1)
    full_data = []

    def _generate_tasks_for_clinic_session(current_date, prof, time, clinic, d_name, week_num, is_supplementary=False):
        """단일 진료 세션에 대한 차리/판정/참관 task들을 생성하여 full_data에 추가
        is_supplementary=True인 경우: 차리/판정 위치는 단순화하여 -2영업일 (요청에 따라 B안)
        """
        date_str = current_date.strftime("%m-%d")
        is_hc = "건증" in clinic
        # 비만클리닉은 이름만 클리닉이고 실제는 외래처럼 동작 (차리+참관 세트)
        is_cl = "클리닉" in clinic and "비만" not in clinic
        sup_tag = "_SUP" if is_supplementary else ""
        pair_base_id = f"{week_num}_{d_name}_{prof}_{clinic}_{date_str}{sup_tag}"
        task_types = []
        if is_hc or is_cl:
            task_types.append(("판정", True))
            task_types.append(("판정 참관", False))
        else:
            task_types.append(("차리", True))
            task_types.append(("외래 참관", False))
        for t_name, is_prep in task_types:
            if is_prep:
                if is_supplementary:
                    # 보충진료는 일괄 -2영업일에 차리/판정 생성 (요일별 세밀한 shift 적용 안 함)
                    def sub_days_skip_weekends(dt, d):
                        curr = dt
                        while d > 0:
                            curr -= timedelta(days=1)
                            if curr.weekday() < 5: d -= 1
                        return curr
                    prep_dt = sub_days_skip_weekends(current_date, 2)
                    prep_dt = find_nearest_working_day(prep_dt, holidays)
                    forced_time = None
                else:
                    prep_dt, forced_time = get_prep_dt(current_date, prof, t_name, clinic, d_name, holidays)
                if start_date <= prep_dt <= display_end_date:
                    p_date_str = prep_dt.strftime("%m-%d")
                    if p_date_str not in holidays:
                        p_week = (prep_dt - start_date).days // 7 + 1
                        f_time = forced_time if forced_time else time
                        t_suffix = "판정" if (is_hc or is_cl) else "차리"
                        if prof in ["조비룡", "박민선"] and is_cl: t_suffix = "차리/판정"
                        if prof == "박진호" and "통증클리닉" in clinic: t_suffix = "차리"
                        if prof == "조수환" and "암외래" in clinic:
                            day_info = f"({d_name})" if d_name == "화" else f"({d_name} {time})"
                        else: day_info = f"({d_name})"
                        f_task = f"Pf. {prof} {clinic} {t_suffix} {day_info}".replace("외래 외래", "외래").replace("  ", " ").strip()
                        full_data.append({"date": p_date_str, "week": p_week, "day": weekday_names[prep_dt.weekday()], "time": f_time, "prof": prof, "task": f_task, "pair_id": pair_base_id})
            elif not is_prep and current_date <= display_end_date:
                if prof == "박진호" and "통증클리닉" in clinic:
                    f_task = f"Pf. {prof} 통증클리닉 참관 ({time})".replace("  ", " ").strip()
                elif "비만클리닉" in clinic:
                    f_task = f"Pf. {prof} 비만클리닉 참관 ({time})".replace("  ", " ").strip()
                elif is_hc or is_cl:
                    f_task = f"Pf. {prof} 판정 참관 ({time})".replace("  ", " ").strip()
                else:
                    f_task = f"Pf. {prof} {clinic} 외래 참관 ({time})".replace("외래 외래", "외래").replace("  ", " ").strip()
                full_data.append({"date": date_str, "week": week_num, "day": d_name, "time": time, "prof": prof, "task": f_task, "pair_id": pair_base_id})

    for w_idx in range(total_weeks + 1):
        week_num = w_idx + 1
        for d_idx, d_name in enumerate(weekday_names):
            current_date = start_date + timedelta(days=(w_idx * 7) + d_idx)
            date_str = current_date.strftime("%m-%d")
            if current_date <= display_end_date and date_str not in holidays:
                full_data.append({"date": date_str, "week": week_num, "day": d_name, "time": "오전", "prof": "공통", "task": "예진", "pair_id": ""})
                full_data.append({"date": date_str, "week": week_num, "day": d_name, "time": "오전", "prof": "공통", "task": "처치 (오전)", "pair_id": ""})
                full_data.append({"date": date_str, "week": week_num, "day": d_name, "time": "오후", "prof": "공통", "task": "처치 (오후)", "pair_id": ""})
            for _, row in master_df.iterrows():
                if pd.isna(row["교수명"]) or not str(row["교수명"]).strip(): continue
                prof = str(row["교수명"])
                day = str(row["요일"])
                time = str(row["시간"])
                clinic = str(row["진료명"]) if pd.notna(row["진료명"]) else ""
                cycle = str(row["주기"])
                gen_chair = bool(row["차리생성"])
                gen_obs = bool(row["참관생성"])
                if day != d_name: continue
                # gen_prof: task 이름에 쓸 교수명 (합친 격주 진료는 라벨명으로 대체, 그 외엔 원래 교수명)
                gen_prof = prof
                off_check_prof = prof   # 휴진 체크 대상 (공유 격주는 그 주 실제 담당자로 교체)
                if cycle in ("홀수주", "짝수주"):
                    _slot = (day, time, clinic)
                    if _slot in _shared_slots:
                        # 둘이 나눠 맡는 진료 → 짝수주 멤버 행은 건너뛰고, 홀수주 멤버가 대표로 매주 생성
                        if cycle == "짝수주":
                            continue
                        _odd_p = _shared_slots[_slot]["홀수주"]
                        _even_p = _shared_slots[_slot]["짝수주"]
                        gen_prof = f"{_odd_p}(홀)/{_even_p}(짝)"
                        # 이번 달 실제 담당: biweekly_choice['{홀라벨교수}|요일|시간|진료명']
                        #   'odd'(기본) = 홀라벨 교수가 1·3·5주 / 'even' = 홀라벨 교수가 2·4주(→짝라벨이 1·3·5)
                        _sh_choice = biweekly_choice.get(f"{_odd_p}|{day}|{time}|{clinic}")
                        _odd_on_135 = (_sh_choice != 'even')
                        _is_odd_week = (week_num % 2 == 1)
                        off_check_prof = _odd_p if (_is_odd_week == _odd_on_135) else _even_p
                        # (주차 필터 없이 매주 생성하되, 그 주 담당자가 휴진이면 아래에서 스킵)
                    else:
                        # 단독 격주 → 사용자 선택 주차 (없으면 라벨 기본값: 홀수주→odd, 짝수주→even)
                        if not biweekly_week_active(cycle, week_num, f"{prof}|{day}|{time}|{clinic}", biweekly_choice):
                            continue
                if date_str in holidays: continue
                if is_prof_off(off_slots, off_check_prof, date_str, time): continue
                is_hc = "건증" in clinic
                # 비만클리닉은 이름만 클리닉이고 실제는 외래처럼 동작
                is_cl = "클리닉" in clinic and "비만" not in clinic
                pair_base_id = f"{week_num}_{d_name}_{gen_prof}_{clinic}"
                task_types = []
                if is_hc or is_cl:
                    task_types.append(("판정", True))
                    task_types.append(("판정 참관", False))
                else:
                    task_types.append(("차리", True))
                    task_types.append(("외래 참관", False))
                for t_name, is_prep in task_types:
                    if is_prep and gen_chair:
                        prep_dt, forced_time = get_prep_dt(current_date, prof, t_name, clinic, d_name, holidays)
                        if start_date <= prep_dt <= display_end_date:
                            p_date_str = prep_dt.strftime("%m-%d")
                            if p_date_str not in holidays:
                                p_week = (prep_dt - start_date).days // 7 + 1
                                f_time = forced_time if forced_time else time
                                t_suffix = "판정" if (is_hc or is_cl) else "차리"
                                if prof in ["조비룡", "박민선"] and is_cl: t_suffix = "차리/판정"
                                if prof == "박진호" and "통증클리닉" in clinic: t_suffix = "차리"
                                if prof == "조수환" and "암외래" in clinic:
                                    day_info = f"({day})" if day == "화" else f"({day} {time})"
                                else: day_info = f"({day})"
                                f_task = f"Pf. {gen_prof} {clinic} {t_suffix} {day_info}".replace("외래 외래", "외래").replace("  ", " ").strip()
                                full_data.append({"date": p_date_str, "week": p_week, "day": weekday_names[prep_dt.weekday()], "time": f_time, "prof": gen_prof, "task": f_task, "pair_id": pair_base_id})
                    elif not is_prep and gen_obs and current_date <= display_end_date:
                        # 참관 task 이름 규칙:
                        #  - 박진호 통증클리닉: "Pf. 박진호 통증클리닉 참관 (오전/오후)" (가장 먼저 체크)
                        #  - 비만클리닉: "Pf. {교수} 비만클리닉 참관 (오전/오후)" (외래처럼 동작하지만 이름은 클리닉)
                        #  - 판정 참관(건증/그 외 클리닉): 진료명 제거 → "Pf. {교수} 판정 참관 (오전/오후)"
                        #  - 외래 참관: 진료명 유지 → "Pf. {교수} {진료명} 참관 (오전/오후)" ("외래 외래"는 "외래"로)
                        if prof == "박진호" and "통증클리닉" in clinic:
                            f_task = f"Pf. {gen_prof} 통증클리닉 참관 ({time})".replace("  ", " ").strip()
                        elif "비만클리닉" in clinic:
                            f_task = f"Pf. {gen_prof} 비만클리닉 참관 ({time})".replace("  ", " ").strip()
                        elif is_hc or is_cl:
                            f_task = f"Pf. {gen_prof} 판정 참관 ({time})".replace("  ", " ").strip()
                        else:
                            f_task = f"Pf. {gen_prof} {clinic} 외래 참관 ({time})".replace("외래 외래", "외래").replace("  ", " ").strip()
                        full_data.append({"date": date_str, "week": week_num, "day": d_name, "time": time, "prof": gen_prof, "task": f_task, "pair_id": pair_base_id})

    # === [신규] 보충진료 처리 ===
    # 단발성 진료 세션을 받아서 마스터와 동일한 방식으로 차리/판정/참관 자동 생성
    # 표시 범위(display_end_date)를 넘어가는 다음 주 보충진료도 처리 (차리/판정 생성을 위해 +1주까지 허용)
    extended_end_date = display_end_date + timedelta(days=7)
    for sup in supplementary_schedules:
        prof = sup.get("교수", "").strip()
        date_str_sup = sup.get("날짜", "").strip()
        time_sup = sup.get("시간", "").strip()
        clinic_sup = sup.get("진료명", "").strip()
        if not (prof and date_str_sup and time_sup and clinic_sup):
            continue
        if date_str_sup in holidays:
            continue
        # 날짜 객체 변환
        try:
            current_date_sup = datetime.strptime(f"{start_date.year}-{date_str_sup}", "%Y-%m-%d").date()
        except ValueError:
            continue
        # 범위 체크 (다음 1주까지 허용)
        if not (start_date <= current_date_sup <= extended_end_date):
            continue
        d_name_sup = weekday_names[current_date_sup.weekday()] if current_date_sup.weekday() < 5 else None
        if d_name_sup is None:
            continue
        week_num_sup = (current_date_sup - start_date).days // 7 + 1
        _generate_tasks_for_clinic_session(current_date_sup, prof, time_sup, clinic_sup, d_name_sup, week_num_sup, is_supplementary=True)

    df = pd.DataFrame(full_data).reset_index(drop=True)
    df['task_id'] = df.index.astype(str) + "_" + df['task']
    return df


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


def pre_assignment_diagnosis(residents, leaves, week_count, start_date, holidays, off_slots, master_schedules_df, supplementary_schedules=None, rad_days=None, student_practices=None, bogeonso_substitutes=None, loading_ranges=None, skip_panjung_obs=None, biweekly_choice=None):
    """
    사전 진단: 일반 배정 가능한 슬롯 수 vs 배정해야 할 task 수를 비교하여
    사용자 지정 target_mult로 배정 가능한지 판단하고, 필요한 경우 자동 상향 배수를 계산.

    Returns dict: {
        "status": "적합" or "부족",
        "general_slots": int,            # 일반 배정 가능 슬롯 수 (영상/보건소 제외)
        "general_tasks": int,             # 일반 배정 대상 task 수 (영상/보건소 task 제외)
        "ideal_avg_target_mult": float,   # 사용자 지정 단순 평균 target_mult
        "required_avg_loading": float,    # 실제 필요한 평균 로딩 (task/슬롯 × 10)
        "multiplier": float,              # 적용되는 상향 배수 (1.00, 1.05, 1.10, ...)
        "message": str                    # 사용자에게 보여줄 한 줄 메시지
    }
    """
    if supplementary_schedules is None: supplementary_schedules = []
    if rad_days is None: rad_days = {}
    if student_practices is None: student_practices = []

    weekday_to_idx = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}

    # === 1) 일반 배정 슬롯 계산 (영상/보건소 제외) ===
    general_slots = 0
    general_residents = []  # 일반 배정에 들어가는 전공의
    for r in residents:
        name = r['이름']
        roles = r.get('역할', [])
        is_bogeonso = "연건 보건소" in roles
        is_rad_with_days = ("본원 영상" in roles) and bool(rad_days.get(name))
        if is_bogeonso or is_rad_with_days:
            continue  # 영상/보건소는 별도 처리
        general_residents.append(r)

        # 슬롯 수 계산: 5일 × 주 × 2 (오전/오후) = 주당 10세션
        total_sessions = 0
        for w in range(week_count):
            for d_idx in range(5):
                dt = start_date + timedelta(days=w*7 + d_idx)
                date_str = dt.strftime("%m-%d")
                if date_str in holidays: continue
                total_sessions += 2  # 오전 + 오후

        # 본인 휴가 차감
        leaf_slots = 0
        for l in leaves:
            if l['이름'] == name and l['날짜'] not in holidays:
                leaf_slots += 2  # 휴가는 오전+오후 양쪽 다

        # 메인외래 차지된 세션 차감 (R3 메인외래는 오전+오후 모두 점유)
        main_clinic_slots = 0
        main = r.get('메인외래', "선택안함")
        if main != "선택안함" and main in weekday_to_idx:
            d_idx = weekday_to_idx[main]
            for w in range(week_count):
                dt = start_date + timedelta(days=w*7 + d_idx)
                date_str = dt.strftime("%m-%d")
                if date_str not in holidays:
                    main_clinic_slots += 2

        # 학생 실습으로 차지된 세션
        sp_slots = sum(1 for sp in student_practices if sp['이름'] == name)

        avail = max(1, total_sessions - leaf_slots - main_clinic_slots - sp_slots)
        general_slots += avail

    # === 2) 일반 배정 task 수 계산 ===
    # generate_schedule 결과에서 영상/보건소 task와 영상 파견자 클리닉 차리/판정 task를 제외
    df_all = generate_schedule(start_date, week_count, holidays, master_schedules_df, off_slots, supplementary_schedules=supplementary_schedules, biweekly_choice=biweekly_choice)

    # 영상 파견자가 받을 클리닉 차리/판정 수 추정 = 영상 파견자 수 × week_count
    # (각 영상 파견자가 주당 1개 받음)
    rad_resident_count = sum(1 for r in residents if "본원 영상" in r.get('역할', []) and rad_days.get(r['이름']))
    estimated_rad_clinic_tasks = rad_resident_count * week_count

    # === 2-b) 판정참관 제외 대상이 있으면 드롭될 판정참관 수를 근사 차감 ===
    # 규칙: 제외 대상이 건증 판정을 받으면 그 짝의 판정참관은 아무에게도 배정되지 않는다.
    # 누가 그 판정을 받을지는 솔버가 정하므로, 영상 클리닉 추정과 같은 방식으로 기대값만 잡는다.
    #   (제외 대상의 판정 수용량 비중) × (전체 판정 중 건증 판정 비율)
    estimated_skipped_obs = 0
    skip_set = {n for n in (skip_panjung_obs or [])}
    if skip_set:
        # 짝이 완전한(건증 판정 + 판정참관) 묶음 수
        pair_tasks = {}
        for _, row in df_all.iterrows():
            pid = row.get('pair_id') or ''
            if pid:
                pair_tasks.setdefault(pid, []).append(row['task'])
        geonjeung_pairs = 0
        for tnames in pair_tasks.values():
            if not any("건증" in t for t in tnames):
                continue
            has_judge = any(("판정" in t and "참관" not in t) for t in tnames)
            has_obs = any(("판정" in t and "참관" in t) for t in tnames)
            if has_judge and has_obs:
                geonjeung_pairs += 1
        # 전체 일반 판정 task 수 (참관 제외)
        all_panjung = sum(1 for t in df_all['task'] if "판정" in t and "참관" not in t)

        def _panjung_capacity(r):
            # H8: R3(영상 제외)는 일반 판정 정확히 1개 / H18: R2·R1·R0는 주당 ~1개
            return 1.0 if r['연차'] == "R3" else float(week_count)

        skip_cap = sum(_panjung_capacity(r) for r in general_residents if r['이름'] in skip_set)
        if skip_cap > 0 and all_panjung > 0 and geonjeung_pairs > 0:
            est = skip_cap * (geonjeung_pairs / all_panjung)
            estimated_skipped_obs = int(round(min(est, geonjeung_pairs, skip_cap)))

    # 전체 task 수에서 영상 파견자가 가져갈 task 수 + 드롭 예상 판정참관을 제외 (일반 풀 로딩 비율 계산용)
    general_tasks = len(df_all) - estimated_rad_clinic_tasks - estimated_skipped_obs
    # 추가로 일반 task는 모두 일반 전공의 풀에서 처리하므로 그대로 사용
    # (보건소 task는 daily_slots에 직접 들어가는 거라 df_all에 없음)

    # === 배정 필요한 전체 task 수 (표시용) ===
    # = 일반 생성 task(len(df_all)) + forced 슬롯(연보/메인외래/학생실습/영상)
    # forced_assignments는 공휴일/휴가와 겹치면 휴가/공휴일을 우선해 제외한 결과 (build_problem_data에서 처리)
    # task로 세지 않는 것: 사전휴가/직전휴가/공휴일/Off
    try:
        from cpsat_solver import build_problem_data as _bpd
        _pdata = _bpd(df_all, residents, leaves, week_count, start_date, holidays,
                      bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
                      student_practices=student_practices)
        forced_total = len(_pdata.get('forced_assignments', {}))
    except Exception:
        forced_total = 0
    total_general_df_tasks = len(df_all)
    total_tasks_needed = total_general_df_tasks + forced_total

    # === 3) 지정 로딩 = 각 일반 전공의의 그룹 로딩범위 중앙값 평균 (loading_ranges 반영) ===
    # loading_ranges를 바꾸면 지정 로딩도 함께 변하도록 범위 중앙값에서 산출
    try:
        from cpsat_solver import LOADING_RANGES as _DEFAULT_LR
    except Exception:
        _DEFAULT_LR = {0: (4.9, 5.5), 1: (6.3, 6.8), 2: (6.5, 7.2), 3: (7.3, 7.9), 4: (7.5, 8.0), 5: (8.0, 9.0)}
    _lr = {g: tuple(loading_ranges[g]) for g in range(6)} if loading_ranges else dict(_DEFAULT_LR)

    def _loading_group(r):
        """0:의국/교육수석 1:학생/진료수석 2:일반R3 3:R2 4:R1/R0 (보건소/영상은 general_residents에서 이미 제외)"""
        roles = r.get('역할', [])
        yr = r['연차']
        if yr == "R3":
            if "의국수석" in roles or "교육수석" in roles: return 0
            if "학생수석" in roles or "진료수석" in roles: return 1
            return 2
        if yr == "R2": return 3
        return 4  # R1/R0

    if not general_residents:
        ideal_avg = 7.0  # 기본값
    else:
        mids = []
        for r in general_residents:
            g = _loading_group(r)
            lo, hi = _lr.get(g, (7.0, 7.0))
            mids.append((lo + hi) / 2.0)
        ideal_avg = sum(mids) / len(mids)

    # === 4) 실제 필요 평균 로딩 ===
    required_avg = (general_tasks * 10) / general_slots if general_slots > 0 else 0

    # === 5) 상향 배수 계산 (1.00, 1.05, 1.10, 1.15, ...) ===
    safety_margin = 1.05
    if required_avg <= ideal_avg:
        multiplier = 1.00
        status = "적합"
    else:
        # 필요 배수 = required / ideal, 그리고 1.05 단위로 올림
        raw_ratio = (required_avg / ideal_avg) * safety_margin
        # 1.05, 1.10, 1.15, ... 단위로 올림
        multiplier = 1.00
        while multiplier < raw_ratio:
            multiplier += 0.05
        multiplier = round(multiplier, 2)
        status = "부족"

    _skip_note = f" | 판정참관 제외 추정 −{estimated_skipped_obs}개 반영" if estimated_skipped_obs else ""
    if status == "적합":
        message = f"✅ 적합 — 배정 필요 task 총 {total_tasks_needed}개 (일반 {total_general_df_tasks} + 연보/메인/학생/영상 {forced_total}){_skip_note} | 일반 풀 필요 로딩 {required_avg:.2f} ≤ 지정 {ideal_avg:.2f}"
    else:
        message = f"🔴 부족 — 배정 필요 task 총 {total_tasks_needed}개 (일반 {total_general_df_tasks} + 연보/메인/학생/영상 {forced_total}){_skip_note} | 일반 풀 필요 로딩 {required_avg:.2f} > 지정 {ideal_avg:.2f}, 자동 {multiplier:.2f}배 상향"

    return {
        "status": status,
        "general_slots": general_slots,
        "general_tasks": general_tasks,
        "total_tasks_needed": total_tasks_needed,   # 배정 필요한 전체 work (일반+연보+메인+학생+영상)
        "total_general_df_tasks": total_general_df_tasks,
        "forced_total": forced_total,
        "estimated_skipped_obs": estimated_skipped_obs,  # 판정참관 제외로 빠질 것으로 추정한 참관 수

        "ideal_avg_target_mult": ideal_avg,
        "required_avg_loading": required_avg,
        "multiplier": multiplier,
        "message": message,
    }


def run_auto_assignment(df_all, residents, leaves, week_count, start_date, holidays, pain_applicants=[], student_practices=[], bogeonso_substitutes=None, rad_days=None, target_mult_multiplier=1.0, allow_pairing_split=False):
    """
    bogeonso_substitutes: dict { "MM-DD": [대체자이름1, 대체자이름2, ...] }
        - 연건 보건소 담당자가 휴가인 날, 그 날짜의 연보 슬롯을 대체할 사람 목록 (복수 선택 가능)
        - 설정대로 무조건 배치되고, 대체자는 그 외 빈 슬롯에 추가로 다른 업무가 배정될 수 있음
    rad_days: dict { "전공의이름": ["월","수",...] }
        - 본원 영상 역할이 있는 전공의의 영상의학과 파견 요일 목록
        - 지정된 요일은 오전+오후 모두 "영상"으로 고정 배치
        - 영상 파견자는 그 외 task를 일절 받지 않음 (단, 조비룡/박민선 클리닉 차리/판정를 주 1개 받음, 조비룡 우선)
    target_mult_multiplier: float (default 1.0)
        - 사전 진단에서 계산된 상향 배수. 모든 사람의 target_mult에 곱해짐.
        - 1.05, 1.10, 1.15, ... 로딩이 부족할 때 비율 유지하며 자동 상향
    allow_pairing_split: bool (default False)
        - True면 외래 차리+참관 묶음(차리/참관)을 분리해서 다른 사람에게 배정 가능
        - 단, 건증 판정+판정 참관 묶음은 절대 분리 안 함
        - 5라운드(1.5배율)까지 룰 만족 못 했을 때 6라운드부터 True로 켜짐
    """
    if bogeonso_substitutes is None:
        bogeonso_substitutes = {}
    if rad_days is None:
        rad_days = {}

    out_df = df_all.copy(); assignments = {}; report = []

    def is_fixed(t):
        if "조수환" in t and "판정" in t: return True
        return any(kw in t for kw in ["참관", "처치", "예진"])

    all_dates = []
    total_potential_slots = 0
    for w in range(week_count):
        for d in range(5):
            dt = start_date + timedelta(days=w*7 + d); d_str = dt.strftime("%m-%d"); all_dates.append(d_str)
            if d_str not in holidays: total_potential_slots += 2

    res_data = {}
    for r in residents:
        daily_slots = {d: {'오전': None, '오후': None} for d in all_dates}
        r_leaves = [l for l in leaves if l['이름'] == r['이름']]
        leaf_slots = 0
        for l in r_leaves:
            if l['날짜'] in daily_slots:
                daily_slots[l['날짜']]['오전'] = l['종류']; daily_slots[l['날짜']]['오후'] = l['종류']
                if l['날짜'] not in holidays: leaf_slots += 2
        avail_sessions = max(1, total_potential_slots - leaf_slots)
        assigned_c = 0; main_clinic = r.get('메인외래', "선택안함")
        if main_clinic != "선택안함":
            day_idx = ["월", "화", "수", "목", "금"].index(main_clinic)
            for w in range(week_count):
                d_str = (start_date + timedelta(days=w*7 + day_idx)).strftime("%m-%d")
                if d_str in daily_slots and d_str not in holidays and daily_slots[d_str]['오전'] is None:
                    daily_slots[d_str]['오전'] = "메인외래"; daily_slots[d_str]['오후'] = "메인외래"; assigned_c += 2
        for sp in student_practices:
            if sp['이름'] == r['이름'] and sp['날짜'] in daily_slots:
                if daily_slots[sp['날짜']][sp['시간']] is None:
                    daily_slots[sp['날짜']][sp['시간']] = "학생실습"; assigned_c += 1
        roles = r['역할']
        # 새 target_mult 값 (사용자 의도 기준) × 사전 진단으로 계산된 상향 배수
        base_target_mult = get_resident_target_mult(r)
        target_mult = base_target_mult * target_mult_multiplier
        res_data[r['이름']] = {"year": r['연차'], "target_mult": target_mult, "avail": avail_sessions, "assigned_count": assigned_c, "panjung_quota": 0, "panjung_per_week": {}, "minor_count": 0, "tx_count": 0, "daily_slots": daily_slots, "main_clinic": main_clinic, "is_bogeonso": "연건 보건소" in roles, "is_rad": "본원 영상" in roles, "is_rookie": "의국 처음" in roles or r['연차'] == "R0"}

    # === 연건 보건소 담당자 자동 배정 (휴가 아닌 날) ===
    # 휴가인 날에는 res_data[bogeonso]의 daily_slots에 이미 "[휴가종류]"가 들어 있으므로 None이 아니어서 자동으로 스킵됨
    bogeonso_names = [n for n, d in res_data.items() if d["is_bogeonso"]]
    for n in bogeonso_names:
        d = res_data[n]
        for d_str in all_dates:
            w_day = datetime.strptime(f"{start_date.year}-{d_str}", "%Y-%m-%d").weekday()
            if d_str not in holidays:
                if d["daily_slots"][d_str]['오전'] is None: d["daily_slots"][d_str]['오전'] = "연보(오전)"
                if w_day in [1, 3] and d["daily_slots"][d_str]['오후'] is None: d["daily_slots"][d_str]['오후'] = "연보(오후)"

    # === [신규] 연건 보건소 휴가일 대체자 강제 배정 ===
    # bogeonso_substitutes 에 있는 날짜의 연보 슬롯을 지정된 대체자(들)에게 강제 배정
    # 대체자가 여러 명이면 라운드로빈으로 분배 (각 슬롯마다 다음 사람)
    sub_report_lines = []
    if bogeonso_substitutes:
        # 휴가 중인 보건소 담당자가 실제로 있는지 확인 (방어 코드)
        bogeonso_leave_dates = set()
        for n in bogeonso_names:
            for l in leaves:
                if l['이름'] == n:
                    bogeonso_leave_dates.add(l['날짜'])

        for d_str, sub_list in bogeonso_substitutes.items():
            if not sub_list: continue
            if d_str in holidays: continue
            if d_str not in all_dates: continue
            # 보건소 담당자가 실제로 이 날 휴가가 아니면 적용하지 않음 (안전장치)
            if d_str not in bogeonso_leave_dates: continue

            w_day = datetime.strptime(f"{start_date.year}-{d_str}", "%Y-%m-%d").weekday()
            # 어떤 슬롯들이 연보 슬롯인지 결정 (월/수/금은 오전만, 화/목은 오전+오후)
            target_slots = ["오전"]
            if w_day in [1, 3]:  # 화, 목
                target_slots.append("오후")

            # 라운드로빈으로 대체자에게 분배
            valid_subs = [s for s in sub_list if s in res_data]
            if not valid_subs:
                sub_report_lines.append(f"  ⚠️ {d_str}: 유효한 대체자 없음 (대체자: {sub_list})")
                continue

            rr_idx = 0
            for slot_time in target_slots:
                # 라운드로빈 시도: 가능한 대체자를 찾을 때까지 순환
                assigned = False
                for tries in range(len(valid_subs)):
                    sub_name = valid_subs[(rr_idx + tries) % len(valid_subs)]
                    sub_slots = res_data[sub_name]['daily_slots'][d_str]
                    # 이미 휴가/공휴일/메인외래 등으로 채워져 있으면 이 사람 건너뜀
                    if sub_slots[slot_time] is None:
                        slot_label = f"연보({slot_time})" if w_day in [1, 3] else "연보(오전)"
                        # 슬롯 시간에 맞는 라벨 사용
                        if slot_time == "오전":
                            slot_label = "연보(오전)"
                        else:
                            slot_label = "연보(오후)"
                        sub_slots[slot_time] = slot_label
                        res_data[sub_name]['assigned_count'] += 1
                        sub_report_lines.append(f"  ✓ {d_str} {slot_time} → **{sub_name}** (연보 대체)")
                        assigned = True
                        rr_idx = (rr_idx + tries + 1) % len(valid_subs)
                        break
                if not assigned:
                    sub_report_lines.append(f"  ⚠️ {d_str} {slot_time}: 모든 대체자가 이미 다른 일정으로 배정됨")

    # === [신규] 본원 영상 파견자 처리 ===
    # 영상 파견 요일이 "지정된" 사람만 특별 처리:
    # 1) 지정된 파견 요일은 오전+오후 모두 "영상"으로 고정 (휴가 우선)
    # 2) 조비룡/박민선 클리닉 차리/판정 묶음을 주 1개 배정 (조비룡 우선)
    # 영상 파견 요일 미지정자는 일반 R3로 동작 (아래 valid_names에 포함)
    rad_report_lines = []
    rad_names = [n for n, d in res_data.items() if d["is_rad"] and rad_days.get(n)]  # 요일 지정된 사람만
    weekday_to_idx = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}
    for rad_name in rad_names:
        days = rad_days.get(rad_name, [])
        day_idx_list = [weekday_to_idx[d] for d in days if d in weekday_to_idx]
        # 1) 매주 지정 요일의 오전/오후 슬롯에 "영상" 고정 (휴가/공휴일이 있으면 그대로 둠)
        for w in range(week_count):
            for d_idx in day_idx_list:
                d_str = (start_date + timedelta(days=w*7 + d_idx)).strftime("%m-%d")
                if d_str in holidays:
                    continue
                slots = res_data[rad_name]['daily_slots'].get(d_str)
                if slots is None:
                    continue
                if slots['오전'] is None:
                    slots['오전'] = "영상"
                    res_data[rad_name]['assigned_count'] += 1
                if slots['오후'] is None:
                    slots['오후'] = "영상"
                    res_data[rad_name]['assigned_count'] += 1
        rad_report_lines.append(f"  ✓ **{rad_name}**: 매주 {'/'.join(days)} 영상 파견 배정")

    # 2) 클리닉 차리/판정 묶음 주 1개 배정 (조비룡 우선)
    if rad_names:
        # 주차별로 묶음 task 모으기 (조비룡 클리닉 / 박민선 클리닉)
        # pair_id 기준으로 묶음 단위 식별
        # 조비룡 클리닉 차리/판정 (목): 진료가 목, task는 수요일에 1개 묶음(차리+판정 같은 셀에 통합)
        # 박민선 클리닉 차리/판정 (월): 진료가 월, task는 직전주 목요일에 1개 묶음
        # 실제 df_all에서 pair_id가 있는 것 = 묶음 task
        clinic_groups_per_week = {}  # {week: [(priority, gid, [(idx,row),...]), ...]}
        for idx, row in out_df.iterrows():
            t = row['task']
            if "클리닉 차리/판정" not in t:
                continue
            if "조비룡" in t:
                prio = 0  # 조비룡 우선 (작은 수가 먼저)
            elif "박민선" in t:
                prio = 1
            else:
                continue
            w = row['week']
            gid = row['pair_id'] if row['pair_id'] else row['task_id']
            clinic_groups_per_week.setdefault(w, {})
            clinic_groups_per_week[w].setdefault(gid, {"prio": prio, "items": []})
            clinic_groups_per_week[w][gid]["items"].append((idx, row))

        # 영상 파견자에게 주차별 라운드로빈으로 배정
        # 같은 주에 영상 파견자가 여러 명이면 조비룡은 우선 영상 파견자 첫 사람, 그 다음 박민선은 두번째 영상 파견자
        for w, gdict in clinic_groups_per_week.items():
            # 우선순위 순으로 정렬 (조비룡 먼저)
            sorted_groups = sorted(gdict.items(), key=lambda x: x[1]["prio"])
            # 영상 파견자 중 아직 이번주 클리닉 묶음을 안 받은 사람들
            rad_received_this_week = set()
            for gid, ginfo in sorted_groups:
                items = ginfo["items"]
                # 이 묶음을 받을 수 있는 영상 파견자 찾기
                for rad_name in rad_names:
                    if rad_name in rad_received_this_week:
                        continue
                    # 이 묶음의 모든 슬롯이 비어있어야 함
                    can_take = True
                    temp_assigns = []
                    for idx, row in items:
                        dv, ot = row['date'], row['time']
                        slots = res_data[rad_name]['daily_slots'].get(dv)
                        if slots is None or slots[ot] is not None:
                            can_take = False
                            break
                        temp_assigns.append((idx, dv, ot, row))
                    if can_take:
                        for idx, dv, ot, row in temp_assigns:
                            assignments[row['task_id']] = rad_name
                            res_data[rad_name]['daily_slots'][dv][ot] = row['task_id']
                            res_data[rad_name]['assigned_count'] += 1
                        rad_received_this_week.add(rad_name)
                        task_label = "조비룡 클리닉" if ginfo["prio"] == 0 else "박민선 클리닉"
                        rad_report_lines.append(f"  ✓ **{rad_name}** 주{w}: {task_label} 차리/판정 배정")
                        break

    valid_names = [n for n, d in res_data.items() if not d["is_bogeonso"] and not (d["is_rad"] and rad_days.get(n))]

    # 1. 박진호 통증클리닉 차리/참관 세트 우선 배정
    if pain_applicants:
        pain_groups = {}
        for idx, row in out_df.iterrows():
            if "박진호" in row['task'] and "통증클리닉" in row['task']:
                gid = row['pair_id'] if row['pair_id'] else row['task_id']
                if gid not in pain_groups: pain_groups[gid] = []
                pain_groups[gid].append((idx, row))
        app_valid_groups = {app: [] for app in pain_applicants if app in valid_names}
        for app in app_valid_groups:
            for gid, items in pain_groups.items():
                can_take_all = True
                for idx, row in items:
                    dv, ot = row['date'], row['time']
                    if res_data[app]['main_clinic'] == row['day']: can_take_all = False; break
                    slots = res_data[app]['daily_slots'][dv]
                    assign_time = None
                    if slots[ot] is None: assign_time = ot
                    elif not is_fixed(row['task']) and slots['오전' if ot == '오후' else '오후'] is None:
                        assign_time = '오전' if ot == '오후' else '오후'
                    if not assign_time: can_take_all = False; break
                if can_take_all: app_valid_groups[app].append(gid)
        sorted_apps = sorted(app_valid_groups.keys(), key=lambda x: len(app_valid_groups[x]))
        assigned_gids = set()
        for app in sorted_apps:
            for gid in app_valid_groups[app]:
                if gid not in assigned_gids:
                    for idx, row in pain_groups[gid]:
                        dv, ot = row['date'], row['time']
                        slots = res_data[app]['daily_slots'][dv]
                        assign_time = ot if slots[ot] is None else ('오전' if ot == '오후' else '오후')
                        assignments[row['task_id']] = app
                        res_data[app]['daily_slots'][dv][assign_time] = row['task_id']
                        out_df.at[idx, 'time'] = assign_time
                        res_data[app]['assigned_count'] += 1
                    assigned_gids.add(gid)
                    break

    # 나머지 그룹화 및 자동 배정 로직
    # === allow_pairing_split=True인 경우 ===
    # 외래 차리 + 외래 참관 묶음을 분리 가능 (각각 다른 사람에게 배정 가능)
    # 단, 건증 판정 + 판정 참관 묶음은 절대 분리 안 함
    # 분리된 묶음은 task_id 단위로 단발 그룹화
    def is_splittable_pair(items):
        """이 묶음이 외래 차리/참관 묶음인지 (분리 가능)"""
        if len(items) < 2: return False
        has_chari = False
        has_observation = False
        has_panjung = False
        for _, row in items:
            t = row['task']
            if "판정" in t and "참관" not in t:
                has_panjung = True  # 판정 task가 있으면 분리 불가
            elif "차리" in t:
                has_chari = True
            elif "참관" in t:
                has_observation = True
        # 판정이 들어간 묶음은 분리 안 함 (건증 판정 + 판정 참관, 클리닉 차리/판정 등)
        if has_panjung: return False
        # 차리 + 참관 묶음만 분리 가능
        return has_chari and has_observation

    task_groups = {}
    split_origin = {}  # 분리된 task_id가 원래 어느 pair_id에서 왔는지 추적 (위반 카운트용)
    for idx, row in out_df.iterrows():
        if row['task_id'] in assignments: continue
        gid = row['pair_id'] if row['pair_id'] else row['task_id']
        if gid not in task_groups: task_groups[gid] = []
        task_groups[gid].append((idx, row))

    # 분리 모드: 분리 가능한 묶음을 task별 단발 그룹으로 쪼개기
    if allow_pairing_split:
        splittable_gids = [gid for gid, items in task_groups.items() if is_splittable_pair(items)]
        for gid in splittable_gids:
            items = task_groups.pop(gid)
            for idx, row in items:
                tid = row['task_id']
                task_groups[tid] = [(idx, row)]
                split_origin[tid] = gid  # 어느 묶음에서 왔는지 기록

    group_info = []
    for gid, items in task_groups.items():
        is_r3_abs, is_tx, is_yejin, is_panjung, is_clinic_panjung, has_fixed = False, False, False, False, False, False
        for idx, row in items:
            t = row['task']
            if "예진" in t: is_yejin = True; is_r3_abs = True
            if (any(p in t for p in ["조비룡", "박민선"]) and any(kw in t for kw in ["외래 참관", "차리"])): is_r3_abs = True
            if "처치" in t: is_tx = True
            if "판정" in t and "참관" not in t: is_panjung = True
            # 조비룡/박민선 클리닉 차리/판정 묶음 식별 (R3 판정 quota에서 제외 + R3에게 페널티)
            if (any(p in t for p in ["조비룡", "박민선"]) and "클리닉" in t and "차리/판정" in t):
                is_clinic_panjung = True
            if is_fixed(t): has_fixed = True
        # 우선순위 재설계 (사용자 의도):
        #   100: R3 전용 묶음 (예진, 조비룡/박민선 차리/참관) - R3만 가능하므로 먼저 확보
        #    80: 판정 묶음 (R3 1개 hard 제한, R1/R0가 다른 일정으로 차기 전에 충분히 가져가야 함)
        #    50: 일반 묶음 task (외래 차리+참관 세트)
        #    30: 단발 task
        #    10: 처치/예진 (가장 마지막 - 묶음이 아닌 단발이라 끝에 채워도 됨)
        if is_r3_abs and not is_yejin and not is_tx:
            # R3 전용 묶음 (예진/처치 아닌 것: 조비룡/박민선 묶음)
            priority = 100
        elif is_panjung:
            priority = 80
        elif is_tx or is_yejin:
            # 처치/예진은 가장 마지막
            priority = 10
        elif len(items) > 1:
            priority = 50
        else:
            priority = 30
        group_info.append({'gid': gid, 'items': items, 'is_r3_abs': is_r3_abs, 'is_tx': is_tx, 'is_yejin': is_yejin, 'is_panjung': is_panjung, 'is_clinic_panjung': is_clinic_panjung, 'priority': priority})
    group_info.sort(key=lambda x: (x['priority'], random.random()), reverse=True)

    def get_min_r1r0_panjung():
        """현재 R1/R0들 중 가장 적게 받은 판정 수"""
        r1r0_pqs = [res_data[n]['panjung_quota'] for n in valid_names if res_data[n]['year'] in ["R1", "R0"]]
        return min(r1r0_pqs) if r1r0_pqs else 999

    def get_cand_score(n, info):
        deficit = res_data[n]['target_mult'] - ((res_data[n]['assigned_count'] * 10) / res_data[n]['avail'])
        bonus = 0
        if info.get('is_panjung', False):
            pq, yr = res_data[n]['panjung_quota'], res_data[n]['year']
            if yr == "R3":
                # 클리닉 차리/판정는 R3에게 우선순위 낮춤 (다른 일반 판정을 받게 유도)
                if info.get('is_clinic_panjung', False):
                    bonus = -3000  # 받을 수는 있지만 일반 판정보다 우선순위 낮음
                else:
                    bonus = 10000 if pq < 1 else -20000
            elif yr == "R2":
                # 사용자 정의: R2 = 주차수 × 1개 (4주차: 4, 5주차: 5)
                r2_target = week_count
                # Soft rule: R2가 R1/R0 min 초과하면 페널티 (hard 아님, 라운드에서 평가)
                min_r1r0 = get_min_r1r0_panjung()
                if (pq + 1) > min_r1r0:
                    bonus = -5000  # soft penalty (이전 -100000 → -5000)
                elif pq < r2_target:
                    bonus = 2000
                else:
                    bonus = -15000  # 목표 초과
            elif yr in ["R1", "R0"]:
                # 사용자 정의: R1/R0 = 주차수 × 2개 (4주차: 8, 5주차: 10)
                r1_target = week_count * 2
                if pq < r1_target:
                    bonus = 5000  # R1/R0 우선 (기존 500보다 크게 - 판정 먼저 풀에 들어가도록)
                else:
                    bonus = -10000
        if info.get('is_tx', False):
            if res_data[n]['year'] == "R1" and res_data[n]['tx_count'] >= 1:
                bonus -= 20000
            bonus -= (res_data[n]['minor_count'] * 10)
        elif info.get('is_yejin', False):
            bonus -= (res_data[n]['minor_count'] * 10)
        return bonus + deficit + random.uniform(-0.1, 0.1)

    def get_loading_group(n):
        """전공의 n의 로딩 그룹 (작을수록 더 낮은 로딩이어야 함)
        0: 의국/교육수석 R3
        1: 학생/진료수석 R3
        2: 일반 R3 (영상 파견자 제외)
        3: R2 (보건소 제외)
        4: R1/R0
        -1: 보건소/영상 파견자 (룰 적용 안 함)
        """
        d = res_data[n]
        if d['is_bogeonso']: return -1
        if d['is_rad'] and rad_days.get(n): return -1
        yr = d['year']
        if yr == "R3":
            # roles 가져오기
            roles = next((r.get('역할', []) for r in residents if r['이름'] == n), [])
            if "의국수석" in roles or "교육수석" in roles: return 0
            if "학생수석" in roles or "진료수석" in roles: return 1
            return 2
        if yr == "R2": return 3
        if yr in ["R1", "R0"]: return 4
        return -1

    # 사전에 각 전공의의 그룹 캐시
    cand_group = {n: get_loading_group(n) for n in res_data.keys()}

    def get_group_min_loading(group_idx):
        """group_idx 그룹에 속한 전공의들의 현재 최소 로딩"""
        members = [n for n, g in cand_group.items() if g == group_idx]
        if not members: return 999
        loads = []
        for n in members:
            if res_data[n]['avail'] > 0:
                loads.append((res_data[n]['assigned_count'] * 10) / res_data[n]['avail'])
        return min(loads) if loads else 999

    def violates_loading_chain(n, additional_count):
        """전공의 n이 task additional_count개 더 받으면 부등호 체인 위반?
        본인 그룹 가설 로딩이 우상위 그룹(group+1, group+2, ...)의 min을 초과하면 위반"""
        my_group = cand_group.get(n, -1)
        if my_group == -1: return False  # 보건소/영상은 룰 제외
        if res_data[n]['avail'] <= 0: return False
        hypothetical = ((res_data[n]['assigned_count'] + additional_count) * 10) / res_data[n]['avail']
        # 나보다 한 단계 위 그룹(=더 높아야 하는 그룹)의 현재 min 로딩보다 내가 높아지면 안 됨
        # 즉 max(내그룹) ≤ min(상위 그룹)
        for higher_group in range(my_group + 1, 5):
            higher_min = get_group_min_loading(higher_group)
            if higher_min < 999 and hypothetical > higher_min:
                return True  # 위반
        return False

    def attempt_assignment(cands_list, info_items):
        for n in cands_list:
            can_take, temp_assigns = True, []
            for idx, row in info_items:
                dv, ot, is_fx = row['date'], row['time'], is_fixed(row['task'])
                if res_data[n]['main_clinic'] == row['day']: can_take = False; break
                slots = res_data[n]['daily_slots'][dv]
                assign_time = ot if slots[ot] is None else (None if is_fx else ('오전' if ot=='오후' and slots['오전'] is None else ('오후' if ot=='오전' and slots['오후'] is None else None)))
                if assign_time: temp_assigns.append((idx, dv, assign_time))
                else: can_take = False; break
            # === 로딩 hard rule은 제거됨 (soft rule인 target_mult만 사용) ===
            # 이전 버전에서 hard rule 사용 → 부등호 만족하지만 미배정 task 발생
            # → 사용자 요청: hard rule 빼고 target_mult로 자연 분배 + 외부 wrapper에서 배율 자동 조정
            if can_take:
                for idx, d_val, t_val in temp_assigns:
                    row = out_df.loc[idx]
                    assignments[row['task_id']] = n
                    res_data[n]['daily_slots'][d_val][t_val] = row['task_id']
                    out_df.at[idx, 'time'] = t_val
                    res_data[n]['assigned_count'] += 1
                    # 판정 quota 카운트:
                    # - "판정" 포함 & "참관" 없음 (= 판정 task)
                    # - 단, R3의 경우 클리닉 차리/판정는 판정 quota에 카운트하지 않음 (별도로 일반 판정을 받아야 함)
                    if "판정" in row['task'] and "참관" not in row['task']:
                        is_clinic_pj = (any(p in row['task'] for p in ["조비룡", "박민선"]) and "클리닉" in row['task'] and "차리/판정" in row['task'])
                        if not (res_data[n]['year'] == "R3" and is_clinic_pj):
                            res_data[n]['panjung_quota'] += 1
                            # 주차별 판정 카운트도 같이 증가
                            w = row['week']
                            res_data[n]['panjung_per_week'][w] = res_data[n]['panjung_per_week'].get(w, 0) + 1
                    if "처치" in row['task']: res_data[n]['tx_count'] += 1
                    if any(kw in row['task'] for kw in ["처치", "예진"]): res_data[n]['minor_count'] += 1
                return True
        return False

    for info in group_info:
        cands = []
        if info['is_r3_abs']: cands = [n for n in valid_names if res_data[n]['year'] == "R3"]
        elif info['is_tx']: cands = [n for n in valid_names if not res_data[n]['is_rookie']]
        else: cands = valid_names[:]
        # === 판정 hard 제외 ===
        # 1) R3 판정 1개 도달 시 후보에서 완전 제외 (클리닉 차리/판정 제외) [hard 유지]
        # 2) R1/R0 주당 최대 3개 hard [신규]
        # 3) R2 주당 최대 2개 hard [신규]
        # (R2 max ≤ R1/R0 min은 hard 제거 → soft로 변경, 라운드 평가 기준으로 사용)
        if info.get('is_panjung', False) and not info.get('is_clinic_panjung', False):
            # 판정 묶음의 주차 확인 (items의 첫 row 주차)
            panjung_week = None
            for idx, row in info['items']:
                if "판정" in row['task'] and "참관" not in row['task']:
                    panjung_week = row['week']
                    break
            # R3 hard 제외 (총 1개)
            cands = [n for n in cands if not (res_data[n]['year'] == "R3" and res_data[n]['panjung_quota'] >= 1)]
            # R2 주당 최대 2개 hard 제외
            if panjung_week is not None:
                cands = [n for n in cands if not (res_data[n]['year'] == "R2" and res_data[n]['panjung_per_week'].get(panjung_week, 0) >= 2)]
                # R1/R0 주당 최대 3개 hard 제외
                cands = [n for n in cands if not (res_data[n]['year'] in ["R1", "R0"] and res_data[n]['panjung_per_week'].get(panjung_week, 0) >= 3)]
        cands.sort(key=lambda n: get_cand_score(n, info), reverse=True)
        if not attempt_assignment(cands, info['items']):
            fallback_cands = valid_names[:]
            # fallback에서도 hard rule 유지
            if info.get('is_panjung', False) and not info.get('is_clinic_panjung', False):
                panjung_week_fb = None
                for idx, row in info['items']:
                    if "판정" in row['task'] and "참관" not in row['task']:
                        panjung_week_fb = row['week']
                        break
                fallback_cands = [n for n in fallback_cands if not (res_data[n]['year'] == "R3" and res_data[n]['panjung_quota'] >= 1)]
                if panjung_week_fb is not None:
                    fallback_cands = [n for n in fallback_cands if not (res_data[n]['year'] == "R2" and res_data[n]['panjung_per_week'].get(panjung_week_fb, 0) >= 2)]
                    fallback_cands = [n for n in fallback_cands if not (res_data[n]['year'] in ["R1", "R0"] and res_data[n]['panjung_per_week'].get(panjung_week_fb, 0) >= 3)]
            # 처치는 fallback에서도 rookie(R0 + R1 의국처음) hard 제외 유지
            if info['is_tx']:
                fallback_cands = [n for n in fallback_cands if not res_data[n]['is_rookie']]
            fallback_cands.sort(key=lambda n: get_cand_score(n, info), reverse=True)
            attempt_assignment(fallback_cands, info['items'])

    report.append("✅ **배정 리포트**")
    if sub_report_lines:
        report.append("")
        report.append("🏥 **연건 보건소 대체 배정 결과**")
        report.extend(sub_report_lines)
        report.append("")
    if rad_report_lines:
        report.append("")
        report.append("📡 **본원 영상 파견 배정 결과**")
        report.extend(rad_report_lines)
        report.append("")

    # === [신규] 미배정 task 표시 (절대원칙 위반 — 모든 task는 빠짐없이 배정되어야 함) ===
    unassigned_rows = []
    for idx, row in out_df.iterrows():
        if row['task_id'] not in assignments:
            unassigned_rows.append(row)
    if unassigned_rows:
        report.append("")
        report.append(f"🚨 **미배정 task ({len(unassigned_rows)}개) — 슬롯 부족으로 자동 배정 실패. 수동 배정 필요**")
        # 주차/날짜/시간순 정렬
        unassigned_sorted = sorted(unassigned_rows, key=lambda r: (r['week'], r['date'], r['time'], r['task']))
        for row in unassigned_sorted:
            report.append(f"  - 주{row['week']} {row['date']}({row['day']}) {row['time']} | {row['task']}")
        report.append("")

    # === 깨진 pairing 카운트 (wrapper 평가용으로 별도 메타데이터에 저장) ===
    broken_pairs_count = 0
    if allow_pairing_split and split_origin:
        origin_assignees = {}
        for tid, origin_pid in split_origin.items():
            assignee = assignments.get(tid)
            if assignee:
                origin_assignees.setdefault(origin_pid, set()).add(assignee)
        broken_pairs_count = sum(1 for pid, names in origin_assignees.items() if len(names) > 1)
    # 메타데이터를 res_data의 특수 키에 저장 (다른 함수가 res_data를 순회할 때 _meta 키는 건너뛰도록)
    res_data['__meta__'] = {
        'broken_pairs_count': broken_pairs_count,
        'split_origin': split_origin,
    }

    # === [신규] 깨진 pairing 표시 (allow_pairing_split=True인 경우만) ===
    if allow_pairing_split and split_origin:
        # split_origin: {task_id: 원래_pair_id}
        # 같은 원래_pair_id의 모든 task가 같은 사람에게 배정되었는지 체크
        # 다른 사람에게 갔으면 그 pair_id는 "깨진" 묶음
        origin_assignees = {}  # {원래_pair_id: set of assignees}
        for tid, origin_pid in split_origin.items():
            assignee = assignments.get(tid)
            if assignee:
                origin_assignees.setdefault(origin_pid, set()).add(assignee)
        broken_pairs = [pid for pid, names in origin_assignees.items() if len(names) > 1]
        if broken_pairs:
            report.append("")
            report.append(f"🔗 **깨진 외래 차리/참관 묶음 ({len(broken_pairs)}개) — 로딩 규칙을 맞추기 위해 분리됨**")
            # 어느 묶음이 깨졌는지 표시
            for pid in broken_pairs:
                # pair_id 형식: "{week}_{day}_{prof}_{clinic}_..."
                parts = pid.split("_")
                if len(parts) >= 4:
                    label = f"주{parts[0]} {parts[1]}요일 {parts[2]} {parts[3]}"
                else:
                    label = pid
                # 어느 사람들에게 어떻게 분리됐는지
                assigned_to = list(origin_assignees[pid])
                report.append(f"  - {label} → 분리: {', '.join(assigned_to)}")
            report.append("")

    for n in sorted(valid_names, key=lambda x: (res_data[x]['assigned_count']*10)/res_data[x]['avail']):
        rd = res_data[n]; load = (rd['assigned_count']*10)/rd['avail']
        report.append(
            f"- **{n} ({rd['year']})**: 세션 {rd['assigned_count']}/{rd['avail']} (로딩 {load:.2f})"
            f" | 🩺판정: **{rd['panjung_quota']}** | 💉처치+예진: **{rd['minor_count']}**"
            f" (처치 {rd['tx_count']}/예진 {rd['minor_count'] - rd['tx_count']})"
        )
    return out_df, assignments, "\n".join(report), res_data


def run_auto_assignment_multi(df_all, residents, leaves, week_count, start_date, holidays,
                                pain_applicants=[], student_practices=[],
                                bogeonso_substitutes=None, rad_days=None, target_mult_multiplier=1.0,
                                num_trials=10, max_multiplier=1.5, max_rounds=5):
    """
    다중 라운드 + 배율 자동 증가 wrapper.

    동작:
      1) 시작 배율 (사용자 지정 target_mult_multiplier)로 num_trials번 시도
      2) 시도 중 로딩 부등호 체인(max(왼쪽)≤min(오른쪽)) 만족하는 결과가 있으면 → 그 중 최적 반환
      3) 만족하는 결과가 없으면 → 배율 +0.05 → 다시 num_trials번 시도 (라운드 증가)
      4) 종료 조건: 배율 max_multiplier 도달 또는 max_rounds 라운드 도달 (먼저 닿는 거)
      5) 종료 시까지 만족 못 했으면 → 모든 라운드 중 가장 좋은 결과 반환

    부등호 체인 (각 부등호 max(왼쪽) ≤ min(오른쪽)):
      max(의국/교육수석) ≤ min(학생/진료수석)
      max(학생/진료수석) ≤ min(일반R3)
      max(일반R3) ≤ min(R2)
      max(R2) ≤ min(R1/R0)

    Returns: (out_df, assigns, report, res_data)
    """
    weekday_to_idx_main = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}

    def resident_group(r):
        """0: 의국/교육수석, 1: 학생/진료수석, 2: 일반 R3, 3: R2,
        4: 의국처음 (R1/R0 + 태그), 5: R1/R0 태그없음, -1: 보건소/영상"""
        roles = r.get('역할', [])
        if "연건 보건소" in roles: return -1
        if "본원 영상" in roles and rad_days and rad_days.get(r['이름']): return -1
        yr = r['연차']
        if yr == "R3":
            if "의국수석" in roles or "교육수석" in roles: return 0
            if "학생수석" in roles or "진료수석" in roles: return 1
            return 2
        if yr == "R2": return 3
        if yr in ["R1", "R0"]:
            if "의국 처음" in roles:
                return 4
            return 5
        return -1

    res_group = {r['이름']: resident_group(r) for r in residents}

    def evaluate_result(res_data, out_df, assigns):
        """결과 평가 - 부등호 위반 수 + 미배정 수 + 깨진 pairing 수 + 표준편차 반환"""
        # 그룹별 로딩 수집 (6 그룹: 0~5)
        group_loads = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
        all_loads = []
        for name, g in res_group.items():
            if g == -1: continue
            if name not in res_data: continue
            d = res_data[name]
            if d['avail'] <= 0: continue
            load = (d['assigned_count'] * 10) / d['avail']
            group_loads[g].append(load)
            all_loads.append(load)

        # 부등호 체인 위반 수 (5개 부등호: 0<1<2<3<4<5)
        chain_violations = 0
        for i in range(5):
            left = group_loads[i]
            right = group_loads[i+1]
            if left and right:
                if max(left) > min(right):
                    chain_violations += 1

        # 판정 hard rule 위반 (R2 max ≤ R1/R0 min + R3 ≤ 1)
        pj_violations = 0
        r2_pqs = []
        r1r0_pqs = []
        for r in residents:
            n = r['이름']
            if n not in res_data: continue
            g = res_group[n]
            d = res_data[n]
            if g == 3: r2_pqs.append(d['panjung_quota'])
            elif g in (4, 5): r1r0_pqs.append(d['panjung_quota'])
            elif g in [0, 1, 2] and d['panjung_quota'] > 1:
                pj_violations += 1
        if r2_pqs and r1r0_pqs:
            if max(r2_pqs) > min(r1r0_pqs):
                pj_violations += 1

        # 미배정 task 수
        unassigned_count = sum(1 for _, row in out_df.iterrows() if row['task_id'] not in assigns)

        # 깨진 pairing 수 (메타데이터에서)
        broken_pairs = res_data.get('__meta__', {}).get('broken_pairs_count', 0)

        # 표준편차
        if len(all_loads) >= 2:
            avg = sum(all_loads) / len(all_loads)
            std = (sum((x - avg) ** 2 for x in all_loads) / len(all_loads)) ** 0.5
        else:
            std = 0

        return chain_violations, pj_violations, unassigned_count, broken_pairs, round(std, 3)

    # === 라운드 루프 ===
    # Phase 1 (라운드 1~5): 배율 증가 + pairing 유지 (10회씩)
    # Phase 2 (라운드 6): 배율 1.5 고정 + pairing 분리 허용 (50회)
    current_mult = target_mult_multiplier
    best_overall = None
    best_overall_score = None
    round_summaries = []
    success_round = -1
    success_trial = -1
    success_with_split = False

    # Phase 1: 배율 증가 (5라운드)
    for round_idx in range(max_rounds):
        round_trials = []

        for trial_idx in range(num_trials):
            df_copy = df_all.copy()
            out_df, assigns, report, res_data = run_auto_assignment(
                df_copy, residents, leaves, week_count, start_date, holidays,
                pain_applicants=pain_applicants, student_practices=student_practices,
                bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
                target_mult_multiplier=current_mult,
                allow_pairing_split=False
            )
            cv, pv, uc, bp, std = evaluate_result(res_data, out_df, assigns)
            score = (cv, pv, uc, bp, std)
            round_trials.append({
                "trial": trial_idx + 1,
                "chain_viol": cv, "pj_viol": pv, "unassigned": uc, "broken_pairs": bp, "std": std,
                "result": (out_df, assigns, report, res_data)
            })

        # 이 라운드에서 부등호 만족한 시도 (chain_violations == 0)
        chain_ok_trials = [t for t in round_trials if t['chain_viol'] == 0]

        if chain_ok_trials:
            best_in_round = min(chain_ok_trials, key=lambda t: (t['pj_viol'], t['unassigned'], t['broken_pairs'], t['std']))
            success_round = round_idx + 1
            success_trial = best_in_round['trial']
            round_summaries.append({
                "round": round_idx + 1,
                "mult": current_mult,
                "chain_ok_count": len(chain_ok_trials),
                "best": best_in_round,
                "split_mode": False,
            })
            best_overall = best_in_round['result']
            best_overall_score = (best_in_round['chain_viol'], best_in_round['pj_viol'], best_in_round['unassigned'], best_in_round['broken_pairs'], best_in_round['std'])
            break
        else:
            best_in_round = min(round_trials, key=lambda t: (t['chain_viol'], t['pj_viol'], t['unassigned'], t['broken_pairs'], t['std']))
            score = (best_in_round['chain_viol'], best_in_round['pj_viol'], best_in_round['unassigned'], best_in_round['broken_pairs'], best_in_round['std'])
            if best_overall_score is None or score < best_overall_score:
                best_overall_score = score
                best_overall = best_in_round['result']
            round_summaries.append({
                "round": round_idx + 1,
                "mult": current_mult,
                "chain_ok_count": 0,
                "best": best_in_round,
                "split_mode": False,
            })
            new_mult = round(current_mult + 0.10, 2)
            if new_mult > max_multiplier:
                # 다음 라운드 진행하지 않음 (Phase 2로 넘어감)
                break
            current_mult = new_mult

    # Phase 2: Phase 1에서 부등호 만족 못 했으면 → 6라운드 (배율 1.5 + pairing 분리 + 50회)
    if success_round == -1:
        phase2_trials_count = 50
        phase2_mult = max_multiplier  # 1.5 고정
        phase2_trials = []

        for trial_idx in range(phase2_trials_count):
            df_copy = df_all.copy()
            out_df, assigns, report, res_data = run_auto_assignment(
                df_copy, residents, leaves, week_count, start_date, holidays,
                pain_applicants=pain_applicants, student_practices=student_practices,
                bogeonso_substitutes=bogeonso_substitutes, rad_days=rad_days,
                target_mult_multiplier=phase2_mult,
                allow_pairing_split=True
            )
            cv, pv, uc, bp, std = evaluate_result(res_data, out_df, assigns)
            phase2_trials.append({
                "trial": trial_idx + 1,
                "chain_viol": cv, "pj_viol": pv, "unassigned": uc, "broken_pairs": bp, "std": std,
                "result": (out_df, assigns, report, res_data)
            })

        # 부등호 만족하는 것 중 깨진 pairing 최소
        chain_ok_p2 = [t for t in phase2_trials if t['chain_viol'] == 0]
        if chain_ok_p2:
            best_p2 = min(chain_ok_p2, key=lambda t: (t['pj_viol'], t['unassigned'], t['broken_pairs'], t['std']))
            success_round = max_rounds + 1
            success_trial = best_p2['trial']
            success_with_split = True
            best_overall = best_p2['result']
            best_overall_score = (best_p2['chain_viol'], best_p2['pj_viol'], best_p2['unassigned'], best_p2['broken_pairs'], best_p2['std'])
            round_summaries.append({
                "round": max_rounds + 1,
                "mult": phase2_mult,
                "chain_ok_count": len(chain_ok_p2),
                "best": best_p2,
                "split_mode": True,
            })
        else:
            # Phase 2도 만족 못 함 → 가장 좋은 결과 선택
            best_p2 = min(phase2_trials, key=lambda t: (t['chain_viol'], t['pj_viol'], t['unassigned'], t['broken_pairs'], t['std']))
            score = (best_p2['chain_viol'], best_p2['pj_viol'], best_p2['unassigned'], best_p2['broken_pairs'], best_p2['std'])
            if best_overall_score is None or score < best_overall_score:
                best_overall_score = score
                best_overall = best_p2['result']
                success_with_split = True
            round_summaries.append({
                "round": max_rounds + 1,
                "mult": phase2_mult,
                "chain_ok_count": 0,
                "best": best_p2,
                "split_mode": True,
            })

    out_df, assigns, report, res_data = best_overall

    # 리포트에 라운드 정보 추가
    extra_report = []
    extra_report.append("")
    if success_round > 0:
        last_summary = round_summaries[-1]
        if success_with_split:
            extra_report.append(f"🔗 **다중 라운드 결과 — 라운드 {success_round} (배율 {last_summary['mult']:.2f} + pairing 분리)에서 부등호 만족!**")
            extra_report.append(f"  ✅ 시도 #{success_trial} 선택: 부등호 위반 0건 / 판정 위반 {best_overall_score[1]}건 / 미배정 {best_overall_score[2]}개 / 깨진 pairing {best_overall_score[3]}개 / 로딩 표준편차 {best_overall_score[4]:.3f}")
        else:
            extra_report.append(f"🎲 **다중 라운드 결과 — 라운드 {success_round}, 배율 {last_summary['mult']:.2f}배에서 부등호 만족!**")
            extra_report.append(f"  ✅ 시도 #{success_trial} 선택: 부등호 위반 0건 / 판정 위반 {best_overall_score[1]}건 / 미배정 {best_overall_score[2]}개 / 로딩 표준편차 {best_overall_score[4]:.3f}")
    else:
        extra_report.append(f"⚠️ **다중 라운드 결과 — {len(round_summaries)}라운드 (배율 {round_summaries[-1]['mult']:.2f}까지, pairing 분리 포함) 시도했으나 부등호 만족 결과 없음**")
        extra_report.append(f"  - 최선 결과: 부등호 위반 {best_overall_score[0]}건 / 판정 위반 {best_overall_score[1]}건 / 미배정 {best_overall_score[2]}개 / 깨진 pairing {best_overall_score[3]}개 / 로딩 표준편차 {best_overall_score[4]:.3f}")
    # 라운드별 요약
    for r in round_summaries:
        n_trials_this_round = 50 if r.get('split_mode') else num_trials
        split_tag = " [pairing 분리]" if r.get('split_mode') else ""
        bp_str = f"/깨진pair {r['best']['broken_pairs']}" if r.get('split_mode') else ""
        extra_report.append(f"  - 라운드 {r['round']} (배율 {r['mult']:.2f}){split_tag}: 부등호 만족 {r['chain_ok_count']}/{n_trials_this_round}회, 최선 = 부등호위반 {r['best']['chain_viol']}/판정위반 {r['best']['pj_viol']}/미배정 {r['best']['unassigned']}{bp_str}")
    extra_report.append("")

    report_lines = report.split("\n")
    insert_idx = 1
    for i, line in enumerate(report_lines):
        if "배정 리포트" in line:
            insert_idx = i + 1
            break
    new_report = "\n".join(report_lines[:insert_idx] + extra_report + report_lines[insert_idx:])
    return out_df, assigns, new_report, res_data