"""평가 모델 v3 — 절대(커리어 클래스) · 폼(이번 시즌) · POT · 신뢰도 분리.

도메인 전문가(아스날 팬) 캘리브레이션 반영:
- v2 는 이번 시즌 ss_rating(=폼)에 앵커해 엘리트·GK·CB 를 저평가했다(Raya 76, Saka 86…).
- v3 는 **절대 OVR = 커리어 클래스**(시장가치 강 prior + 포지션 공정 보정 + 검증/베테랑 보정,
  어린 미검증은 게이팅) 로 두어 Raya 90·Rice 95·Saka 92 급을 재현하고,
  **폼 = 이번 시즌 평점(포지션 스케일)+아웃풋** 을 별도 축으로 둔다.
- POT = 유망주 성장여지. 신뢰도 = 표본/검증(PL 다시즌) 여부.

ground-truth(사용자 아스날 절대/폼)로 계수를 맞춘 뒤 전 리그로 일반화.
"""
from __future__ import annotations

import math

import pandas as pd

from league_level import level as league_level_of, rating_offset


def _num(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return d if math.isnan(f) else f
    except (TypeError, ValueError):
        return d


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def line_of(pos) -> str:
    p = str(pos or "").upper()
    # line_of_row 결과(GK·DEF·MID·ATT)를 다시 넣는 호출부가 많다 — 예전엔 "DEF"·"ATT" 를 못 알아봐
    # 수비수·공격수가 전부 MID 기준(평점 중앙값 7.05·보정 +2)으로 계산됐다(2026-10-15 발견).
    if p in ("GK", "DEF", "MID", "ATT"):
        return p
    if p in ("GK",) or "KEEPER" in p:
        return "GK"
    if p in ("CB", "FB", "RB", "LB", "DF") or "BACK" in p or "DEFEN" in p:
        return "DEF"
    if p in ("ST", "W", "RW", "LW", "FW") or "WING" in p or "FORWARD" in p or "STRIKER" in p:
        return "ATT"
    return "MID"


def line_of_row(row) -> str:
    """역할 기반 라인 분류 — tm_position(트페 역할)을 우선한다.

    football-lineups fl_group(RW/LW 등 포메이션 슬롯)만 쓰면 공격형 미드(Ødegaard·Eze)가
    ATT 로 빠져 미드진이 얇아 보인다. tm_position("Attacking Midfield")은 역할이 정확하므로
    이를 우선하고, 없으면 fl_group/pos 로 폴백한다.
    """
    def _s(v):  # NaN(float) 은 truthy → 'or' 폴백을 깨므로 빈 문자열로 정규화
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)
    # player_frame 이 붙인 '실제로 선 자리'(ESPN 선발 3회+) 우선 — TM '수비형 미드' Lewis-Skelly 는 실제로 풀백(2026-10-15)
    pl = _s(row.get("_line"))
    if pl in ("GK", "DEF", "MID", "ATT"):
        return pl
    t = _s(row.get("tm_position")).lower()
    if "keeper" in t:
        return "GK"
    if "back" in t or "defender" in t:
        return "DEF"
    if "midfield" in t:                       # 수비형/중앙/공격형 미드 전부 MID
        return "MID"
    if "wing" in t or "forward" in t or "striker" in t:
        return "ATT"
    return line_of(_s(row.get("fl_group")) or _s(row.get("pos")))


def value_ovr(v) -> float | None:
    val = _num(v)
    if val <= 0:
        return None
    return 13.04 * math.log10(val) - 16.24


# ── 절대 OVR (커리어 클래스) ──────────────────────────────────────
# 포지션 보정 — 시장은 수비수를 덜, 공격형·창의형 미드를 더 쳐준다. v3.4 까지 DEF·MID +2 · ATT +1 이라
# 몸값 €60~70M 중간대가 일괄로 떠 Zubimendi 88 · Eze 87 · White 85(사용자 기준 85 · 83~84 · 83, 2026-10-15).
# golden(사용자 기준)·스카우트 기준표 조합 탐색으로 정함(GK 는 별도 분기의 _GK_BASE).
_POS_ADJ = {"DEF": 0.5, "MID": -0.5, "ATT": 0.0}
_GK_BASE = 2.0
_SS_MID = {"GK": 6.85, "DEF": 6.95, "MID": 7.05, "ATT": 6.95}  # 포지션별 '평범한 주전' 평점


