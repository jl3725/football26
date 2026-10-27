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

from league_level import RATING_PER_LEVEL, level as league_level_of, rating_offset


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


# 몸값 → 기준점: 13.04·log10(몸값) − 16.24. VALUE_KNEE 위로는 기울기 VALUE_TOP_SLOPE — 26/27 몸값 인플레로
# €75~120M 공격 자원이 일괄 86.5~89 에 몰렸다(Cherki·Semenyo·Cunha·Mbeumo 88, 2026-10-19 사용자 지적).
VALUE_KNEE, VALUE_TOP_SLOPE = 40e6, 13.04


def value_ovr(v) -> float | None:
    val = _num(v)
    if val <= 0:
        return None
    if val <= VALUE_KNEE:
        return 13.04 * math.log10(val) - 16.24
    return 13.04 * math.log10(VALUE_KNEE) - 16.24 + VALUE_TOP_SLOPE * math.log10(val / VALUE_KNEE)


# ── 절대 OVR (커리어 클래스) ──────────────────────────────────────
# 포지션 보정 — 시장은 수비수를 덜, 공격형·창의형 미드를 더 쳐준다. v3.4 까지 DEF·MID +2 · ATT +1 이라
# 몸값 €60~70M 중간대가 일괄로 떠 Zubimendi 88 · Eze 87 · White 85(사용자 기준 85 · 83~84 · 83, 2026-10-15).
# golden(사용자 기준)·스카우트 기준표 조합 탐색으로 정함(GK 는 별도 분기의 _GK_BASE).
# v3.7(2026-10-19): ATT 0 → −1 — 시장은 같은 경기력이면 공격수에 돈을 더 쳐준다. €75~80M 공격수(Cunha·Mbeumo·Semenyo)
# 가 일괄 88 이던 것(사용자 지적 '그 정도까진 아니다'), 탐색: golden 위반 0 · 스카우트 평균 이탈 0.168→0.137
_POS_ADJ = {"DEF": 0.5, "MID": -0.5, "ATT": -1.0}
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
# 경기력 보정 — (클래스 평점 − 포지션 평균) × PERF_SLOPE, ±PERF_CAP. 시장가치 기준점 위에 얹는 폭.
# v3.6(2026-10-19): 8 → 10 — 두 출처 평균 평점이 한 사이트 버릇을 줄여 경기력을 더 믿을 수 있게 됐고, 평점은 좋은데
# 몸값이 비슷한 선수(Vušković 7.5 vs Konsa 6.8)가 같은 OVR 이던 것(사용자 지적)
PERF_SLOPE, PERF_CAP = 10.0, 3.5
# 유망주 검증 전 기준점 — 출전이 적은 21세 이하를 이 값 쪽으로 당긴다(+ 시장가치 몫 YOUTH_ANCHOR_VALUE)
# v3.6: 시장가치 몫 0 → 0.5 — €50M 16세 Dowman(167분)이 62 로 1분 뛴 €1M 유스와 비슷했다(사용자 지적)
_YOUTH_ANCHOR, YOUTH_ANCHOR_VALUE = 60.0, 0.5
YOUTH_ADJ_SCALE = 0.85     # v3.6: 잠재력 차감 0.85배 — 경기력 가중을 올린 만큼(Lewis-Skelly 기준 81~84 유지)
# 평점이 말하는 수준(PE) — 26/27 전성기(24~29세)·2,500분+ 주전 362명 OVR ≈ 79.85 + 37.8 × (클래스 − 포지션 평균),
# 상관 0.83. 30세+ 는 나이만큼(_VET_PE_W) 이 값 쪽으로 섞는다(시장가치의 나이 할인 대신).
PE_A, PE_B = 79.85, 37.8
# v3.8 탐색(golden 위반 0 · 스카우트 3+ 이탈 0): 6점 넘는 몫의 50% — Šeško 83→82 · Højlund 80→76 · Kvaratskhelia 88→87
UNDERPERF_GAP, UNDERPERF_K, UNDERPERF_MIN_AGE = 6.0, 0.5, 22.0
# 이번 시즌 부진(v3.10, 2026-10-27 사용자: '17위 맨유 쿠냐·음뵈모가 87 — 스탯이 반영되나'). 시장가치는 TM 이 다시 매기기
# 전까지(EPL 은 시즌 중 1~2번) 시즌 시작 때 값이고, 경기력 보정에서 이번 시즌 몫은 시즌 초 10% 남짓이라 이번 시즌 부진이
# 거의 안 보였다. 이번 시즌 평점 수준(리그+유럽·컵, 자기 커리어 수준 쪽으로 SLUMP_PRIOR_MIN 분어치 수축)이
#   ① 자기 커리어 수준보다 낮고(decline) ② 지금 OVR 보다 PE 로 SLUMP_GAP 넘게 낮으면(over)
# min(over, decline) 의 SLUMP_K × min(이번 시즌 출전 / SLUMP_FULL_MIN, 1) 을 뺀다(최대 SLUMP_MAX). 한쪽 방향만 —
# 잘하는 쪽은 경기력 보정과 몸값 재평가가 맡는다. 몸값이 다시 매겨지면 over 가 줄어 저절로 작아진다.
# 탐색(grid_v310 3차, 5,759명): golden 위반 0 · 스카우트 평균 이탈 그대로(0.168) · 바뀐 선수 189 · −2 이상 12(대부분 폼 45~59).
# 쿠냐 87→86(같은 페이스면 1,100분 무렵 84), 음뵈모 87→86. 포지션 평균 쪽으로 수축하면 시즌 초엔 폼 94 브루노까지 깎였고,
# 차감 0.7+ 이면 쿠냐 85 지만 강팀 센터백(Pacho·Bastoni·Inácio)이 스카우트 범위 밖으로 나갔다.
SLUMP_GAP, SLUMP_K, SLUMP_FULL_MIN, SLUMP_MAX, SLUMP_PRIOR_MIN = 3.0, 0.5, 1500.0, 4.0, 600.0
# v3.6 탐색(golden 위반 0 · 스카우트 3+ 이탈 0 · Groß 78 · Dowman 70 · Vušković>Konsa): 36세 45%
_VET_PE_AGES, _VET_PE_W = (30.0, 32.0, 34.0, 36.0), (0.0, 0.18, 0.34, 0.45)
# 모델 버전 — 바뀌면 rating_history 가 과거 기록을 평행이동해 모델 변경이 선수 추이(▲▼)로 보이지 않게 한다
MODEL_VERSION = "v3.11"
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
             prev_league_level=None, hist_ss_rating=None, hist_minutes=None, hist_league_level=None) -> float:
    """OVR(커리어 클래스)용 평점 — 표본 수축 + 리그 보정(EPL 기준 환산).

    이번 시즌·직전 시즌을 출전 시간으로 가중하고 포지션 평균을 600분어치 섞는다. 시즌 초 600분짜리
    고평점(예: 포르투갈 8.44)이 클래스를 끌어올리지 않게 하고, 리그 안 상대평가인 Sofascore 평점을
    리그 레벨만큼 낮춰 리그 간에 비교 가능하게 한다(src/league_level.py).
    직전 시즌 평점은 그 시즌에 뛴 리그로 환산한다 — 예전엔 이번 시즌 리그로만 빼서 벨기에에서 넘어온
    Tzolis 의 7.71 이 EPL 7.71 처럼 들어가 OVR 88 이 됐다(2026-10-15).
    """
    rel, off = _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level,
                            hist_ss_rating, hist_minutes, hist_league_level)
    return rel - off if rel > 0 else 0.0


