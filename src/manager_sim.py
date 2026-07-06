"""Manager Change Simulator — 감독이 바뀌면 전술·스쿼드 적합도·영입 우선순위가 어떻게 변하나.

simulate(target_club, new_manager):
  1) 전술 변화: 현 감독 vs 새 감독 스타일/포메이션/전술벡터
  2) 현 스쿼드 적합도 변화: 새 감독 시스템(역할별 스타일)에 안 맞는 선수(교체 후보)
  3) 새 시스템 영입 우선순위: 새 감독이 강조하는 역할 중 스쿼드가 얇은 곳의 후보(스타일 매칭)

'새 감독' = 이름(현재 맡은 클럽의 전술로 대체) 또는 클럽명. 로컬 전용(Qdrant/Neo4j).
사용: python src/manager_sim.py "Manchester Utd" "Mikel Arteta"
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import transfer_fit as tf  # noqa: E402  (_qdrant, _cos, _pool, QCOLLECTION)
from manager_tactics import _load, tactical_profile  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def _mgr_to_club() -> dict:
    _, mgr, _ = _load()
    out = {}
    for _lg, d in mgr.items():
        for club, p in d.items():
            if (p or {}).get("name"):
                out[p["name"].lower()] = club
    return out


def _role_centroid(qc, club, role):
    from qdrant_client import models
    f = models.Filter(must=[models.FieldCondition(key="club", match=models.MatchValue(value=club)),
                            models.FieldCondition(key="pos_detail", match=models.MatchValue(value=role))])
    pts = qc.scroll(tf.QCOLLECTION, scroll_filter=f, with_vectors=True, limit=50)[0]
    return np.mean([p.vector for p in pts], axis=0) if pts else None


def _club_players(qc, club):
    from qdrant_client import models
    f = models.Filter(must=[models.FieldCondition(key="club", match=models.MatchValue(value=club))])
    return qc.scroll(tf.QCOLLECTION, scroll_filter=f, with_vectors=True, with_payload=True, limit=60)[0]


def simulate(target_club: str, new_manager: str) -> dict:
    nm_club = _mgr_to_club().get(new_manager.lower(), new_manager)   # 이름→클럽, 없으면 클럽명으로
    cur, new = tactical_profile(target_club), tactical_profile(nm_club)
    if not cur or not new:
        return {"error": f"프로필 없음 (target={target_club}, new={nm_club})"}
    qc = tf._qdrant()

    # 2) 현 스쿼드 적합도: 각 선수 스타일 vs '새 감독의 같은 역할' centroid
    cent_cache: dict = {}
    misfit = []
    for p in _club_players(qc, target_club):
        role = p.payload.get("pos_detail")
        if not role:
            continue
        if role not in cent_cache:
            cent_cache[role] = _role_centroid(qc, nm_club, role)
        cvec = cent_cache[role]
        if cvec is None:
            continue
        fit = max(0.0, tf._cos(p.vector, cvec)) * 100
        misfit.append({"player": p.payload["name"], "role": role, "sys_fit": round(fit)})
    misfit.sort(key=lambda x: x["sys_fit"])

    # 3) 새 시스템 영입 우선순위: 새 감독 강조 역할 중 타깃 스쿼드 얇은 곳
    pool = tf._pool()
    tgt_sq = pool[pool["squad"].astype(str) == target_club]
    priorities = []
    for ru in new.get("role_usage", [])[:5]:
        role = ru["role"]
        depth = int((tgt_sq["_pos_detail"] == role).sum())
        if depth <= 2 and role not in ("Goalkeeper",):
            cvec = _role_centroid(qc, nm_club, role)
            cands = []
            if cvec is not None:
                hits = qc.search(tf.QCOLLECTION, query_vector=cvec.tolist(), limit=40)
                for h in hits:
                    if h.payload.get("club") == target_club or h.payload.get("pos_detail") != role:
                        continue
                    cands.append(f"{h.payload['name']}({h.payload['league']})")
                    if len(cands) >= 4:
                        break
            priorities.append({"role": role, "share": ru["minutes_share"], "depth": depth, "candidates": cands})
    return {"target_club": target_club, "new_manager": new_manager, "new_from_club": nm_club,
            "current": cur, "new": new, "squad_misfit": misfit[:6], "priorities": priorities}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    club = sys.argv[1] if len(sys.argv) > 1 else "Manchester Utd"
    newm = sys.argv[2] if len(sys.argv) > 2 else "Mikel Arteta"
    r = simulate(club, newm)
    if "error" in r:
        print("❌ " + r["error"]); return 1
    cur, new = r["current"], r["new"]
    print("=" * 78)
    print(f"Manager Change Simulator — {club} 에 {newm}({r['new_from_club']} 전술) 부임 가정")
    print("=" * 78)
    print(f"  현 감독({cur['manager']}): {', '.join(cur['style_tags'])} | {cur['formation'] or '?'}")
    print(f"  새 감독({new['manager']}): {', '.join(new['style_tags'])} | {new['formation'] or '?'}")
    print("  전술벡터 변화(주요):")
    for ax in ("pressing", "control", "creativity", "attack_output", "disruption"):
        a, b = cur["tactical_vector"].get(ax), new["tactical_vector"].get(ax)
        if a is not None and b is not None:
            print(f"     {ax:14} {a:5.0f} → {b:5.0f} ({b - a:+.0f})")
    print("\n  🔻 새 시스템에 덜 맞는 현 스쿼드(교체 검토):")
    for m in r["squad_misfit"]:
        print(f"     {m['player']:22} {m['role']:16} sys_fit {m['sys_fit']}")
    print("\n  🎯 새 시스템 영입 우선순위(강조 역할 · 스쿼드 얇음):")
    for p in r["priorities"]:
        print(f"     {p['role']:18} (기용 {int(p['share']*100)}% · 현뎁스 {p['depth']}) → {', '.join(p['candidates']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