def _big_match_bonus(ucl_starts=0, uel_starts=0, conf_starts=0, cup_starts=0) -> float:
    """빅매치 검증 가산점 — 유럽>컵, 아주 작게(≈이전의 1/3). 능치 근간(시장가+폼)을 흔들지 않는 선.

    선발 수 기준(검증 표본). UCL 정규 선발 최대 +0.6, UEL +0.4, 컨퍼런스 +0.15, 국내컵 +0.2,
    총 상한 +0.7. (이전 +1.8은 엘리트를 +2 과대평가시켜 축소)
    """
    b = (min(0.6, _num(ucl_starts) * 0.06) + min(0.4, _num(uel_starts) * 0.045)
         + min(0.15, _num(conf_starts) * 0.025) + min(0.2, _num(cup_starts) * 0.02))
    return min(0.7, b)


# 상단 소프트 압축 — 88 이상은 절반 기울기로 눌러 최상위 인플레(Haaland 98 등)를 잡는다.
# 미드티어(~85 이하)는 그대로. 유저 그라운드-트루스에 맞춤.
# v3.4: 잠재력 보정으로 '몸값만 비싼' 젊은 선수가 내려간 만큼 검증된 최상위가 같이 눌리지 않게 0.5→0.6.
_CAP_KNEE, _CAP_SLOPE = 88.0, 0.6


def _soft_cap(raw: float) -> float:
    return _CAP_KNEE + (raw - _CAP_KNEE) * _CAP_SLOPE if raw > _CAP_KNEE else raw


def blended_ss(ss_rating, minutes, prev_ss_rating=None, prev_minutes=None) -> float:
    """이번 시즌 평점에 직전 시즌 평점을 표본 가중으로 섞는다 — 시즌 초 소표본 흔들림 완화.

    직전 시즌 가중 = 직전 출전의 절반 × (1 - 이번 시즌 출전/2500) → 시즌이 진행될수록 0.
    직전 시즌 값이 없으면(25/26 데이터 등) 이번 시즌 평점 그대로.
    """
    ss, mn = _num(ss_rating), _num(minutes)
    pss, pmn = _num(prev_ss_rating), _num(prev_minutes)
    w_prev = 0.5 * pmn * max(0.0, 1.0 - mn / 2500.0) if pss > 0 else 0.0
    w_cur = mn if ss > 0 else 0.0
    if w_cur + w_prev <= 0:
        return ss
    return (ss * w_cur + pss * w_prev) / (w_cur + w_prev)


