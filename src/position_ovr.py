"""
포지션별 OVR — 멀티 포지션 선수는 포지션마다 OVR 이 다르고, 대표 OVR = 가장 잘 맞는 포지션의 OVR(2026-11-02 사용자 A안).

포지션별 OVR = 공통 OVR(몸값·평점·나이 — ratings_v3) + 익숙함 × 역할 기여 − 낯선 자리 감점.
  · 후보 자리 = 실제로 선발로 선 자리(ESPN 라인업, 이번 시즌 1.0 + 지난 시즌 0.5 경기치 MIN_EXP 이상) + TM 대표 포지션 +
    FotMob 첫 포지션. FotMob 의 나머지 포지션 목록은 후보로 삼지 않는다 — 에제 'CDM'(실제 DM 선발 지난 시즌 1경기)이
    DM 84 로 나왔다(2026-11-02 사용자: '실제 뛰었던 포지션과 매칭이 되나'). TM 프로필 대표·그 밖의 포지션(커리어상
    익숙한 자리, src/fetch_tm_positions.py)도 후보 — 최근 두 시즌에 안 뛰었어도 익숙함 하한 CAREER_FAM(감점 −3).
  · 익숙함 = 그 자리 경험 ÷ min(FULL_EXP, 가장 많이 선 자리 경험)(최대 1). 경험 = 선발 경기치 + 같은 라인 이웃 자리 몫(NEAR —
    CM 을 뛰면 DM·AM 도 어느 정도 익숙. 이웃 몫은 이미 후보인 자리에만, 그 자리 선발 경기치만큼까지 더하고 새 후보를
    만들지 않는다). 시즌 안에선 쌓이기만 하고, 시즌이 바뀌어 지난 시즌 선발이 빠져도 TM 커리어 하한이 받친다.
  · 표시값 버티기(hold) — 보이는 OVR 은 반올림 전 값이 반올림 경계를 HOLD 만큼 더 넘을 때만 바뀐다(기준 = 마지막 기록).
  · 낯선 자리 감점 = PEN_MAX × (1 − 익숙함). 땜질(소보슬라이 RB 지난 시즌 10경기 = 5경기치 · DM 14)은 약 −4, 두어 경기치면 약 −6.
    예전 식(경험 점수 차이)은 몇 경기만 뛰어도 거의 다 차서 땜질 자리도 −1 이었다(사용자: '1씩만 깎이는 건 이상').
  · 역할 기여 = 그 포지션 템플릿 레이더 지표(src/position_templates.TEMPLATES — 중앙 미드필더면 파이널서드 패스·패스 성공률·
    롱패스·키패스·xA·드리블·볼 회수·태클)의 같은 템플릿 8개 리그 백분위 평균 → (평균 − 같은 OVR 선수의 보통 백분위) / 50
    × ROLE_MAX × 표본 비중. 볼 순환·탈압박처럼 평점에 덜 잡히는 '연결형' 기여가 여기로 들어온다. 보통 백분위를 빼므로
    전체 척도는 그대로(OVR 구간마다 평균 ±0.2) — 실력은 공통 OVR 이 이미 세었고, 여기는 '그 자리 일에 맞는 정도'만.
    기록은 주로 뛴 자리에서 나온 것이라 덜 뛴 자리의 기여는 익숙함만큼만 반영한다.
대표 포지션 = 포지션별 OVR 이 가장 높은 자리(같으면 지금 쓰이는 자리 — TM·FotMob 현재 포지션, 그다음 더 많이 뛴 자리).
새 자리에서 오래 뛸수록 익숙함이 차서 그 자리가
대표가 된다(레위스스켈리 LB → DM). 가장 많이 뛴 자리는 감점이 없어 대표 OVR 은 공통 OVR + 역할 기여 그대로.
GK 는 한 포지션이라 공통 OVR 그대로.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import position_templates as ptpl

ROLE_MAX = 2.0               # 역할 기여 최대 ±
CONTRIB_FULL_MIN = 1200.0    # 이 출전(안정화 포함 _eff_minutes)이면 역할 기여 전부
POOL_MIN = 450.0             # 백분위 비교 대상 출전 기준(화면 템플릿과 같음)
MIN_EXP = 2.0                # 실제 선발 경기치가 이보다 적은 자리는 후보 아님(라이스 RB 0.5 · 에제 DM 0.5)
PRIMARY_BASE = 3.0           # TM 대표 포지션 · FotMob 첫 포지션 = 선발이 적어도 후보(선발 3경기치로 침)
FULL_EXP = 10.0              # 이만큼(선발 경기치) 선 자리는 완전히 익숙 — 감점 없음
PEN_MAX = 8.0                # 익숙함 0 일 때 감점
HOLD = 0.3                   # 표시값 버티기 여유(hold) — 반올림 경계를 이만큼 더 넘어야 보이는 OVR 이 바뀐다
CAREER_FAM = 0.625           # TM 프로필 대표·그 밖의 포지션(src/fetch_tm_positions.py) = 커리어상 익숙한 자리 — 익숙함 하한
                             # (감점 −3, TM 편집 목록이라 실제 선발보다 보수적으로). 라인업은 이번·지난 시즌뿐이라 그 전 자리(베르나르두 RW)·시즌이 바뀔 때 빠지는 경험을 받친다
# 같은 라인 이웃 자리 몫(익숙함에만) — ESPN 라인업은 같은 중앙 미드필더를 포메이션에 따라 DM·CM·AM 으로 나눠 적고
# (4-2-3-1 의 두 미드 = DM), 윙어는 좌우를 오가고, 수비 라인(CB·풀백)도 서로 어느 정도 익숙하다. 라인이 다른 자리
# (미드 ↔ 수비 등)는 몫이 없다 — CB↔DM 몫을 두면 DM 29경기치의 1/4 만으로 로드리 CB(실제 4경기치)가 완전히 익숙해졌다.
NEAR = {("DM", "CM"): 0.5, ("CM", "AM"): 0.5, ("DM", "AM"): 0.25, ("LW", "RW"): 0.5, ("AM", "LW"): 0.25,
        ("AM", "RW"): 0.25, ("LB", "RB"): 0.25, ("CB", "LB"): 0.25, ("CB", "RB"): 0.25}

FM_ROLE = {"GK": "GK", "CB": "CB", "LB": "LB", "RB": "RB", "LWB": "LB", "RWB": "RB", "CDM": "DM", "CM": "CM",
           "CAM": "AM", "LM": "LW", "RM": "RW", "LW": "LW", "RW": "RW", "ST": "ST", "CF": "ST"}
ROLE_TEMPLATE = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "DM": "DM", "CM": "CM", "AM": "AM",
                 "LW": "W", "RW": "W", "ST": "ST"}


def fm_roles(positions) -> list[str]:
    """FotMob 세부 포지션 문자열('CDM,CAM,RW,CM') → 역할 목록(중복 없이 순서대로)."""
    out: list[str] = []
    for p in str(positions or "").split(","):
        r = FM_ROLE.get(p.strip().upper())
        if r and r not in out:
            out.append(r)
    return out


def experience(starts: dict | None, primary: list[str], career=()) -> dict[str, float]:
    """{후보 자리: 경험(선발 경기치 + 이웃 자리 몫)} — 후보 = 선발 MIN_EXP 경기치 이상 ∪ primary(TM 대표·FotMob 첫 포지션)
    ∪ career(TM 프로필 대표·그 밖의 포지션 — 경험은 선발대로, 익숙함 하한은 choose 가 CAREER_FAM)."""
    direct = {r: float(v) for r, v in (starts or {}).items() if r in ROLE_TEMPLATE and r != "GK" and float(v) > 0}
    cand = {r for r, v in direct.items() if v >= MIN_EXP}
    for r in primary:
        if r in ROLE_TEMPLATE and r != "GK":
            direct[r] = max(direct.get(r, 0.0), PRIMARY_BASE)
            cand.add(r)
    for r in career:
        if r in ROLE_TEMPLATE and r != "GK":
            direct.setdefault(r, 0.0)
            cand.add(r)
    share = dict.fromkeys(cand, 0.0)
    for (a, b), w in NEAR.items():
        for x, y in ((a, b), (b, a)):
            if y in share and direct.get(x):
                share[y] += w * direct[x]
    # 이웃 몫은 그 자리에서 직접 뛴 만큼까지만 — 안 그러면 CB 25경기 선수가 RB 2경기만 서도 RB 가 거의 다 익숙해졌다
    return {r: direct[r] + min(share[r], direct[r]) for r in cand}


def contributions(frames: dict[str, pd.DataFrame], common: dict[str, pd.Series] | None = None,
                  templates=None) -> dict[str, pd.DataFrame]:
    """리그별 세부 지표 표(api _stat_frame) → 리그별 {템플릿: 역할 기여} 표(같은 인덱스). 백분위는 8개 리그 같은 템플릿
    (출전 POOL_MIN+) 기준 — 화면 레이더와 같은 지표·같은 중간 순위 규칙. 시도가 너무 적은 성공률 지표는 뺀다.
    common({리그: 공통 OVR})을 주면 기여 = 그 OVR 의 같은 템플릿 선수가 보통 받는 백분위(표본 직선 회귀) 대비 차이 —
    잘하는 선수는 지표도 높아 '평균 대비'로 두면 이미 OVR 에 든 실력을 한 번 더 세어 상위권만 올라갔다(85+ 평균 +0.7)."""
    templates = templates or [t for t in ptpl.TEMPLATES if t != "GK"]
    parts = [(lg, f) for lg, f in frames.items() if f is not None and not f.empty]
    if not parts:
        return {}
    allf = pd.concat([f for _, f in parts], ignore_index=True)
    sizes = np.cumsum([0] + [len(f) for _, f in parts])
    mins = pd.to_numeric(allf.get("minutes"), errors="coerce").fillna(0).to_numpy(dtype=float)
    eff = pd.to_numeric(allf["_eff_minutes"] if "_eff_minutes" in allf.columns else allf.get("minutes"),
                        errors="coerce").fillna(0).to_numpy(dtype=float)
    weight = np.clip(eff / CONTRIB_FULL_MIN, 0.0, 1.0)
    com = None
    if common is not None:
        com = np.concatenate([pd.to_numeric(common.get(lg, pd.Series(dtype=float)).reindex(f.index), errors="coerce")
                              .to_numpy(dtype=float) for lg, f in parts])
    tpl = allf["_template"].astype(str).to_numpy() if "_template" in allf.columns else np.array([""] * len(allf))
    recs = None
    att: dict = {}
    vals: dict[str, np.ndarray] = {}
    for t in templates:
        in_pool = (tpl == t) & (mins >= POOL_MIN)
        pool = allf[in_pool]
        acc = np.zeros(len(allf))
        cnt = np.zeros(len(allf))
        for k in ptpl.TEMPLATES[t]["radar"]:
            _label, col, inv, rule = ptpl.M[k]
            if col not in allf.columns:
                continue
            srt = np.sort(pd.to_numeric(pool[col], errors="coerce").dropna().to_numpy())
            if srt.size == 0:
                continue
            v = pd.to_numeric(allf[col], errors="coerce").to_numpy(dtype=float)
            lo, hi = np.searchsorted(srt, v, "left"), np.searchsorted(srt, v, "right")
            below = (srt.size - hi) / srt.size if inv else lo / srt.size
            pct = (below + 0.5 * (hi - lo) / srt.size) * 100
            ok = ~np.isnan(v)
            if rule:                                   # 시도 수가 너무 적은 성공률은 화면처럼 빼고 본다
                if rule not in att:
                    recs = recs if recs is not None else allf.to_dict("records")
                    att[rule] = np.array([ptpl.attempts(r, rule) for r in recs], dtype=float)
                ok &= ~(att[rule] < ptpl.MIN_ATTEMPTS)
            acc += np.where(ok, pct, 0.0)
            cnt += ok
        mean = np.where(cnt >= 4, acc / np.maximum(cnt, 1), np.nan)      # 지표가 4개 미만이면 기여 없음
        expect = np.full(len(allf), 50.0)
        if com is not None:
            fit = in_pool & ~np.isnan(mean) & ~np.isnan(com)
            if fit.sum() >= 30:
                b, a = np.polyfit(com[fit], mean[fit], 1)
                expect = np.where(np.isnan(com), 50.0, a + b * com)
        vals[t] = np.where(np.isnan(mean), 0.0, (mean - expect) / 50.0 * ROLE_MAX * weight)
    out = {}
    for i, (lg, f) in enumerate(parts):
        out[lg] = pd.DataFrame({t: v[sizes[i]:sizes[i + 1]] for t, v in vals.items()}, index=f.index)
    return out


def choose(common: float, exp: dict[str, float], contrib: dict[str, float], primary=(), career=()) -> dict:
    """공통 OVR(반올림 전) · {후보 자리: 경험} · {템플릿: 역할 기여} → {main, ovr, raw(대표 반올림 전), by_role: {자리: OVR},
    fam: {자리: 익숙함 0~1}, vals: {자리: 반올림 전}}.
    대표 = 포지션별 OVR(반올림) 최고, 같으면 지금 쓰이는 자리(primary — TM·FotMob 현재 포지션), 그다음 더 많이 뛴 자리."""
    if not exp:
        return {"main": None, "ovr": int(round(common)), "raw": float(common), "by_role": {}, "fam": {}, "vals": {}}
    # 88 넘는 몫은 공통 OVR 처럼 압축(ratings_v3._soft_cap)
    import ratings_v3 as rv3  # noqa: PLC0415
    k = rv3._CAP_SLOPE if common >= rv3._CAP_KNEE else 1.0
    contrib = {t: v * (k if v > 0 else 1.0) for t, v in contrib.items()}
    denom = min(FULL_EXP, max(exp.values()))
    fam = {r: max(min(1.0, e / denom) if denom > 0 else 1.0, CAREER_FAM if r in career else 0.0) for r, e in exp.items()}
    val = {r: min(99.0, max(45.0, common + fam[r] * contrib.get(ROLE_TEMPLATE[r], 0.0) - PEN_MAX * (1.0 - fam[r])))
           for r in exp}
    rank = {r: (int(round(val[r])), r in primary, exp[r]) for r in val}
    main = max(val, key=lambda r: rank[r])
    by_role = {r: rank[r][0] for r in sorted(val, key=lambda r: rank[r], reverse=True)}
    return {"main": main, "ovr": by_role[main], "raw": val[main], "by_role": by_role,
            "fam": {r: round(fam[r], 2) for r in by_role}, "vals": {r: round(val[r], 3) for r in by_role}}


def hold(before, raw: float) -> int:
    """표시값 버티기 — 지금 보이는 OVR(before, 마지막 기록)은 반올림 전 값이 그 숫자에서 0.5 + HOLD 이상 벗어날 때만 바뀐다.
    반올림 경계(83.49 ↔ 83.51)에서 하루 단위로 ±1 이 오가던 것 — 10/14~11/1 OVR 변경의 22% 가 7일 안에 원래대로 돌아왔다."""
    r = int(round(raw))
    if before is None or before != before:
        return r
    b = int(before)
    return b if abs(raw - b) < 0.5 + HOLD else r


def held(res: dict, before) -> dict:
    """choose 결과에 표시값 버티기 — 대표 OVR 은 hold, 다른 자리는 대표와의 차이를 그대로(대표보다 높지 않게)."""
    shown = hold(before, res["raw"])
    if shown == res["ovr"]:
        return res
    by = {r: min(shown, int(round(shown + res["vals"][r] - res["raw"]))) for r in res["by_role"]}
    if res["main"]:
        by[res["main"]] = shown
    return {**res, "ovr": shown, "by_role": by}