def _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level,
                 hist_ss_rating=None, hist_minutes=None, hist_league_level=None, extra=(), prior_min=None):
    """(리그 안 상대 평점 블렌드, 같은 가중의 리그 보정량). class_ss = 앞 − 뒤.

    hist_* = 2시즌 전 이상(attach_prev_season.attach_hist — 시즌 가중을 곱한 유효 출전). 시즌이 쌓이면 자동으로
    들어오고, 없으면(지금) 이번 + 직전 시즌만 쓰던 것과 같다.
    extra = [(평점, 가중 출전 분, 대회 수준, 지난 시즌?)] — 유럽·컵 경기(src/allcomp_stats.py). 리그 평점과 나란한 표본으로
    섞고 수준만큼 보정한다(UCL 상위 상대 = EPL 수준 → 보정 0). 2026-10-21 사용자: 챔스 우승 PSG 가 리그 평점만으로 낮았다."""
    ss, mn, pss, pmn = _num(ss_rating), _num(minutes), _num(prev_ss_rating), _num(prev_minutes)
    hss, hmn = _num(hist_ss_rating), _num(hist_minutes)
    if ss <= 0 and pss <= 0 and hss <= 0:
        return 0.0, 0.0
    mid = _SS_MID[ln]
    off_cur = rating_offset(league_level)
    off_prev = rating_offset(prev_league_level) if prev_league_level is not None else off_cur
    w_cur = mn if ss > 0 else 0.0
    w_prev = pmn if pss > 0 else 0.0
    if prev_league_level is not None and league_level is not None and prev_league_level != league_level:
        w_prev *= _MOVED_PREV_W
    w_hist = hmn if hss > 0 else 0.0
    off_hist = rating_offset(hist_league_level) if hist_league_level is not None else off_cur
    if hist_league_level is not None and league_level is not None and hist_league_level != league_level:
        w_hist *= _MOVED_PREV_W
    xs = xw = xo = 0.0
    for x_ss, x_mn, x_lvl, is_prev in extra or ():
        r_, m_ = _num(x_ss), _num(x_mn)
        if r_ <= 0 or m_ <= 0:
            continue
        if is_prev and prev_league_level is not None and league_level is not None and prev_league_level != league_level:
            m_ *= _MOVED_PREV_W
        # 상대 수준은 100(EPL 평균 상대)을 넘을 수 있다 — 리그 보정과 달리 자르지 않는다(맨시티 상대 고평점은 가산)
        lv_ = _num(x_lvl)
        x_off = RATING_PER_LEVEL * (100.0 - lv_) if lv_ > 0 else 0.0
        xs, xw, xo = xs + r_ * m_, xw + m_, xo + x_off * m_
    pm = _CLASS_PRIOR_MIN if prior_min is None else prior_min
    w = w_cur + w_prev + w_hist + xw + pm
    return ((ss * w_cur + pss * w_prev + hss * w_hist + xs + mid * pm) / w,
            (off_cur * w_cur + off_prev * w_prev + off_hist * w_hist + xo + off_cur * pm) / w)


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
                 prev_league_level=None, prev_gk_save_pct=None, prev_gk_cs_pct=None, prev_value=None,
                 hist_ss_rating=None, hist_minutes=None, hist_league_level=None,
                 x_ss_rating=None, x_minutes=None, x_level=None,
                 prev_x_ss_rating=None, prev_x_minutes=None, prev_x_level=None,
                 nt_ss_rating=None, nt_minutes=None, nt_level=None,
                 prev_nt_ss_rating=None, prev_nt_minutes=None, prev_nt_level=None, _parts: list | None = None) -> int:
    """_parts 에 리스트를 주면 단계별 기여(키, 값)를 채운다 — 화면 'OVR 구성'(ovr_parts_of_row)."""
    ln = line_of(pos_group)
    a = _num(age)

    def rec(key: str, delta: float) -> None:
        if _parts is not None and abs(delta) >= 0.05:
            _parts.append((key, round(float(delta), 1)))
    # '검증'(유망주 게이팅·베테랑 보정)은 직전 시즌 출전까지 합산 — 시즌 초 전원 미검증 방지.
    # 직전 시즌 컬럼이 없으면 이번 시즌 출전만(기존 동작).
    mn = _num(minutes) + _num(prev_minutes)
    vov = value_ovr(value)
    pv = value_ovr(prev_value)
    if vov is None:
        vov = pv
    elif pv is not None and vov > pv and _num(prev_value) >= _JUMP_MIN_PREV:
        cut = min(_JUMP_MAX_CUT, (1.0 - _VALUE_JUMP_KEEP) * (vov - pv))
        vov -= cut
        rec("jump", -cut)
    rel, off = _class_parts(ss_rating, minutes, prev_ss_rating, prev_minutes, ln, league_level, prev_league_level,
                            hist_ss_rating, hist_minutes, hist_league_level,
                            extra=[(x_ss_rating, x_minutes, x_level, False), (prev_x_ss_rating, prev_x_minutes, prev_x_level, True),
                                   # 대표팀(allcomp_stats nt_*) — 리그와 무관해 이적 할인(지난 시즌?)을 걸지 않는다
                                   (nt_ss_rating, nt_minutes, nt_level, False), (prev_nt_ss_rating, prev_nt_minutes, prev_nt_level, False)])
    # GK 성능 리그 보정 — 평점 척도(×8)의 1.5배: 선방·클린시트는 팀 지배력 영향이 커 약한 리그 강팀 GK 가
    # 더 부풀려진다(포르투갈 주전 GK CS 35% vs EPL 31.5%, Porto Costa 직전 시즌 CS 63.6%)
    lg_off = rating_offset(league_level) * 12.0
    base = vov if vov is not None else _vov_fallback(ln, mn)
    if _parts is not None:
        _parts.insert(0, ("base" if vov is not None else "base_fallback", round(float(base + (-dict(_parts).get("jump", 0.0))), 1)))
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
        rec("gk_base", _GK_BASE)
        rec("gk_perf", perf)
        rec("age", age_adj)
    else:
        # 리그 보정은 상한 밖에서 — 약한 리그 최상위가 상한(+3.5)에 걸려 보정이 사라지지 않게
        perf_adj = _clamp((rel - _SS_MID[ln]) * PERF_SLOPE, -PERF_CAP, PERF_CAP) - off * 8.0 if rel > 0 else 0.0
        vet_adj = _interp(a, _VET_AGES, _VET_ADJ) * proven if a > 0 else 0.0
        raw = base + _POS_ADJ[ln] + perf_adj + vet_adj
        rec("pos", _POS_ADJ[ln])
        rec("perf", perf_adj)
        rec("vet", vet_adj)
        # 베테랑: 시장가치는 나이로 깎여 실력을 덜 말해 준다 → 나이만큼 '평점이 말하는 수준'(전성기 주전 회귀
        # PE_A + PE_B × (클래스 평점 − 포지션 평균))을 섞는다. 35세 그로스(€2.5M → 기준점 67)가 이번 시즌
        # 평점 7.5(FotMob 7.8)에도 76 이었다(2026-10-19 사용자 지적).
        w_pe = _interp(a, _VET_PE_AGES, _VET_PE_W) * proven if a > 0 and rel > 0 else 0.0
        if w_pe > 0:
            pe = PE_A + PE_B * (rel - off - _SS_MID[ln]) + _POS_ADJ[ln]
            new = (1 - w_pe) * raw + w_pe * pe
            rec("vet_pe", new - raw)
            raw = new
        # 몸값 대비 경기력 저조 — 몸값 기준이 '평점이 말하는 수준'(PE)보다 UNDERPERF_GAP 넘게 높으면 그 초과분의
        # UNDERPERF_K 만큼(두 시즌 2,500분 기준 표본 비례) 뺀다. 부풀려 거래된 몸값(Šeško €75M · 평점 6.5/6.8 → 84,
        # 2026-10-19 사용자 지적). 한쪽 방향만 — 평점보다 실제가 낫다고 평가받는 선수(Kvaratskhelia)는 몸값이 이미 말해 준다
        if rel > 0 and UNDERPERF_K > 0 and a >= UNDERPERF_MIN_AGE:   # 21세 이하는 유망주 보정(차감·검증)이 따로 맡는다
            pe = PE_A + PE_B * (rel - off - _SS_MID[ln]) + _POS_ADJ[ln]
            over = raw - pe - UNDERPERF_GAP
            if over > 0:
                cut = UNDERPERF_K * over * _clamp(mn / 2500.0, 0.0, 1.0)
                rec("underperf", -cut)
                raw -= cut
        # 이번 시즌 부진 — 위 차감 뒤의 값으로 본다(두 규칙이 같은 몫을 두 번 빼지 않게).
        # 이번 시즌 수준은 '자기 커리어 수준' 쪽으로 수축한다 — 포지션 평균 쪽으로 당기면 시즌 초엔 잘하는 엘리트(브루노 폼 94)까지
        # 평범해 보여 깎였다. 두 조건이 다 맞을 때만: 이번 시즌이 자기 수준보다 낮고(decline), OVR 이 이번 시즌 수준보다 높다(over).
        # 이번 시즌 = 클럽 경기(리그+유럽·컵)만 — A매치 교체 30분(하베르츠 네덜란드전 6.36)이 '부진'을 키우지 않게.
        # 대표팀 표본은 자기 커리어 수준(own = rel)에만 들어간다
        c_w = (_num(minutes) if _num(ss_rating) > 0 else 0.0) + (_num(x_minutes) if _num(x_ss_rating) > 0 else 0.0)
        if rel > 0 and SLUMP_K > 0 and a >= UNDERPERF_MIN_AGE and c_w > 0 and _num(ss_rating) > 0:
            c_rel, c_off = _class_parts(ss_rating, minutes, None, None, ln, league_level, None,
                                        extra=[(x_ss_rating, x_minutes, x_level, False)], prior_min=0.0)
            own = rel - off
            cur = ((c_rel - c_off) * c_w + own * SLUMP_PRIOR_MIN) / (c_w + SLUMP_PRIOR_MIN)
            # PE 는 화면 OVR 척도(상단 압축 뒤)로 맞춘 회귀 — 압축 전 값과 비교하면 폼 96 페드리까지 '부진'이 됐다
            over = _soft_cap(raw) - (PE_A + PE_B * (cur - _SS_MID[ln]) + _POS_ADJ[ln]) - SLUMP_GAP
            decline = PE_B * (own - cur)
            if over > 0 and decline > 0:
                cut = min(SLUMP_MAX, SLUMP_K * min(over, decline) * _clamp(c_w / SLUMP_FULL_MIN, 0.0, 1.0))
                rec("slump", -cut)
                raw -= cut
    bm = _big_match_bonus(ucl_starts, uel_starts, conf_starts, cup_starts)
    raw += bm
    rec("big", bm)
    if 0 < a < _YOUTH_AGES[-1] and vov is not None and ln != "GK":     # GK 는 위 나이 보정에 포함
        ya = _interp(a, _YOUTH_AGES, _YOUTH_ADJ) * YOUTH_ADJ_SCALE    # 시장가치의 잠재력 프리미엄
        raw += ya
        rec("youth", ya)
    # 어린 미검증만 게이팅(누적 커리어 부족). '검증'은 나이가 아니라 출전시간으로 본다:
    # 어릴수록 완전검증에 필요한 출전이 많지만, 풀시즌을 뛴 유망주(예: Yamal 2262분·16G11A)는
    # 나이로 깎지 않는다. 저출전 유망주만 60 쪽으로 보수화(과대평가 방지).
    if 0 < a <= 21:
        proven_min = 900.0 + (21 - a) * 120.0     # 21세=900분, 18세=1260, 15세=1620 필요
        proven = _clamp(mn / proven_min, 0.1, 1.0)
        # 검증 전 기준점 — 60 고정이 아니라 시장가치를 일부(YOUTH_ANCHOR_VALUE) 반영: 1분 뛴 €1M 유스는 60 근처,
        # €50M 16세(Dowman)는 그보다 위. 몸값 전부를 믿지는 않는다(예전 1분 유망주 79 사고)
        anchor = _YOUTH_ANCHOR + YOUTH_ANCHOR_VALUE * max(0.0, raw - _YOUTH_ANCHOR)
        new = proven * raw + (1 - proven) * anchor
        rec("gate", new - raw)
        raw = new
    capped = _soft_cap(raw)
    rec("cap", capped - raw)
    lg_w = _LEAGUE_OVR_PER_LEVEL * max(0.0, 100.0 - _num(league_level, 100.0))
    rec("league", -lg_w)
    ovr = capped - lg_w
    # 유망주 상한 — 아무리 잘해도 established 슈퍼스타(92+)를 넘지 않게 나이별 천장.
    # 18세 91 · 19세 92 · 20세 93 · 21세 94(사실상 무제한). 진짜 최상위는 성숙이 필요.
    if 0 < a <= 21 and ovr > 88.0 + (a - 15) * 1.0:
        rec("youth_cap", 88.0 + (a - 15) * 1.0 - ovr)
        ovr = 88.0 + (a - 15) * 1.0
    return int(_clamp(round(ovr), 45, 99))