_CLASS_PRIOR_MIN = 600.0   # 클래스 평점을 포지션 평균 쪽으로 당기는 가상 출전(분)
# 모델 버전 — 바뀌면 rating_history 가 과거 기록을 평행이동해 모델 변경이 선수 추이(▲▼)로 보이지 않게 한다
MODEL_VERSION = "v3.5"
# 잠재력 프리미엄 — 같은 시장가치·리그에서 어린 선수의 실제 경기력(리그 보정 평점)이 낮은 만큼(vov 환산).
# 25/26 1,500분+ 1,450명 회귀(27~29세 기준): 17~20세 −6.8 · 21세 −4.9 · 22세 −5.1 · 23세 −4.4 · 24세 −3.9 ·
# 25세 −3.8 · 26세 −2.4 (같은 회귀에서 30~32세 +5.3 · 33세+ +9.4 — 베테랑 보정과 같은 근거).
# 성능 보정이 평균 −0.8 정도를 이미 반영하므로 그만큼 뺀 값. 예전엔 24세 미만 1살당 0.12 라
# 23세 €120M Anderson 91, 19세 Cubarsí 89 처럼 몸값의 잠재력 몫이 현재 기량으로 들어갔다(2026-10-15 사용자 지적).
# v3.5: 24~25세 주전(Timber·Calafiori)까지 −3 깎던 것을 줄임 — 상위 몸값 구간의 나이 차는 표본이 작아(±2.5)
# 사용자 기준(Timber 86 · Calafiori 85)을 따른다. 21세 이하는 데이터대로 유지(Lewis-Skelly 81~84).
_YOUTH_AGES, _YOUTH_ADJ = (20.0, 21.0, 23.0, 25.0, 26.0, 27.0), (-3.5, -2.5, -1.0, 0.0, 0.0, 0.0)
# 몸값 급등 감쇠 — 직전 시즌보다 오른 시장가치는 한 시즌 활약을 시장이 미리 반영한 몫이라(성능 보정과 이중 계산)
# 새 수준에서 검증되기 전엔 절반만 인정(최대 −3). 26/27 시장가치 2,371명 중 75% 는 그대로, 상위 10% 가 ×1.5+.
# 직전 가치 €5M 미만은 제외 — 1군 데뷔 유망주의 정상 성장이거나 매칭 오류(Cho 직전 €150K)라서.
_VALUE_JUMP_KEEP, _JUMP_MAX_CUT, _JUMP_MIN_PREV = 0.5, 3.0, 5e6
# 리그를 옮긴 선수의 직전 시즌 평점 가중 — 옮긴 선수는 직전 평점이 이번 평점을 훨씬 덜 설명한다
# (26/27 270분+·직전 900분+ 회귀 기울기: 잔류 946명 0.82, 이동 106명 0.51, 4레벨+ 상위 리그행 39명 0.33).
_MOVED_PREV_W = 0.4
# 베테랑 나이 보정 — 시장가치는 나이로 깎이지만 꾸준히 뛰는 베테랑의 기량은 유지된다.
# 25/26 1,500분+ 1,444명(리그·평점 통제) 시장가치 기준점의 27세 대비 차: 30세 −5.0, 32세 −8.3, 34세 −11.6,
# 35세+ −12~−14. 반면 평점(리그 보정)은 24~36세 내내 평균 −0.19~−0.25 로 같다 → 할인 대부분은
# 리세일·잔여 커리어 몫. 측정 할인의 60~75% 를 되돌린다(실제 노쇠분 여유). 출전 1,500분(이번+직전)에 비례.
# 예전엔 30세+ 일괄 +3 이라 Modrić(41, 직전 시즌 평점 7.53·2,811분) 76, Neuer 77 이었다(2026-10-15 사용자 지적).
_VET_AGES, _VET_ADJ = (28.0, 30.0, 32.0, 34.0, 36.0, 38.0), (0.0, 3.0, 5.4, 7.8, 9.5, 11.0)
# GK: 같은 회귀(148명)에서 32세 −4.7, 34세 −11.7, 35세+ −9~−14. GK 전성기는 더 늦게까지 가므로 35세+ 는 80% 가까이.
# 어린 GK 는 잠재력 프리미엄 −0.8/년(하한 −3.2).
# 예전엔 30세+ 일괄 +2 라 24세 €40M Verbruggen 이 31세 €30M Raya(3연속 골든글러브)보다 높았다.
_GK_VET_AGES, _GK_VET_ADJ = (27.0, 30.0, 33.0, 35.0, 37.0, 39.0), (0.0, 2.4, 4.8, 7.5, 10.0, 11.0)
_GK_AGE_PIVOT, _GK_AGE_SLOPE, _GK_AGE_LO = 27.0, 0.8, -3.2
# 리그 가중 — 평점 리그 보정(0.02/레벨 × 8 = 레벨당 0.16)은 성능 보정 상한(±3.5) 밖에서도 적용하고,
# 최종 OVR 에서 레벨당 0.1 을 더 뺀다(포르투갈 −0.9 · 네덜란드 −1.0 · 벨기에 −1.2 · 프랑스 −0.7 ·
# 독일 −0.5 · 스페인 −0.45 · 이탈리아 −0.4). 예전엔 약한 리그 최상위가 상한에 걸려 리그 보정이 사라져
# Diogo Costa 90 · Godts 88 이었다(2026-10-15 사용자 지적, '너무 심하지 않게').
_LEAGUE_OVR_PER_LEVEL = 0.1


def _interp(x: float, xs, ys) -> float:
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


