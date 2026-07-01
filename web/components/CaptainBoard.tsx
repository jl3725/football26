"use client";
import { useEffect, useState } from "react";
import { getCaptains, type Captain } from "@/lib/api";
import { tier, hexA } from "@/lib/ui";

export default function CaptainBoard({ team, accent }: { team: string; accent: string }) {
  const [caps, setCaps] = useState<Captain[]>([]);
  useEffect(() => { let a = true; getCaptains(team).then((d) => a && setCaps(d.captains)).catch(() => {}); return () => { a = false; }; }, [team]);
  if (caps.length === 0) return null;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>주장단 · Captaincy</h3>
      <div className="cap-board">
        {caps.map((c, i) => {
          const t = c.ovr ? tier(c.ovr) : null;
          return (
            <div className={`cap-card${c.is_main ? " main" : ""}`} key={i}
              style={c.is_main ? { borderColor: hexA(accent, 0.6), background: `linear-gradient(160deg, ${hexA(accent, 0.16)}, transparent)` } : undefined}>
              <div className="cap-band" style={{ background: c.is_main ? accent : "rgba(255,255,255,0.12)", color: c.is_main ? "#0b0f17" : "var(--muted)" }}>
                {c.is_main ? "Ⓒ 주장" : c.role}
              </div>
              {c.photo ? <img className="cap-photo" src={c.photo} alt="" /> : <span className="cap-photo ph" />}
              <div className="cap-name">{c.name}</div>
              <div className="cap-meta">
                {c.pos || "—"}
                {c.ovr != null && <span className="cap-ovr" style={{ color: t?.light }}> · {c.ovr}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