# ── 폼 (이번 시즌) ────────────────────────────────────────────────
# 포지션별 Sofascore 평점 분포 — 25/26 8개 리그 900분+ 정규 출전 2,359명(리그 평균은 거의 같음).
# 예전 공식은 구간 상한(GK 7.00)을 넘으면 계속 올라 GK 정규 주전 중앙값이 96, 99 가 157명이었다.
_F_MEAN = {"GK": 7.02, "DEF": 6.81, "MID": 6.87, "ATT": 6.81}
_F_SD = {"GK": 0.19, "DEF": 0.195, "MID": 0.21, "ATT": 0.23}
_F_PRIOR_MIN = 900.0       # 이번 시즌 평점을 포지션 평균 쪽으로 당기는 가상 출전(표본 적은 선수는 중간 쪽으로)


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
    """폼 원점수(z) — 이번 시즌 평점을 포지션 평균 쪽으로 900분어치 수축 + 공격포인트 가산.

    예전엔 직전 시즌 평점 쪽으로 당겨서, 이번 시즌 6.90(362분)인 Tzolis 가 지난 시즌(벨기에) 7.71 덕에
    폼 98(절정)이었다(2026-10-19 사용자 지적 '6점대인데 절정?'). 폼은 '이번 시즌' 지표라 지난 시즌은 OVR(클래스)
    에만 쓰고, 여기선 표본이 적으면 중간(평균) 쪽으로만 당긴다. prev_* 인자는 호환용으로 남겨 둔다."""
    ss, mn = _num(ss_rating), _num(minutes)
    if ss <= 0 or mn < 200:
        return None   # 표본 부족 → 폼 미산정
    ln = line_of(pos_group)
    prior = _F_MEAN[ln]
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