def class_ss(ss_rating, minutes, prev_ss_rating, prev_minutes, ln: str, league_level=None,
             prev_league_level=None) -> float:
    """OVR(커리어 클래스)용 평점 — 표본 수축 + 리그 보정(EPL 기준 환산).

    이번 시즌·직전 시즌을 출전 시간으로 가중하고 포지션 평균을 600분어치 섞는다. 시즌 초 600분짜리
    고평점(예: 포르투갈 8.44)이 클래스를 끌어올리지 않게 하고, 리그 안 상대평가인 Sofascore 평점을
    리그 레벨만큼 낮춰 리그 간에 비교 가능하게 한다(src/league_level.py).
    직전 시즌 평점은 그 시즌에 뛴 리그로 환산한다 — 예전엔 이번 시즌 리그로만 빼서 벨기에에서 넘어온
    Tzolis 의 7.71 이 EPL 7.71 처럼 들어가 OVR 88 이 됐다(2026-10-15).
    """
    rel, off = _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level)
    return rel - off if rel > 0 else 0.0


def _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level):
    """(리그 안 상대 평점 블렌드, 같은 가중의 리그 보정량). class_ss = 앞 − 뒤."""
    ss, mn, pss, pmn = _num(ss_rating), _num(minutes), _num(prev_ss_rating), _num(prev_minutes)
    if ss <= 0 and pss <= 0:
        return 0.0, 0.0
    mid = _SS_MID[ln]
    off_cur = rating_offset(league_level)
    off_prev = rating_offset(prev_league_level) if prev_league_level is not None else off_cur
    w_cur = mn if ss > 0 else 0.0
    w_prev = pmn if pss > 0 else 0.0
    if prev_league_level is not None and league_level is not None and prev_league_level != league_level:
        w_prev *= _MOVED_PREV_W
    w = w_cur + w_prev + _CLASS_PRIOR_MIN
    return ((ss * w_cur + pss * w_prev + mid * _CLASS_PRIOR_MIN) / w,
            (off_cur * w_cur + off_prev * w_prev + off_cur * _CLASS_PRIOR_MIN) / w)


# 골키퍼 선방률·클린시트 — 이번 시즌 + 직전 시즌 + 평균(67%·27%)을 1,200분어치 섞는다.
# 예전엔 이번 시즌 몇 경기 값만 써서 6경기 선방률 75%·CS 67% 인 Verbruggen 이 보정 상한(+7)을 채워 90,
# 지난 시즌 CS 51%(골든글러브)인 Raya 는 89 였다(2026-10-15 사용자 지적).
_GK_SAVE_MID, _GK_CS_MID, _GK_PRIOR_MIN = 67.0, 27.0, 1200.0


def _gk_blend(cur, mn, prev, pmn, mid) -> float | None:
    c, p_ = _num(cur), _num(prev)
    w_c = _num(mn) if c > 0 or (cur is not None and cur == cur and _num(mn) > 0) else 0.0
    w_p = _num(pmn) if (prev is not None and prev == prev and _num(pmn) > 0) else 0.0
    if w_c + w_p <= 0:
        return None
    return (c * w_c + p_ * w_p + mid * _GK_PRIOR_MIN) / (w_c + w_p + _GK_PRIOR_MIN)


# 시장가치가 없을 때(TM 매칭 실패 — 리그마다 3~17명) 기준점: 직전 시즌 시장가치 → 같은 출전 시간대 중앙값
# (26/27 시장가치 있는 선수, 이번+직전 출전 150분 64 · 600분 67 · 1,200분 72.5 · 2,000분 74.5 · 3,000분 75.7, GK 는 3~4 낮음).
# 예전엔 60 으로 시작해 Chelsea Sánchez 가 62, 일괄 77 로 바꾸자 1분 뛴 유망주가 79 였다.
_FB_MIN = (150.0, 600.0, 1200.0, 2000.0, 3000.0)
_FB_VOV = {"GK": (60.7, 64.3, 66.6, 68.2, 72.1), "OUT": (64.0, 67.0, 72.5, 74.5, 75.7)}


def _vov_fallback(ln: str, mn: float) -> float:
    return _interp(mn, _FB_MIN, _FB_VOV["GK" if ln == "GK" else "OUT"])


