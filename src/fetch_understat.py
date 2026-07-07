"""
Understat에서 2025-26 EPL 선수별 xG 지표를 수집해 FBref 기본 데이터와 병합한다.

최종 출력: data/players_full_2025_2026.csv
  FBref basic (출전시간·크로스·태클·인터셉트) +
  Understat    (xg/90, npxg/90, xa/90, key_passes/90, shots/90)

실행: python src/fetch_understat.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import soccerdata as sd
from unidecode import unidecode

from leagues import (
    ACTIVE_LEAGUE,
    SEASON_FBREF,
    data_path,
    league_config,
    register_soccerdata_custom_leagues,
)

register_soccerdata_custom_leagues()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FBREF = data_path("players")
OUT = data_path("players_full")
CFG = league_config()
LEAGUE = CFG.fbref_id


def normalize_name(s: str) -> str:
    """이름 비교용 정규화: 악센트 제거 + 소문자 + 공백 정리."""
    return unidecode(str(s)).lower().strip()


def merge_key(team: str, player: str) -> str:
    return f"{normalize_name(team)}|{normalize_name(player)}"


SofascoreMergeTarget = str | tuple[str, str]

SOFASCORE_PLAYER_ALIASES: dict[str, dict[tuple[str, str], SofascoreMergeTarget]] = {
    "EPL": {
        ("crystal palace", "yeremy pino"): "Yeremi Pino",
        ("nottingham forest", "callum hudson odoi"): "Callum Hudson-Odoi",
        ("aston villa", "emiliano buendia"): "Emi Buendía",
        ("manchester city", "nico gonzalez"): "Nicolás González",
        ("burnley", "lucas pires"): "Lucas",
        ("manchester city", "antoine semenyo"): ("Bournemouth", "Antoine Semenyo"),
        ("crystal palace", "jorgen strand larsen"): ("Wolves", "Jørgen Strand Larsen"),
    },
    "LaLiga": {
        ("osasuna", "alejandro catena"): "Catena",
        ("alaves", "jonny otto"): "Jonny Castro",
        ("alaves", "youssef enriquez"): "Youssef Lekhedim",
        ("alaves", "mariano diaz"): "Mariano",
        ("athletic club", "hugo rincon"): ("Girona", "Hugo Rincón"),
        ("athletic club", "julen agirrezabala"): ("Valencia", "Julen Agirrezabala"),
        ("girona", "viktor tsygankov"): "Viktor Tsyhankov",
        ("athletic club", "nico serrano"): "Nicolás Serrano",
        ("atletico madrid", "thomas lemar"): ("Girona", "Thomas Lemar"),
        ("atletico madrid", "carlos martin"): ("Rayo Vallecano", "Carlos Martín"),
        ("atletico madrid", "dani martinez"): "Daniel Martinez",
        ("barcelona", "pablo gavi"): "Gavi",
        ("celta vigo", "aleix febas"): ("Elche", "Aleix Febas"),
        ("celta vigo", "manuel sanchez"): ("Levante", "Manu Sánchez"),
        ("celta vigo", "javi galan"): ("Osasuna", "Javi Galán"),
        ("celta vigo", "hugo burcio"): "Hugo García",
        ("real betis", "cucho hernandez"): "Cucho",
        ("espanyol", "jofre carreras"): "Jofre",
        ("espanyol", "antoniu roca"): "Antoniu",
        ("espanyol", "miguel rubio"): "Miguel Ángel Rubio",
        ("espanyol", "angel fortuno"): "Fortuño",
        ("getafe", "damian caceres"): "Damián",
        ("getafe", "jose luis perez"): "Joselu Pérez",
        ("getafe", "juan iglesias"): "Iglesias",
        ("girona", "lass kourouma"): "Lancinet Kourouma",
        ("levante", "roger brugue"): "Brugui",
        ("levante", "manuel sanchez"): "Manu Sánchez",
        ("levante", "tai abed"): "Tay Abed",
        ("osasuna", "raul garcia de haro"): "Raúl",
        ("oviedo", "abdel rahim"): "Rahim Bonkano",
        ("sevilla", "jose angel carmona"): "Carmona",
        ("athletic club", "dani vivian"): "Daniel Vivian",
        ("villarreal", "luiz junior"): "Luiz Lúcio Reis Júnior",
        ("rayo vallecano", "isi palazon"): "Isaac Palazón Camacho",
        ("rayo vallecano", "alemao"): "Alexandre Alemão",
        ("real betis", "abdessamad ezzalzouli"): "Abde Ezzalzouli",
        ("real betis", "nobel mendy"): ("Rayo Vallecano", "Nobel Mendy"),
        ("valencia", "jose luis gaya"): "José Luis Gayà",
        ("rayo vallecano", "pathe ismael ciss"): "Pathé Ciss",
        ("real madrid", "thiago pitarch"): "Thiago Pinar",
        ("real sociedad", "jon pacheco"): ("Alavés", "Jon Pacheco"),
        ("real sociedad", "javi lopez"): ("Oviedo", "Javi López"),
        ("real sociedad", "orri oskarsson"): "Orri Steinn Óskarsson",
        ("real sociedad", "job ochieng"): "Job Ochieng'",
        ("real sociedad", "gorka carrera zarranz"): "Gorka Carrera",
        ("real sociedad", "dani diaz"): "Daniel Díaz",
        ("valencia", "jose copete"): "Copete",
        ("valencia", "pepelu"): "José Luis García Vayá",
        ("espanyol", "kike garcia"): "Kiké",
        ("levante", "jon ander olasagasti"): "Olasagasti",
        ("alaves", "abderrahman rebbach"): "Abde Rebbach",
        ("levante", "etta eyong"): "Karl Etta Eyong",
        ("celta vigo", "javier rueda"): "Javi Rueda",
        ("athletic club", "robert navarro"): "Roberto Navarro",
        ("athletic club", "alejandro rego mora"): "Alejandro Rego",
        ("sevilla", "juan iglesias"): ("Getafe", "Iglesias"),
        ("sevilla", "rafa mir"): ("Elche", "Rafa Mir"),
        ("sevilla", "oso"): "Joaquín Martínez Gauna",
        ("sevilla", "peque fernandez"): "Peque",
        ("sevilla", "miguel sierra"): "Miguel Ángel Sierra",
        ("valencia", "andre almeida"): "Domingos André Ribeiro Almeida",
        ("villarreal", "carlos romero"): ("Espanyol", "Carlos Romero"),
        ("villarreal", "ramon terrats"): ("Espanyol", "Ramón Terrats"),
        ("villarreal", "dani parejo"): "Daniel Parejo",
        ("villarreal", "alexander freeman"): "Alex Freeman",
        ("sevilla", "andres castrin"): "Castrin",
        ("rayo vallecano", "fran perez"): "Francisco Perez",
    },
    "SerieA": {
        ("cagliari", "michel adopo"): "Michel Ndary Adopo",
        ("como", "nico paz"): "Nicolás Paz",
        ("roma", "evan ndicka"): "Obite N'Dicka",
        ("como", "marc kempf"): "Marc-Oliver Kempf",
        ("atalanta", "ederson"): "Éderson Silva",
        ("juventus", "bremer"): "Gleison Bremer",
        ("inter", "yann bisseck"): "Yann Aurel Bisseck",
        ("parma", "oliver sorensen"): "Oliver Jensen",
        ("lecce", "kialonda gaspar"): "Kialonda",
        ("napoli", "eljif elmas"): "Elif Elmas",
        ("napoli", "frank anguissa"): "Andre-Frank Zambo Anguissa",
        ("cagliari", "ze pedro"): "Zé Pedro Figueiredo",
        ("cremonese", "romano floriani mussolini"): "Romano Floriani",
        ("torino", "rafael obrador"): "Rafel Obrador",
        ("inter", "francesco pio esposito"): "Francesco Esposito",
        ("lazio", "oliver provstgaard"): "Oliver Nielsen",
        ("pisa", "henrik wendel meister"): "Henrik Meister",
        ("hellas verona", "jean daniel akpa-akpro"): "Jean-Daniel Akpa-Akpro",
        ("hellas verona", "armel bella-kotchap"): "Armel Bella Kotchap",
        ("hellas verona", "moatasem al-musrati"): "Al-Musrati",
        ("bologna", "charalampos lykogiannis"): "Babis Lykogiannis",
        ("pisa", "nicolas"): "Nícolas Andrade",
        ("udinese", "vakoun issouf bayo"): "Vakoun Bayo",
        ("juventus", "juan cabal"): "Juan David Cabal",
        ("torino", "tino anjorin"): "Faustino Anjorin",
        ("cremonese", "mikayil faye"): "Mikayil Ngor Faye",
        ("parma", "benjamin cremaschi"): "Ben Cremaschi",
        ("pisa", "samuel iling junior"): "Samuel Iling-Junior",
        ("cremonese", "faris moumbagna"): "Faris Pemi Moumbagna",
        ("genoa", "wedtoin latif ouedraogo"): "Latif Ouedraogo",
        ("napoli", "nikita contini"): "Nikita Contini Baranovsky",
        ("milan", "cheveyo mul-balentien"): "Cheveyo Muy",
        ("genoa", "joi xheto nuredini"): "Joi Nuredini",
    },
    "Eredivisie": {
        ("twente", "kristian nokkvi hlynsson"): "Kristian Hlynsson",
        ("ajax", "oliver edvardsen"): "Oliver Valaker Edvardsen",
        ("heerenveen", "nikolai hopland"): "Nikolai Soyset Hopland",
        ("feyenoord", "tobias elshout van den"): "Tobias van den Elshout",
    },
}


def sofascore_identity_for_merge(team: str, player: str) -> tuple[str, str]:
    aliases = SOFASCORE_PLAYER_ALIASES.get(ACTIVE_LEAGUE, {})
    target = aliases.get((normalize_name(team), normalize_name(player)))
    if isinstance(target, tuple):
        return target
    return team, target or player


def read_understat_or_empty(fb: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(columns=[
        "team",
        "player",
        "minutes",
        "xg",
        "np_xg",
        "xa",
        "key_passes",
        "shots",
        "xg_chain",
        "goals",
        "assists",
    ])
    try:
        if ACTIVE_LEAGUE in {"LigaPortugal", "Eredivisie", "BelgianProLeague"}:
            raise RuntimeError(f"Understat does not cover {CFG.name}")
        us = sd.Understat(leagues=LEAGUE, seasons=SEASON_FBREF)
        return us.read_player_season_stats().reset_index()
    except Exception as e:
        print(f"skip ({e})", end=" ", flush=True)
        return empty


def main() -> int:
    fb = pd.read_csv(FBREF)
    fb["_key"] = [merge_key(t, p) for t, p in zip(fb["squad"], fb["player"])]

    # ── Understat 수집 ──────────────────────────────────────────────────────
    print("→ Understat xG 수집 ...", end=" ", flush=True)
    udf = read_understat_or_empty(fb)
    print(f"{len(udf)}명 ✓")

    n90 = udf["minutes"] / 90
    udf["xg_p90"]       = (udf["xg"]         / n90).round(3)
    udf["npxg_p90"]     = (udf["np_xg"]       / n90).round(3)
    udf["xa_p90"]       = (udf["xa"]          / n90).round(3)
    udf["kp_p90"]       = (udf["key_passes"]  / n90).round(3)
    udf["shots_p90"]    = (udf["shots"]       / n90).round(3)
    udf["xg_chain_p90"] = (udf["xg_chain"]    / n90).round(3)

    udf["_key"] = [merge_key(t, p) for t, p in zip(udf["team"], udf["player"])]

    # ── FBref 기본 로드 ─────────────────────────────────────────────────────
    fb = pd.read_csv(FBREF)
    fb["_key"] = [merge_key(t, p) for t, p in zip(fb["squad"], fb["player"])]

    # ── 병합 ────────────────────────────────────────────────────────────────
    # goals=페널티 포함 시즌 총득점, assists=시즌 총도움 (Understat raw 누적치)
    u_cols = ["_key", "xg_p90", "npxg_p90", "xa_p90", "kp_p90", "shots_p90",
              "xg_chain_p90", "goals", "assists"]
    merged = fb.merge(udf[u_cols], on="_key", how="left")
    merged = merged.drop(columns=["_key"])

    match_rate = merged["xg_p90"].notna().mean()

    # ── 결측 보강 (NaN → 합리적 대체값) ──────────────────────────────────────
    # Understat 미매칭 선수: FBref 관측값으로 폴백
    merged["npxg_p90"]  = merged["npxg_p90"].fillna(merged["npg_per90"])
    merged["xa_p90"]    = merged["xa_p90"].fillna(merged["ast_per90"])
    merged["shots_p90"] = merged["shots_p90"].fillna(merged["sh_per90"])
    merged["kp_p90"]    = merged["kp_p90"].fillna(merged["ast_per90"] * 3)  # 키패스≈도움의 수배
    # 골/어시 총합 결측: per90 × 출전90 으로 추정(미매칭은 대부분 fringe 선수)
    merged["goals"]   = merged["goals"].fillna((merged["npg_per90"] * merged["minutes"] / 90).round())
    merged["assists"] = merged["assists"].fillna((merged["ast_per90"] * merged["minutes"] / 90).round())
    merged["goals"]   = merged["goals"].fillna(0).astype(int)
    merged["assists"] = merged["assists"].fillna(0).astype(int)
    # FBref basic 자체 결측(크로스/수비 등)은 0으로
    for c in ["crosses_per90", "fouled_per90", "offsides_per90",
              "interceptions_per90", "tackles_won_per90", "fouls_per90",
              "xg_chain_p90", "xg_p90"]:
        merged[c] = merged[c].fillna(0)

    # ── FBref 키퍼 지표 보강 (GK 슬롯 표시용) ────────────────────────────────
    try:
        fbk = sd.FBref(leagues=LEAGUE, seasons=SEASON_FBREF)
        kdf = fbk.read_player_season_stats("keeper").reset_index()
        kdf.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in kdf.columns]
        save_col = next((c for c in kdf.columns if c.endswith("Save%")), None)
        cs_col   = next((c for c in kdf.columns if c.endswith("CS%")), None)
        kdf["_key"] = [merge_key(t, p) for t, p in zip(kdf["team"], kdf["player"])]
        keep = {"_key": "_key"}
        if save_col: keep[save_col] = "gk_save_pct"
        if cs_col:   keep[cs_col]   = "gk_cs_pct"
        kk = kdf[list(keep)].rename(columns=keep).drop_duplicates("_key", keep="first")
        merged["_key"] = [merge_key(t, p) for t, p in zip(merged["squad"], merged["player"])]
        merged = merged.merge(kk, on="_key", how="left").drop(columns=["_key"])
        print(f"  키퍼 지표 보강: Save%={save_col is not None}, CS%={cs_col is not None}")
    except Exception as e:
        print(f"  키퍼 보강 건너뜀: {e}")
        merged["gk_save_pct"] = np.nan

    # ── 팀 수비+공격 강도 머지 (있을 때만) ─────────────────────────────────
    td_path = data_path("team_defense")
    if td_path.exists():
        td = pd.read_csv(td_path)
        cols = ["squad", "goals_against", "goals_against_per_game", "defense_score"]
        rename = {
            "goals_against": "team_goals_against",
            "goals_against_per_game": "team_ga_per_game",
            "defense_score": "team_defense_score",
        }
        # 신규 컬럼 (있을 때만) — 팀 공격 강도
        if "goals_for" in td.columns:
            cols += ["goals_for", "goals_for_per_game", "attack_score"]
            rename.update({
                "goals_for": "team_goals_for",
                "goals_for_per_game": "team_gf_per_game",
                "attack_score": "team_attack_score",
            })
        merged = merged.merge(td[cols].rename(columns=rename), on="squad", how="left")
        td_match = merged["team_defense_score"].notna().mean()
        print(f"  팀 수비+공격 머지: 매칭률 {td_match*100:.0f}%")
    else:
        print("  team_defense 없음 (src/fetch_team_defense.py 먼저 실행)")

    # ── Sofascore advanced stats 머지 (있을 때만) ───────────────────────────
    ss_path = data_path("players_sofascore_stats")
    if ss_path.exists():
        ss = pd.read_csv(ss_path)
        # 평탄화: per-90 + 비율 컬럼 묶음
        m = ss["minutesPlayed"].replace(0, np.nan)
        n90 = m / 90.0
        ss_add = pd.DataFrame({
            "_key": [
                merge_key(*sofascore_identity_for_merge(t, p))
                for t, p in zip(ss["squad"], ss["player"])
            ],
            "_ss_squad": ss["squad"],
            "_ss_player": ss["player"],
            "_ss_minutes_raw": ss["minutesPlayed"],
            # 비율 (이미 % 형태)
            "ss_rating":            ss["rating"],
            "pass_pct":             ss["accuratePassesPercentage"],
            "long_ball_pct":        ss["accurateLongBallsPercentage"],
            "cross_acc_pct":        ss["accurateCrossesPercentage"],
            "dribble_success_pct":  ss["successfulDribblesPercentage"],
            "tackles_won_pct":      ss["tacklesWonPercentage"],
            "aerial_won_pct":       ss["aerialDuelsWonPercentage"],
            "ground_duels_won_pct": ss["groundDuelsWonPercentage"],
            "total_duels_won_pct":  ss["totalDuelsWonPercentage"],
            # 카운트 → per-90
            "key_passes_per90":           ss["keyPasses"] / n90,
            "big_chances_created_per90":  ss["bigChancesCreated"] / n90,
            "clearances_per90":           ss["clearances"] / n90,
            "blocked_shots_per90":        ss["blockedShots"] / n90,
            "outfielder_blocks_per90":    ss["outfielderBlocks"] / n90,
            "interceptions_per90_ss":     ss["interceptions"] / n90,
            "recoveries_per90":           ss["ballRecovery"] / n90,
            "aerial_won_per90":           ss["aerialDuelsWon"] / n90,
            "tackles_won_per90_ss":       ss["tacklesWon"] / n90,
            "ground_duels_won_per90":     ss["groundDuelsWon"] / n90,
            "errors_per90":               (ss["errorLeadToGoal"].fillna(0) + ss["errorLeadToShot"].fillna(0)) / n90,
            "possession_won_att_per90":   ss["possessionWonAttThird"] / n90,
            "successful_dribbles_per90":  ss["successfulDribbles"] / n90,
            "final_third_passes_per90":   ss["accurateFinalThirdPasses"] / n90,
            # GK
            "gk_saves_per90":         ss["saves"] / n90,
            "gk_clean_sheets":        ss["cleanSheet"],
            "gk_high_claims_per90":   ss["highClaims"] / n90,
            "gk_runs_out_per90":      ss["runsOut"] / n90,
            "gk_punches_per90":       ss["punches"] / n90,
            "gk_crosses_not_claimed": ss["crossesNotClaimed"],
            "ss_appearances":         ss["appearances"],
            "ss_minutes":             ss["minutesPlayed"],
        })
        merged["_key"] = [merge_key(t, p) for t, p in zip(merged["squad"], merged["player"])]
        ss_add = ss_add.sort_values("ss_minutes", ascending=False).drop_duplicates("_key", keep="first")
        ss_value_cols = [c for c in ss_add.columns if not c.startswith("_")]
        merged = merged.merge(ss_add[["_key", *ss_value_cols]], on="_key", how="left")
        minute_fallback = 0
        if ACTIVE_LEAGUE in {"LigaPortugal", "Eredivisie", "BelgianProLeague"}:
            used_ss_keys = set(merged.loc[merged["ss_rating"].notna(), "_key"])
            available = ss_add[~ss_add["_key"].isin(used_ss_keys)].copy()
            for idx, row in merged[merged["ss_rating"].isna()].sort_values("minutes", ascending=False).iterrows():
                team_pool = available[available["_ss_squad"] == row["squad"]].copy()
                if team_pool.empty or pd.isna(row.get("minutes")):
                    continue
                team_pool["_minute_diff"] = (team_pool["_ss_minutes_raw"] - row["minutes"]).abs()
                team_pool = team_pool.sort_values("_minute_diff")
                best = team_pool.iloc[0]
                second_diff = team_pool.iloc[1]["_minute_diff"] if len(team_pool) > 1 else 9999
                if best["_minute_diff"] <= 8 or (best["_minute_diff"] <= 20 and second_diff - best["_minute_diff"] >= 8):
                    for col in ss_value_cols:
                        merged.at[idx, col] = best[col]
                    available = available.drop(index=best.name)
                    minute_fallback += 1

        merged = merged.drop(columns=["_key"])
        ss_match = merged["ss_rating"].notna().mean()
        print(f"  Sofascore stats 머지: {len(ss_add)}행 → 매칭률 {ss_match*100:.0f}%")
        if minute_fallback:
            print(f"  Sofascore minutes fallback: {minute_fallback}명")
    else:
        print("  Sofascore stats 없음 (src/fetch_sofascore_stats.py 먼저 실행)")

    merged.to_csv(OUT, index=False, encoding="utf-8")

    print(f"[OK] 저장: {OUT.name}  ({len(merged)}명, Understat 매칭률 {match_rate*100:.0f}%)")
    print(f"\n[Understat 보강 후 {CFG.default_team} 샘플]")
    ars = merged[merged["squad"] == CFG.default_team].sort_values("minutes", ascending=False)
    print(ars[["player", "minutes", "npxg_p90", "xa_p90", "kp_p90", "shots_p90",
               "interceptions_per90", "tackles_won_per90"]].head(8).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
