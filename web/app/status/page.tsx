import type { Metadata } from "next";
import DataStatus from "@/components/DataStatus";

export const metadata: Metadata = { title: "DATA STATUS — SCOUT.AI" };

// 데이터 상태 화면 — 수집 에이전트별 마지막 성공·지연·최근 실패(/api/ops/status). 상태바 DATA 칩에서 들어온다.
export default function StatusPage() {
  return <DataStatus />;
}