def absolute_ovr(*, value, ss_rating, minutes, age, pos_group,
                 gk_save_pct=None, gk_cs_pct=None,
                 ucl_starts=0, uel_starts=0, conf_starts=0, cup_starts=0,
                 prev_minutes=None, prev_ss_rating=None, league_level=None,
                 prev_league_level=None, prev_gk_save_pct=None, prev_gk_cs_pct=None, prev_value=None) -> int:
    ln = line_of(pos_group)
    a = _num(age)
    # '검증'(유망주 게이팅·베테랑 보정)은 직전 시즌 출전까지 합산 — 시즌 초 전원 미검증 방지.
    # 직전 시즌 컬럼이 없으면 이번 시즌 출전만(기존 동작).
    mn = _num(minutes) + _num(prev_minutes)
    vov = value_ovr(value)
    pv = value_ovr(prev_value)
    if vov is None:
        vov = pv
    elif pv is not None and vov > pv and _num(prev_value) >= _JUMP_MIN_PREV:
        vov -= min(_JUMP_MAX_CUT, (1.0 - _VALUE_JUMP_KEEP) * (vov - pv))
    rel, off = _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level)
    # GK 성능 리그 보정 — 평점 척도(×8)의 1.5배: 선방·클린시트는 팀 지배력 영향이 커 약한 리그 강팀 GK 가
    # 더 부풀려진다(포르투갈 주전 GK CS 35% vs EPL 31.5%, Porto Costa 직전 시즌 CS 63.6%)
    lg_off = rating_offset(league_level) * 12.0
    base = vov if vov is not None else _vov_fallback(ln, mn)
    proven = _clamp(mn / 1500.0, 0.0, 1.0)
    if ln == "GK":
        # GK 는 시장가·ss 로 변별 불가(값 압축) → 선방%/CS% 를 성능축으로(직전 시즌·평균과 섞어 소표본 완화).
        # Sofascore GK 평점은 슈팅을 많이 받는 약팀 GK 에 유리해 성능축에 넣지 않는다.
        save = _gk_blend(gk_save_pct, minutes, prev_gk_save_pct, prev_minutes, _GK_SAVE_MID)
        cs = _gk_blend(gk_cs_pct, minutes, prev_gk_cs_pct, prev_minutes, _GK_CS_MID)
        if save is not None:
            perf = (_clamp((save - 67.0) * 0.6, -4.0, 4.0)
                    + _clamp(((cs if cs is not None else 27.0) - 27.0) * 0.09, -1.2, 3.0) - lg_off)
        else:
            perf = _clamp((rel - _SS_MID["GK"]) * 8.0, -3.5, 3.5) - off * 8.0 if rel > 0 else 0.0
        # 나이 보정: 어린 GK 의 잠재력 프리미엄은 빼고(−), 30대 GK 의 시장가 할인은 출전 검증만큼 되돌린다(+)
        if a <= 0:
            age_adj = 0.0
        elif a < _GK_AGE_PIVOT:
            age_adj = max(_GK_AGE_LO, _GK_AGE_SLOPE * (a - _GK_AGE_PIVOT))
        else:
            age_adj = _interp(a, _GK_VET_AGES, _GK_VET_ADJ) * proven
        raw = base + _GK_BASE + perf + age_adj
    else:
        # 리그 보정은 상한 밖에서 — 약한 리그 최상위가 상한(+3.5)에 걸려 보정이 사라지지 않게
        perf_adj = _clamp((rel - _SS_MID[ln]) * 8.0, -3.5, 3.5) - off * 8.0 if rel > 0 else 0.0
        vet_adj = _interp(a, _VET_AGES, _VET_ADJ) * proven if a > 0 else 0.0
        raw = base + _POS_ADJ[ln] + perf_adj + vet_adj
    raw += _big_match_bonus(ucl_starts, uel_starts, conf_starts, cup_starts)
    if 0 < a < _YOUTH_AGES[-1] and vov is not None and ln != "GK":     # GK 는 위 나이 보정에 포함
        raw += _interp(a, _YOUTH_AGES, _YOUTH_ADJ)       # 시장가치의 잠재력 프리미엄
    # 어린 미검증만 게이팅(누적 커리어 부족). '검증'은 나이가 아니라 출전시간으로 본다:
    # 어릴수록 완전검증에 필요한 출전이 많지만, 풀시즌을 뛴 유망주(예: Yamal 2262분·16G11A)는
    # 나이로 깎지 않는다. 저출전 유망주만 60 쪽으로 보수화(과대평가 방지).
    if 0 < a <= 21:
        proven_min = 900.0 + (21 - a) * 120.0     # 21세=900분, 18세=1260, 15세=1620 필요
        proven = _clamp(mn / proven_min, 0.1, 1.0)
        raw = proven * raw + (1 - proven) * 60.0
    ovr = _soft_cap(raw) - _LEAGUE_OVR_PER_LEVEL * max(0.0, 100.0 - _num(league_level, 100.0))
    # 유망주 상한 — 아무리 잘해도 established 슈퍼스타(92+)를 넘지 않게 나이별 천장.
    # 18세 91 · 19세 92 · 20세 93 · 21세 94(사실상 무제한). 진짜 최상위는 성숙이 필요.
    if 0 < a <= 21:
        ovr = min(ovr, 88.0 + (a - 15) * 1.0)
    return int(_clamp(round(ovr), 45, 99))


