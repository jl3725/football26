"""뉴스 종류 규칙 분류 — 평가 표본(data/eval/news_kind_eval.csv, Gemini 정답) 기준선 + 다른 뜻 표현 단위 검사.

2026-10-23 '뉴스 이적 분류 잡음 정리': 이적 정밀도 0.78 → 0.92, 재현율 0.86 → 0.93, 전체 정확도 0.59 → 0.73.
낱말을 고칠 때 이 기준선 아래로 떨어지면 실패한다(표본을 다시 만들면 scripts/build_news_eval.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import news_classify as nc  # noqa: E402

EVAL = ROOT / "data" / "eval" / "news_kind_eval.csv"


@pytest.fixture(scope="module")
def ev() -> pd.DataFrame:
    if not EVAL.exists():
        pytest.skip("평가 표본 없음")
    e = pd.read_csv(EVAL)
    e["rule"] = [nc.rule_kind(h, d) for h, d in zip(e["headline"].astype(str), e["descr"].fillna("").astype(str))]
    return e


def test_transfer_precision_recall(ev):
    tp = ((ev.rule == "transfer") & (ev.ai_kind == "transfer")).sum()
    fp = ((ev.rule == "transfer") & (ev.ai_kind != "transfer")).sum()
    fn = ((ev.rule != "transfer") & (ev.ai_kind == "transfer")).sum()
    assert tp / max(1, tp + fp) >= 0.88
    assert tp / max(1, tp + fn) >= 0.88


def test_overall_accuracy(ev):
    assert (ev.rule == ev.ai_kind).mean() >= 0.70


@pytest.mark.parametrize("headline", [
    "Arsenal bid to follow up derby win with victory at Fulham",       # bid to = 시도
    "How Slot deals with the pressure at Anfield",                      # deal with = 대처
    "Benfica vence no prolongamento e segue na Taça",                   # 연장전
    "Inter, fiducia rinnovata a Chivu dopo il pareggio",                 # 신뢰
    "Former striker joins the cast of new football drama",              # 출연
    "Club secures housing loan for new training centre",                # 대출
])
def test_not_transfer_idioms(headline):
    assert nc.rule_kind(headline, "") != "transfer"


@pytest.mark.parametrize("headline", [
    "Galatasaray, Osimhen için bonservis ödedi",
    "Fenerbahçe yıldız ismi kiralık olarak kadrosuna kattı",
    "Brøndby-profil skifter til Bundesliga-klub",
    "Chelsea complete signing of Brazilian winger",
    "Barcelona agree fee for Bundesliga defender",
])
def test_transfer_words(headline):
    assert nc.rule_kind(headline, "") == "transfer"


def test_weak_word_only_in_headline():
    # 요약의 애매한 낱말('llegada'·'contract')만으로는 이적이 아니다 — 경기 기사 요약에 흔하다
    assert nc.rule_kind("Real Betis 2-1 Sevilla: the derby report", "La llegada del equipo al estadio y el contrato del técnico") != "transfer"
    # 제목의 애매한 낱말은 이적
    assert nc.rule_kind("Liverpool target Dutch midfielder", "") == "transfer"
