"""
Arsenal/Man Utd 선수 Sofascore id + 등번호 수동 시딩 (IP 차단 중 임시).
웹 검색으로 확보한 id를 이미지 CDN(img.sofascore.com)으로 검증 후 player_slots에 기록.
실행: python _seed_ids.py
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
import tls_requests
from unidecode import unidecode

DATA = Path(__file__).resolve().parent / "data"
SLOTS = DATA / "player_slots_2025_2026.csv"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.sofascore.com/"}

# norm_key → (sofa_id, number).  number 미확인은 "".
SEED = {
    # Arsenal
    "david raya": ("581310", "1"),
    "jurrien timber": ("958959", "12"),
    "william saliba": ("941168", "2"),
    "gabriel magalhaes": ("869792", "6"),
    "riccardo calafiori": ("957602", "33"),
    "martin odegaard": ("547410", "8"),
    "martin zubimendi": ("966837", "36"),
    "declan rice": ("856714", "41"),
    "bukayo saka": ("934235", "7"),
    "viktor gyokeres": ("804508", "14"),
    "leandro trossard": ("135666", "19"),
    "eberechi eze": ("864921", "10"),
    # Arsenal — 추가 선수
    "gabriel jesus": ("794839", "9"),
    "gabriel martinelli": ("922573", "11"),
    "kai havertz": ("836705", "29"),
    "mikel merino": ("592010", "23"),
    "ben white": ("846036", "4"),
    "myles lewis-skelly": ("1423711", "49"),
    "kepa arrizabalaga": ("232422", "13"),
    "noni madueke": ("966547", "20"),
    "christian norgaard": ("135256", "16"),
    "cristhian mosquera": ("1144630", "3"),
    "piero hincapie": ("1002837", "5"),
    "max dowman": ("1917626", "56"),
    # Manchester Utd
    "senne lammens": ("964753", "31"),
    "diogo dalot": ("843200", "2"),
    "leny yoro": ("1153315", ""),
    "lisandro martinez": ("859999", "6"),
    "luke shaw": ("190839", ""),
    "casemiro": ("122951", "18"),
    "kobbie mainoo": ("1142175", "37"),
    "amad diallo": ("971037", "16"),
    "bruno fernandes": ("288205", "8"),
    "matheus cunha": ("886363", "10"),
    "benjamin sesko": ("986397", "30"),
    "matthijs de ligt": ("803031", ""),
    "noussair mazraoui": ("847030", "3"),
    "patrick dorgu": ("1397168", "13"),
}


def verify(sid: str) -> bool:
    try:
        r = tls_requests.get(f"https://img.sofascore.com/api/v1/player/{sid}/image",
                             headers=H, timeout=12)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
    except Exception:
        return False


def main() -> int:
    print("→ 이미지 CDN 검증 ...")
    ok = {}
    for key, (sid, num) in SEED.items():
        good = verify(sid)
        print(f"  {'OK ' if good else 'BAD'} {key:22} id={sid}")
        if good:
            ok[key] = (sid, num)
    print(f"검증 통과: {len(ok)}/{len(SEED)}")

    df = pd.read_csv(SLOTS)
    if "sofa_id" not in df.columns:
        df["sofa_id"] = ""
    if "number" not in df.columns:
        df["number"] = ""
    df["sofa_id"] = df["sofa_id"].astype("object")
    df["number"] = df["number"].astype("object")

    nk = df["player"].map(lambda s: unidecode(str(s)).lower().strip())
    filled = 0
    for i, key in nk.items():
        if key in ok:
            sid, num = ok[key]
            df.at[i, "sofa_id"] = sid
            if num:
                df.at[i, "number"] = num
            filled += 1
    df.to_csv(SLOTS, index=False, encoding="utf-8")
    print(f"[OK] {SLOTS.name} 시딩: {filled}행에 sofa_id 기록")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