# ── 폼 (이번 시즌) ────────────────────────────────────────────────
# 포지션별 Sofascore 평점 분포 — 25/26 8개 리그 900분+ 정규 출전 2,359명(리그 평균은 거의 같음).
# 예전 공식은 구간 상한(GK 7.00)을 넘으면 계속 올라 GK 정규 주전 중앙값이 96, 99 가 157명이었다.
_F_MEAN = {"GK": 7.02, "DEF": 6.81, "MID": 6.87, "ATT": 6.81}
_F_SD = {"GK": 0.19, "DEF": 0.195, "MID": 0.21, "ATT": 0.23}
_F_PRIOR_MIN = 900.0       # 이번 시즌 평점을 직전 시즌(없으면 포지션 평균) 쪽으로 당기는 가상 출전


def _output_bonus(ln: str, minutes, goals, assists) -> float:
    """공격포인트 가산(z 단위). 270분 미만은 없음."""
    mn = _num(minutes)
    if mn < 270:
        return 0.0
    per90 = (_num(goals) + _num(assists)) / (mn / 90.0)
    if ln == "ATT":
        return min(0.6, per90 * 0.6)
    if ln == "MID":
        return min(0.45, per90 * 0.6)
    return min(0.2, per90 * 0.4)


def form_score(*, ss_rating, minutes, goals=0, assists=0, pos_group="",
               prev_ss_rating=None, prev_minutes=None) -> float | None:
    """폼 원점수(z) — 평점을 직전 시즌(없으면 포지션 평균) 쪽으로 900분어치 수축 + 공격포인트 가산."""
    ss, mn = _num(ss_rating), _num(minutes)
    if ss <= 0 or mn < 200:
        return None   # 표본 부족 → 폼 미산정
    ln = line_of(pos_group)
    pss, pmn = _num(prev_ss_rating), _num(prev_minutes)
    prior = pss if (pss > 0 and pmn >= 450) else _F_MEAN[ln]
    shrunk = (ss * mn + prior * _F_PRIOR_MIN) / (mn + _F_PRIOR_MIN)
    return (shrunk - _F_MEAN[ln]) / _F_SD[ln] + _output_bonus(ln, minutes, goals, assists)


def _form_scale(p: float) -> int:
    """0~1 위치 → 45~99. 중앙 72 · 상위 10% 94 · 상위 1% 99."""
    return int(_clamp(round(45.0 + 54.0 * p), 40, 99))


