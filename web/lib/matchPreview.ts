"use client";
import { createContext, useContext } from "react";
import type { Fixture } from "./api";

// 어느 경기 카드에서든 매치 프리뷰 서랍 열기 — 공급자는 components/MatchPreview.tsx
export const MatchPreviewCtx = createContext<((m: Fixture) => void) | null>(null);
export const useMatchPreview = () => useContext(MatchPreviewCtx);
