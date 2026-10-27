// SCOUT TAKE — 선수 화면 맨 위 한줄평(평가 한 줄 + 근거 한 줄) + 같은 포지션 백분위 강점·약점 칩.
// 2026-10-27 사용자: 주 사용자는 팬, 느낌은 고급 스카우트 리포트 — '쿠냐 87 왜?' 같은 질문에 화면이 바로 답하게.
// 문장은 AI(무료 Gemini)가 화면 숫자만으로 쓰고 검증을 넘은 것만(src/scout_take.py). 문장이 없으면 칩만 — 규칙 문장으로 채우지 않는다.
import Info from "./Info";
import type { ScoutTake as Take } from "@/lib/api";

export default function ScoutTake({ t }: { t?: Take | null }) {
  if (!t) return null;
  // 역할·리그 순위 배지는 바로 아래('이번 시즌 역할'·배지 줄)에 있어 여기선 빼고 같은 포지션 백분위만
  const strengths = (t.strengths ?? []).filter((s) => !/리그 \d+위$/.test(s));
  const chips = strengths.length + (t.weaks?.length ?? 0) > 0;
  if (!t.l1 && !chips) return null;
  const day = t.at ? t.at.slice(0, 10) : "";
  return (
    <section className="stk" aria-labelledby="stk-h">
      <div className="stk-h">
        <h3 id="stk-h">SCOUT TAKE</h3>
        <span>스카우트 한줄평</span>
        <Info wide label="한줄평 기준">
          <p><b>한줄평</b> — 이 화면의 숫자(OVR·폼·평점·골·도움·순위·역할)만 보고 AI 가 쓴 문장. 숫자·이름이 화면 값과 맞는 것만 싣고, 매일 바뀐 선수만 다시 씁니다{day ? ` (쓴 날 ${day})` : ""}.</p>
          <p><b>강점·약점</b> — 같은 포지션 안 백분위 상·하위 30%. 출전이 적으면 비워 둡니다.</p>
        </Info>
      </div>
      {t.l1 && <p className="stk-l1">{t.l1}</p>}
      {t.l2 && <p className="stk-l2">{t.l2}</p>}
      {chips && (
        <div className="stk-chips">
          {strengths.length > 0 && (
            <div className="stk-g"><span className="stk-k">강점</span>{strengths.map((s) => <span className="stk-c good" key={s}>{s}</span>)}</div>
          )}
          {(t.weaks?.length ?? 0) > 0 && (
            <div className="stk-g"><span className="stk-k">약점</span>{t.weaks!.map((s) => <span className="stk-c weak" key={s}>{s}</span>)}</div>
          )}
        </div>
      )}
      {t.thin && <p className="stk-note">출전이 적어 강점·약점은 아직</p>}
    </section>
  );
}