def form_rating(*, ss_rating, minutes, goals=0, assists=0, pos_group="",
                prev_ss_rating=None, prev_minutes=None) -> int | None:
    """폼(단일 선수, 모집단 없이) — z 를 정규분포 백분위로 근사. 보통은 add_form_column 의 리그 내 순위를 쓴다."""
    z = form_score(ss_rating=ss_rating, minutes=minutes, goals=goals, assists=assists, pos_group=pos_group,
                   prev_ss_rating=prev_ss_rating, prev_minutes=prev_minutes)
    if z is None:
        return None
    return _form_scale(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def add_form_column(df: pd.DataFrame) -> pd.DataFrame:
    """리그 선수 표에 `_form` 열 — 이번 시즌 같은 리그·같은 포지션 안 순위(백분위)를 45~99 로.

    고정 공식은 시즌 초 평점 흩어짐(표준편차 0.32~0.44, 풀시즌 0.19~0.23)을 감당 못 해 99 가
    수십~백여 명이었다. 순위 기준이면 시즌 어느 시점이든 99 는 포지션별 최상위 1~2% 뿐이다.
    """
    if df is None or df.empty:
        return df
    lines = df.apply(line_of_row, axis=1)
    z = [form_score(ss_rating=r.get("ss_rating"), minutes=r.get("minutes"), goals=r.get("goals"),
                    assists=r.get("assists"), pos_group=ln, prev_ss_rating=r.get("prev_ss_rating"),
                    prev_minutes=r.get("prev_minutes"))
         for (_, r), ln in zip(df.iterrows(), lines)]
    zs = pd.Series(z, index=df.index, dtype="float64")
    pct = zs.groupby(lines).rank(pct=True, method="average")
    n = zs.groupby(lines).transform("count")
    # (순위−0.5)/n 꼴로 — 최상위가 1.0(=99) 에 딱 붙지 않게, 표본 작은 포지션은 덜 극단으로
    p = (pct * n - 0.5) / n
    out = df.copy()
    out["_form"] = [(_form_scale(v) if v == v else None) for v in p]
    return out


# ── 잠재력 ────────────────────────────────────────────────────────
def potential(*, absolute: int, age, value) -> int:
    a = _num(age)
    vov = value_ovr(value)
    if a <= 0 or a > 23 or vov is None:
        return absolute
    youth = max(0.0, 23 - a) * 1.0
    pot = max(absolute, 0.4 * absolute + 0.6 * (vov + 3) + youth)
    return int(_clamp(round(pot), absolute, 99))


# ── 신뢰도 (검증 vs 투영) ─────────────────────────────────────────
def confidence(*, minutes, ss_rating) -> str:
    mn = _num(minutes)
    if _num(ss_rating) <= 0:
        return "low"
    if mn >= 1500:
        return "high"
    if mn >= 700:
        return "med"
    return "low"


# ── 역할 (대회별 사용량 기반 · OVR 과 분리된 3번째 축) ────────────────
# 리그 minutes 는 능력치용이지만, '실제 역할'은 리그 주전 여부 + 유럽/컵 검증으로 본다.
# 컵 스탯을 OVR 에 섞지 않고 여기서만 쓴다(도메인 원칙).
def role_tag(*, league_min, euro_starts=0, euro_apps=0, cup_starts=0, cup_apps=0, age=0) -> str:
    lm = _num(league_min)
    es, ea = _num(euro_starts), _num(euro_apps)
    cs, ca = _num(cup_starts), _num(cup_apps)
    a = _num(age)
    if lm >= 1800:                       # ~20경기+ 풀타임 = 확실한 리그 주전
        if es >= 6:
            return "핵심 주전"            # 리그+유럽 둘 다 선발 = 최상위 검증
        if ea >= 3:
            return "주전·유럽 로테이션"
        return "리그 주전"
    if lm >= 1000:                       # 준주전
        return "주전·유럽 로테이션" if es >= 5 else "로테이션"
    # 리그 출전 적음 — 유럽 무대 선발 5+ 면 부상/컵런으로 보고 유럽 로테이션으로 인정
    if es >= 5:
        return "주전·유럽 로테이션"
    if 0 < a <= 21 and (lm > 0 or ca > 0 or ea > 0):
        return "유망주 출전"
    if (cs + ca) >= 4 and es < 2:
        return "컵 전용"
    if lm >= 400 or ea >= 1 or es >= 1:
        return "백업"
    return "주변 자원"


def big_match_proven(*, euro_starts=0, euro_apps=0) -> bool:
    """UCL/UEL 급 무대에서 검증된 표본이 있는가(신뢰도 보정용)."""
    return _num(euro_starts) >= 4 or _num(euro_apps) >= 6


def _prev_level(row):
    pl = row.get("prev_league")
    return league_level_of(pl) if isinstance(pl, str) and pl else None


def ovr_of_row(row) -> int:
    """선수 행 → 절대 OVR (API _player_ovr 와 같은 입력). player_frame 이 리그 표에 `_ovr` 로 미리 붙인다."""
    return absolute_ovr(
        value=row.get("market_value_eur"), ss_rating=row.get("ss_rating"),
        minutes=row.get("minutes"), age=row.get("age"), pos_group=line_of_row(row),
        gk_save_pct=row.get("gk_save_pct"), gk_cs_pct=row.get("gk_cs_pct"),
        ucl_starts=row.get("ucl_starts"), uel_starts=row.get("uel_starts"),
        conf_starts=row.get("conf_starts"), cup_starts=row.get("cup_starts"),
        prev_minutes=row.get("prev_minutes"), prev_ss_rating=row.get("prev_ss_rating"),
        league_level=row.get("_league_level"), prev_league_level=_prev_level(row),
        prev_gk_save_pct=row.get("prev_gk_save_pct"), prev_gk_cs_pct=row.get("prev_gk_cs_pct"),
        prev_value=row.get("prev_market_value_eur"))


def player_line(row) -> dict:
    # 라인은 역할(tm_position) 우선 — FBref 'MF'·'FW,MF' 같은 대분류로 윙어를 미드로 보던 것 수정
    pos = line_of_row(row)
    ab = ovr_of_row(row)
    fm = row.get("_form")
    if fm is None or fm != fm:                     # 리그 내 순위 폼이 없으면(단독 행) 근사식
        fm = form_rating(ss_rating=row.get("ss_rating"), minutes=row.get("minutes"),
                         goals=row.get("goals"), assists=row.get("assists"), pos_group=pos,
                         prev_ss_rating=row.get("prev_ss_rating"), prev_minutes=row.get("prev_minutes"))
    else:
        fm = int(fm)
    return {"ovr": ab, "form": fm, "pot": potential(absolute=ab, age=row.get("age"), value=row.get("market_value_eur")),
            "confidence": confidence(minutes=row.get("minutes"), ss_rating=row.get("ss_rating"))}


# ── 팀 (베스트 XI 가중, 절대·폼 블렌드) ───────────────────────────
_ATT = {"ATT"}
_MID = {"MID"}
_DEF = {"DEF", "GK"}


def team_ratings(full_df, squad) -> dict | None:
    if full_df is None or "squad" not in full_df.columns:
        return None
    sq = full_df[full_df["squad"] == squad].copy()
    if "left_for" in sq.columns:
        sq = sq[sq["left_for"].isna() | (sq["left_for"].astype(str).str.strip() == "")]
    if sq.empty:
        return None
    rows = []
    for _, r in sq.iterrows():
        pl = player_line(r)
        # 팀 강함 = 클래스(절대) 와 이번폼 블렌드. 폼 없으면 절대만.
        strength = pl["ovr"] if pl["form"] is None else round(0.55 * pl["ovr"] + 0.45 * pl["form"])
        rows.append({"ovr": pl["ovr"], "strength": strength, "min": _num(r.get("minutes")),
                     "line": line_of_row(r)})

    def _avg_best(items, n):
        top = sorted(items, key=lambda x: -x["strength"])[:n]
        return round(sum(x["strength"] for x in top) / len(top)) if top else None

    def _unit(codes, n):
        return _avg_best([x for x in rows if x["line"] in codes], n)

    overall = _avg_best(rows, 11)   # 베스트 XI
    att, mid, dfn = _unit(_ATT, 3), _unit(_MID, 4), _unit(_DEF, 4)

    def _i(v, fb=75):
        return int(v) if v is not None else fb
    return {"overall": _i(overall), "attack": _i(att, _i(overall)),
            "midfield": _i(mid, _i(overall)), "defense": _i(dfn, _i(overall)),
            "squad_size": len(rows)}
