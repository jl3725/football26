"use client";
// 전역 PlayerPeek — 화면 어디서든 선수 이름/토큰/칩 클릭 → 미니 프로필 팝오버.
// 데이터: getDatabase() 세션 캐시로 즉시 표시 → getPlayerDetail 로 G/A·계약·시장가 추이 보강.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  getDatabase, getPlayerDetail, fmtEur, activeLeague,
  type DbPlayer, type PlayerDetail,
} from "@/lib/api";
import { tier, roleClass } from "@/lib/ui";
import { Skel } from "./Skeleton";

export type PeekHint = Partial<Pick<DbPlayer,
  "photo" | "pos" | "age" | "ovr" | "value_eur" | "nationality" | "role" | "big_match" | "squad" | "league" | "logo">>;
export type PeekReq = { name: string; club?: string; league?: string; hint?: PeekHint };

type OpenFn = (e: React.MouseEvent | { clientX: number; clientY: number }, req: PeekReq) => void;
const Ctx = createContext<OpenFn>(() => {});

/** 어디서든: const peek = usePeek(); onClick={(e)=>peek(e,{name, club})} */
export const usePeek = () => useContext(Ctx);

function norm(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

function resolve(db: DbPlayer[], req: PeekReq): DbPlayer | null {
  const n = norm(req.name);
  const cands = db.filter((p) => norm(p.player) === n);
  if (cands.length === 0) {
    // 성(姓)만 일치 + 구단 일치 폴백 (라인업 토큰은 성만 노출되는 경우 대비)
    const last = n.split(" ").pop() || n;
    const loose = db.filter((p) => norm(p.player).endsWith(last) && req.club && norm(p.squad) === norm(req.club));
    return loose.length === 1 ? loose[0] : null;
  }
  if (cands.length === 1) return cands[0];
  if (req.club) {
    const byClub = cands.find((p) => norm(p.squad) === norm(req.club!));
    if (byClub) return byClub;
  }
  if (req.league) {
    const byLg = cands.find((p) => p.league === req.league);
    if (byLg) return byLg;
  }
  return cands[0];
}

const PEEK_W = 316;
const PEEK_H = 350; // 위/아래 배치 판단용 추정치

export function PeekProvider({ children, onOpenPlayer, onOpenTeam }: {
  children: React.ReactNode;
  onOpenPlayer?: (club: string, league: string, player: string) => void;
  onOpenTeam?: (club: string, league: string) => void;
}) {
  const [req, setReq] = useState<PeekReq | null>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [base, setBase] = useState<DbPlayer | null>(null);
  const [detail, setDetail] = useState<PlayerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const seq = useRef(0);

  const open: OpenFn = useCallback((e, r) => {
    const t = (e as React.MouseEvent).currentTarget as HTMLElement | undefined;
    const rect = t?.getBoundingClientRect?.();
    const ax = rect ? rect.left + rect.width / 2 : (e as { clientX: number }).clientX;
    const ay = rect ? rect.bottom : (e as { clientY: number }).clientY;
    const ayTop = rect ? rect.top : ay;
    const vw = window.innerWidth, vh = window.innerHeight;
    const x = Math.min(Math.max(8, ax - PEEK_W / 2), vw - PEEK_W - 8);
    const below = ay + 8 + PEEK_H <= vh;
    const y = below ? ay + 8 : Math.max(8, ayTop - PEEK_H - 8);
    setPos({ x, y });
    setReq(r);
  }, []);

  const close = useCallback(() => { setReq(null); setBase(null); setDetail(null); }, []);

  useEffect(() => {
    if (!req) return;
    const my = ++seq.current;
    setBase(null); setDetail(null); setDetailLoading(true);
    getDatabase()
      .then((db) => {
        if (seq.current !== my) return;
        const hit = resolve(db.players, req);
        setBase(hit);
        const club = hit?.squad ?? req.club;
        const lg = hit?.league ?? req.league ?? activeLeague();
        const pname = hit?.player ?? req.name;
        if (!club) { setDetailLoading(false); return; }
        getPlayerDetail(club, pname, lg)
          .then((d) => { if (seq.current === my) { setDetail(d); setDetailLoading(false); } })
          .catch(() => { if (seq.current === my) setDetailLoading(false); });
      })
      .catch(() => { if (seq.current === my) setDetailLoading(false); });
  }, [req]);

  useEffect(() => {
    if (!req) return;
    const onKey = (ev: KeyboardEvent) => { if (ev.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [req, close]);

  const h = req?.hint;
  const name = base?.player ?? req?.name ?? "";
  const photo = base?.photo || h?.photo || "";
  const ovr = base?.ovr ?? h?.ovr ?? detail?.ovr ?? null;
  const posTxt = base?.pos || h?.pos || detail?.pos || "";
  const age = base?.age ?? h?.age ?? detail?.age ?? null;
  const nat = base?.nationality || h?.nationality || detail?.nationality || "";
  const val = base?.value_eur ?? h?.value_eur ?? detail?.value_eur ?? 0;
  const role = base?.role || h?.role || "";
  const bigMatch = base?.big_match ?? h?.big_match ?? false;
  const club = base?.squad ?? req?.club ?? "";
  const clubLogo = base?.logo || h?.logo || "";
  const league = base?.league ?? req?.league ?? "";
  const tc = ovr != null ? tier(ovr) : tier(70);
  const vh = detail?.value_history ?? [];
  const spark = vh.length >= 2 ? vh : null;

  return (
    <Ctx.Provider value={open}>
      {children}
      {req && (
        <>
          <div className="peek-backdrop" onClick={close} />
          <div className="peek" style={{ left: pos.x, top: pos.y }} role="dialog" aria-label={name}>
            <div className="peek-band" style={{ background: `linear-gradient(90deg, ${tc.deep}, ${tc.light})` }} />
            <div className="peek-head">
              {photo
                ? <img className="peek-photo" src={photo} alt="" style={{ borderColor: tc.deep }} />
                : <span className="peek-photo-fallback" style={{ borderColor: tc.deep }}>{name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase()}</span>}
              <div className="peek-id">
                <div className="peek-name" title={name}>{name}</div>
                <div className="peek-sub">
                  {clubLogo && <img src={clubLogo} alt="" />}
                  {club && <span>{club}</span>}
                  {posTxt && <span>· {posTxt}</span>}
                  {age != null && <span>· {age}세</span>}
                  {nat && <span>· {nat}</span>}
                </div>
                <div className="peek-sub" style={{ marginTop: 4 }}>
                  <b style={{ color: "#dfe6f2", fontSize: 12 }}>{fmtEur(val)}</b>
                  {detail?.contract_until && <span>· 계약 ~{detail.contract_until}</span>}
                </div>
              </div>
              <div className="peek-ovr">
                {ovr != null
                  ? <b style={{ color: tc.light }}>{ovr}</b>
                  : <Skel w={34} h={30} style={{ margin: "0 auto" }} />}
                <span>{tc.name}</span>
              </div>
            </div>

            {(role || bigMatch) && (
              <div className="peek-tags">
                {role && <span className={`role-tag ${roleClass(role)}`}>{role}</span>}
                {bigMatch && <span className="role-bm">⚡ 빅매치 검증</span>}
              </div>
            )}

            {base || detail ? (
              <div className="peek-stats">
                <div className="peek-stat">
                  {detail ? <b>{detail.minutes.toLocaleString()}</b> : detailLoading ? <Skel w={30} h={18} style={{ margin: "0 auto 2px" }} /> : <b>—</b>}
                  <span>출전(분)</span>
                </div>
                <div className="peek-stat">
                  {detail ? <b>{detail.goals}</b> : detailLoading ? <Skel w={20} h={18} style={{ margin: "0 auto 2px" }} /> : <b>—</b>}
                  <span>득점</span>
                </div>
                <div className="peek-stat">
                  {detail ? <b>{detail.assists}</b> : detailLoading ? <Skel w={20} h={18} style={{ margin: "0 auto 2px" }} /> : <b>—</b>}
                  <span>도움</span>
                </div>
                <div className="peek-stat">
                  {detail ? <b>{detail.ss_rating ? detail.ss_rating.toFixed(2) : "—"}</b> : detailLoading ? <Skel w={30} h={18} style={{ margin: "0 auto 2px" }} /> : <b>—</b>}
                  <span>평점</span>
                </div>
              </div>
            ) : detailLoading ? (
              <div className="peek-loadrow"><Skel h={44} r={10} /></div>
            ) : (
              <div className="peek-empty">이 선수의 상세 데이터가 아직 수집되지 않았습니다.</div>
            )}

            {spark && (
              <div className="peek-spark">
                <div className="peek-spark-cap"><span>시장가치 추이</span><span>{fmtEur(spark[spark.length - 1].value_eur)}</span></div>
                <svg viewBox="0 0 100 26" width="100%" height="26" preserveAspectRatio="none">
                  {(() => {
                    const vs = spark.map((p) => p.value_eur);
                    const mx = Math.max(...vs), mn = Math.min(...vs);
                    const pts = vs.map((v, i) => {
                      const x = (i / (vs.length - 1)) * 100;
                      const y = mx === mn ? 13 : 23 - ((v - mn) / (mx - mn)) * 20;
                      return `${x},${y}`;
                    }).join(" ");
                    const up = vs[vs.length - 1] >= vs[0];
                    return <polyline points={pts} fill="none" stroke={up ? "#4fc27f" : "#e07070"} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />;
                  })()}
                </svg>
              </div>
            )}

            <div className="peek-actions">
              {club && onOpenPlayer && (
                <button className="primary" style={{ background: `linear-gradient(120deg, ${tc.light}, ${tc.deep})` }}
                  onClick={() => { onOpenPlayer(club, league || activeLeague(), name); close(); }}>
                  프로필 열기
                </button>
              )}
              {club && onOpenTeam && (
                <button onClick={() => { onOpenTeam(club, league || activeLeague()); close(); }}>구단으로</button>
              )}
              <button onClick={close}>닫기</button>
            </div>
          </div>
        </>
      )}
    </Ctx.Provider>
  );
}