def ss_all_comps(row):
    """이번 시즌 폼용 평점 — 리그 평점에 유럽·컵 평점(src/allcomp_stats.attach_x)을 그 리그 척도로 바꿔 출전 분(가중)으로 섞는다.
    유럽·컵 평점의 EPL 환산(평점 − 0.02×(100 − 상대 수준)) + 그 리그 보정 = 그 리그 평점과 같은 눈금.
    2026-10-21: 폼이 리그 평점만이라 챔스에서 펄펄 난 PSG 선수의 '이번 시즌 폼'·팀 강도에 안 들어갔다."""
    ss, mn = _num(row.get("ss_rating")), _num(row.get("minutes"))
    xs, xm, xl = _num(row.get("x_ss_rating")), _num(row.get("x_minutes")), _num(row.get("x_level"))
    if xs <= 0 or xm <= 0 or xl <= 0:
        return row.get("ss_rating")
    x_lg = xs - RATING_PER_LEVEL * (100.0 - xl) + rating_offset(row.get("_league_level"))
    if ss <= 0 or mn <= 0:
        return x_lg
    return (ss * mn + x_lg * xm) / (mn + xm)


def add_form_column(df: pd.DataFrame) -> pd.DataFrame:
    """리그 선수 표에 `_form` 열 — 이번 시즌 같은 리그·같은 포지션 안 순위(백분위)를 45~99 로.

    고정 공식은 시즌 초 평점 흩어짐(표준편차 0.32~0.44, 풀시즌 0.19~0.23)을 감당 못 해 99 가
    수십~백여 명이었다. 순위 기준이면 시즌 어느 시점이든 99 는 포지션별 최상위 1~2% 뿐이다.
    """
    if df is None or df.empty:
        return df
    lines = df.apply(line_of_row, axis=1)
    z = [form_score(ss_rating=ss_all_comps(r), minutes=r.get("minutes"), goals=r.get("goals"),
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


def youth_gated(age, minutes) -> bool:
    """유망주 검증 보정(출전이 적으면 60 쪽으로)이 걸리는가 — absolute_ovr 와 같은 규칙.
    지난 시즌 OVR 이 이 보정에 걸렸으면 지금과 비교한 ▲▼ 는 성장보다 '계산 조건 차이'라 보여 주지 않는다
    (Lewis-Skelly 지난 시즌 709분 → 71, 지금 이번+지난 1,042분 → 81 이 '▲10' 으로 보였다, 2026-10-19)."""
    a, mn = _num(age), _num(minutes)
    return 0 < a <= 21 and mn < 900.0 + (21 - a) * 120.0


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


def _prev_level(row, col: str = "prev_league"):
    pl = row.get(col)
    return league_level_of(pl) if isinstance(pl, str) and pl else None


def _x_args(row) -> dict:
    """유럽·컵 평점 표본(src/allcomp_stats.attach_x) — 열이 없으면 빈 값(리그 평점만, 예전 동작)."""
    return {k: row.get(k) for k in ("x_ss_rating", "x_minutes", "x_level", "prev_x_ss_rating", "prev_x_minutes", "prev_x_level",
                                    "nt_ss_rating", "nt_minutes", "nt_level", "prev_nt_ss_rating", "prev_nt_minutes", "prev_nt_level")}


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
        prev_value=row.get("prev_market_value_eur"),
        hist_ss_rating=row.get("hist_ss_rating"), hist_minutes=row.get("hist_minutes"),
        hist_league_level=_prev_level(row, "hist_league"), **_x_args(row))


# 'OVR 구성' 화면 이름 — 키: (영문, 한글 설명)
PART_LABELS = {
    "base": ("VALUE", "시장가치 기준점"), "base_fallback": ("VALUE", "시장가치 없음 → 출전 시간대 기준점"),
    "jump": ("VALUE JUMP", "몸값 급등 감쇠(새 몸값의 절반만)"), "pos": ("POSITION", "포지션 보정"),
    "perf": ("PERFORMANCE", "경기력 — 평점(Sofascore·FotMob 평균, 이번·지난 시즌, 리그+유럽·컵+대표팀, 대회·상대 수준 보정)"),
    "gk_base": ("GK", "골키퍼 기준"), "gk_perf": ("PERFORMANCE", "선방률·클린시트(리그 보정)"),
    "vet": ("VETERAN", "베테랑 — 나이로 깎인 몸값 일부 되돌림"), "age": ("AGE", "나이 보정"),
    "vet_pe": ("VETERAN FORM", "베테랑 — '평점이 말하는 수준' 쪽으로"), "big": ("BIG MATCH", "유럽대항전·컵 선발"),
    "youth": ("POTENTIAL", "어린 선수 몸값의 잠재력 몫 빼기"), "gate": ("UNPROVEN", "출전 부족 — 검증 전 기준점 쪽으로"),
    "underperf": ("UNDERPERFORM", "몸값 대비 경기력 저조 — 평점 수준보다 크게 높은 몫 일부 빼기"),
    "slump": ("SEASON SLUMP", "이번 시즌 부진 — 몸값이 아직 반영 못 한 이번 시즌 평점 수준 쪽으로"),
    "cap": ("TOP CAP", "88 초과분 압축"), "league": ("LEAGUE", "리그 수준 보정"), "youth_cap": ("AGE CAP", "나이별 천장"),
}


def ovr_parts_of_row(row) -> dict:
    """OVR 이 어떻게 나왔나 — ovr_of_row 와 같은 입력으로 단계별 기여. 화면 'OVR 구성'."""
    parts: list = []
    ovr = absolute_ovr(
        value=row.get("market_value_eur"), ss_rating=row.get("ss_rating"),
        minutes=row.get("minutes"), age=row.get("age"), pos_group=line_of_row(row),
        gk_save_pct=row.get("gk_save_pct"), gk_cs_pct=row.get("gk_cs_pct"),
        ucl_starts=row.get("ucl_starts"), uel_starts=row.get("uel_starts"),
        conf_starts=row.get("conf_starts"), cup_starts=row.get("cup_starts"),
        prev_minutes=row.get("prev_minutes"), prev_ss_rating=row.get("prev_ss_rating"),
        league_level=row.get("_league_level"), prev_league_level=_prev_level(row),
        prev_gk_save_pct=row.get("prev_gk_save_pct"), prev_gk_cs_pct=row.get("prev_gk_cs_pct"),
        prev_value=row.get("prev_market_value_eur"),
        hist_ss_rating=row.get("hist_ss_rating"), hist_minutes=row.get("hist_minutes"),
        hist_league_level=_prev_level(row, "hist_league"), **_x_args(row), _parts=parts)
    return {"ovr": ovr, "parts": [{"key": k, "en": PART_LABELS.get(k, (k, ""))[0], "ko": PART_LABELS.get(k, ("", k))[1],
                                   "value": v} for k, v in parts]}


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


# 팀 라인 OVR 의 실적 보정 — 선수 평점 평균만으론 '수비 조직'이 안 보인다(아스날 25/26 최소 실점인데 26/27 초반
# 맨시티 수비 OVR 이 더 높았다, 2026-10-15). 실적(0~99, 50 = 리그 평균, 1 표준편차 = 20 — api _team_perf)을
# ±2.5 로: 리그 평균보다 1 표준편차 좋으면 +1.
TEAM_PERF_MAX = 2.5


def team_ratings(full_df, squad, perf: dict | None = None, form_w: float = 0.45) -> dict | None:
    """팀 라인 전력. form_w = 이번 시즌 폼 비중 상한(1,350분에 최대). 0 이면 선수 OVR 만 — 리그 간 비교용 '절대 전력'
    (폼은 리그 안 순위라 시즌이 진행될수록 리그 간 격차를 줄인다 — 2026-10-21 검수: 시즌 초 EPL−벨기에 15점, 시즌 말 7점)."""
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
        # 팀 강함 = 클래스(절대) 와 이번폼 블렌드. 폼 없으면 절대만. 폼 비중은 출전 시간에 비례(1,350분에 최대 45%) —
        # 시즌 초 5~6경기 폼이 45% 를 차지해 맨시티 수비(폼 93~98)가 실제 기록보다 크게 앞섰다(2026-10-15).
        wf = form_w * min(1.0, _num(r.get("minutes")) / 1350.0)
        # GK 폼은 빼고 OVR 만 — 폼은 Sofascore 평점인데 GK 평점은 슈팅을 많이 받는 팀 GK 에 유리해 OVR 성능축에서도
        # 쓰지 않는다(absolute_ovr). 넣었을 땐 6경기 폼 Donnarumma 98 · Raya 77 이 수비 라인을 1점 가까이 갈랐다.
        ln = line_of_row(r)
        strength = pl["ovr"] if pl["form"] is None or ln == "GK" else (1 - wf) * pl["ovr"] + wf * pl["form"]
        rows.append({"ovr": pl["ovr"], "strength": strength, "min": _num(r.get("minutes")),
                     "line": ln, "player": str(r.get("player") or "")})

    def _avg_best(items, n):
        top = sorted(items, key=lambda x: -x["strength"])[:n]
        return sum(x["strength"] for x in top) / len(top) if top else None   # 반올림은 실적 보정 뒤 한 번만

    def _pool(codes):
        # 수비 라인 = GK 는 1명까지(주전 GK) + 수비수 — 예전엔 상위 4명에 GK 둘(Alisson·Mamardashvili)이 들어갔다
        gks = sorted([x for x in rows if x["line"] == "GK" and "GK" in codes], key=lambda x: -x["strength"])[:1]
        return [x for x in rows if x["line"] in codes and x["line"] != "GK"] + gks

    def _unit(codes, n):
        return _avg_best(_pool(codes), n)

    def _who(codes, n):
        top = sorted(_pool(codes), key=lambda x: -x["strength"])[:n]
        return [{"player": x["player"], "strength": int(round(x["strength"]))} for x in top]

    # 베스트 XI = 주전 GK 1 + 필드 10 (예전 상위 11명은 GK 둘이 들어가기도 했다)
    _gk1 = sorted([x for x in rows if x["line"] == "GK"], key=lambda x: -x["strength"])[:1]
    _out = sorted([x for x in rows if x["line"] != "GK"], key=lambda x: -x["strength"])[:10]
    overall = _avg_best(_gk1 + _out, 11)
    att, mid, dfn = _unit(_ATT, 3), _unit(_MID, 4), _unit(_DEF, 4)
    adj = {}
    if perf:
        for k, v in (("attack", att), ("midfield", mid), ("defense", dfn)):
            p = perf.get(k)
            adj[k] = _clamp((p - 50.0) / 50.0 * TEAM_PERF_MAX, -TEAM_PERF_MAX, TEAM_PERF_MAX) if p is not None and v is not None else 0.0
        att = None if att is None else att + adj["attack"]
        mid = None if mid is None else mid + adj["midfield"]
        dfn = None if dfn is None else dfn + adj["defense"]
        if overall is not None:
            overall = overall + sum(adj.values()) / 3

    def _i(v, fb=75):
        return int(round(v)) if v is not None else fb
    return {"overall": _i(overall), "attack": _i(att, _i(overall)),
            "midfield": _i(mid, _i(overall)), "defense": _i(dfn, _i(overall)),
            "squad_size": len(rows), "perf_adj": {k: round(v, 1) for k, v in adj.items()},
            "units": {"attack": _who(_ATT, 3), "midfield": _who(_MID, 4), "defense": _who(_DEF, 4)}}
