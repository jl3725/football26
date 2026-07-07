// 섹션 헤더 accent 바 마커 — 이모지 대신 프로페셔널한 시각 큐.
export default function Bar({ c }: { c: string }) {
  return <span style={{ display: "inline-block", width: 3, height: 12, borderRadius: 2, background: c, marginRight: 8, verticalAlign: "-1px" }} />;
}
