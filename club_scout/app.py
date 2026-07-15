# -*- coding: utf-8 -*-
"""Club Scout — 一口出資の相対選定（馬券予想とは非連携）。"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from scorer import load_ranks, load_rules, rank_candidates, reload_ranks, score_candidate
from decision import decide, pocket_card_text
from store import append_kinjou, load_candidates, upsert_candidate

CLUB = Path(__file__).resolve().parent
AXIS_PATH = CLUB / "data" / "axis_summary.json"
RANKS_PATH = CLUB / "data" / "family_trainer_ranks.json"

st.set_page_config(page_title="Club Scout（広尾）", layout="wide")
st.title("Club Scout — 広尾一口選定")
st.caption(
    "軸: mykeibadb 馬主「広尾レース」(553800) ／ 募集: hirootc.jp ／ "
    "近況: 丸ごとコピペ ／ 予想パイプライン非連携"
)

rules = load_rules()
data = load_candidates()
cands = data.get("candidates") or []

with st.sidebar:
    st.subheader("プール／予算")
    pools = sorted({str(c.get("pool") or "default") for c in cands}) or ["default"]
    pool = st.selectbox("相対比較プール", pools)
    only_ok = st.checkbox("満口など見送り除外", value=True)
    st.markdown("---")
    st.subheader("軸サマリ（DB）")
    if AXIS_PATH.exists():
        axis = json.loads(AXIS_PATH.read_text(encoding="utf-8"))
        owner = axis.get("owner") or {}
        st.write(
            f"{owner.get('banushi_hojinkaku_nashi')} / code={axis.get('banushi_code')}"
        )
        st.write(
            f"登録馬 {axis.get('kyosoba_count')} 頭（現役相当 {axis.get('kyosoba_active')}）"
        )
        stats = axis.get("master_cum_stats") or {}
        st.write(f"累計 勝 {stats.get('wins')} / 走 {stats.get('starts')}")
    else:
        st.info("data/axis_summary.json がありません。db_hiroo_axis.py を実行してください。")
    if st.button("ルール／ランク再読込"):
        reload_ranks()
        st.cache_data.clear()
        st.rerun()

tab_rank, tab_families, tab_decide = st.tabs(
    ["相対ランキング", "広尾牝系・クロス統計", "カタログ即断"]
)

with tab_decide:
    st.subheader("買う / 様子見 / 見送り")
    st.caption("カタログ（blood）の項目だけで判定。母名を入れると母母をDB解決します。")
    with st.expander("ポケットカード", expanded=False):
        st.text(pocket_card_text())
    d1, d2 = st.columns(2)
    with d1:
        d_name = st.text_input("募集名", "ストームハート'25", key="dec_name")
        d_dam = st.text_input("母名（カタログ）", "ストームハート", key="dec_dam")
        d_trainer = st.text_input("予定調教師", "蛯名正義", key="dec_tr")
        d_sire = st.text_input("父", "コントレイル", key="dec_sire")
    with d2:
        d_price = st.number_input("一口価格（万円）", 0.0, 10.0, 1.8, 0.1, key="dec_price")
        d_status = st.selectbox("募集状況", ["募集中", "残口わずか", "満口"], key="dec_st")
        d_sig = st.text_input("看板牝系（任意・母母母など）", "", key="dec_sig")
        d_kinjou = st.text_area("近況コピペ（任意）", "", height=120, key="dec_kj")
    if st.button("判定する", type="primary", key="dec_btn"):
        out = decide(
            {
                "name": d_name,
                "dam": d_dam,
                "trainer": d_trainer,
                "sire": d_sire,
                "price_man_yen": float(d_price),
                "status": d_status,
                "signature_line": d_sig.strip(),
                "kinjou_latest": d_kinjou,
            }
        )
        color = {"GO": "green", "HOLD": "orange", "PASS": "red"}.get(out["verdict"], "gray")
        st.markdown(
            f"### :{color}[{out['verdict']}] {out['label']}　**{out['points']} pt**"
        )
        st.write(out["meaning"])
        if out.get("resolved"):
            st.info(f"母→母母: {out['resolved']}")
        st.dataframe(out.get("detail") or [], use_container_width=True, hide_index=True)
        for h in out.get("combo_hints") or []:
            st.write(f"- {h}")

with tab_families:
    ranks = load_ranks()
    if not ranks:
        st.warning("family_trainer_ranks.json がありません。build_family_ranks.py を実行してください。")
    else:
        st.caption(ranks.get("definition") or {})
        st.subheader("広尾独自牝系ランク")
        uniq = ranks.get("hiroo_unique_families") or []
        st.dataframe(
            [
                {
                    "広尾牝系ランク": u.get("hiroo_family_rank"),
                    "広尾牝系": u.get("hiroo_family_grade"),
                    "母母": u.get("family_name"),
                    "全体グレード": u.get("grade"),
                    "広尾比率": u.get("hiroo_share"),
                    "平滑勝率": u.get("win_rate_sm"),
                    "頭数": u.get("n_horses"),
                    "広尾頭数": u.get("hiroo_horses"),
                }
                for u in uniq[:30]
            ],
            use_container_width=True,
            hide_index=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("広尾×調教師")
            st.dataframe(
                [
                    {
                        "順位": t.get("rank"),
                        "G": t.get("grade"),
                        "調教師": t.get("trainer"),
                        "平滑勝率": t.get("win_rate_sm"),
                        "頭数": t.get("n_horses"),
                    }
                    for t in (ranks.get("trainer_hiroo") or [])
                    if t.get("grade") != "U"
                ][:25],
                use_container_width=True,
                hide_index=True,
            )
        with c2:
            st.subheader("広尾×調教師×牝系クロス")
            st.dataframe(
                [
                    {
                        "順位": x.get("rank"),
                        "G": x.get("grade"),
                        "調教師": x.get("trainer"),
                        "母母": x.get("family_name"),
                        "平滑勝率": x.get("win_rate_sm"),
                        "頭数": x.get("n_horses"),
                    }
                    for x in (ranks.get("cross_hiroo") or [])
                    if x.get("grade") != "U"
                ][:25],
                use_container_width=True,
                hide_index=True,
            )

with tab_rank:
    ranked = rank_candidates(cands, rules, pool=pool, only_eligible=only_ok)
    st.subheader(f"相対ランキング（{pool}）")
    if not ranked:
        st.warning("候補がありません。")
    else:
        top = ranked[0]
        fm = top.get("family_meta") or {}
        extra = ""
        if fm.get("hiroo_unique"):
            extra = (
                f"／広尾牝系 {fm.get('hiroo_family_grade')} "
                f"(#{fm.get('hiroo_family_rank')})"
            )
        st.success(
            f"本命候補: **{top.get('name')}**  {top.get('total')} / {top.get('max_score')}　"
            f"推奨 {top.get('recommend_units')}{extra}"
        )
        rows = []
        for r in ranked:
            bd = r.get("breakdown") or {}
            fm = r.get("family_meta") or {}
            rows.append(
                {
                    "順位": r.get("rank"),
                    "ラベル": r.get("label"),
                    "馬名": r.get("name"),
                    "総合": r.get("total"),
                    "牝系": bd.get("family"),
                    "全体G": fm.get("overall_grade"),
                    "広尾牝系": fm.get("hiroo_family_grade"),
                    "クロス": bd.get("cross"),
                    "厩舎": bd.get("trainer"),
                    "父": bd.get("sire"),
                    "近況": bd.get("body_kinjou"),
                    "価格": bd.get("price"),
                    "推奨口数": r.get("recommend_units"),
                    "状態": r.get("status"),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.markdown("---")
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("近況コピペ → 再スコア")
            ids = [f"{c.get('id')} | {c.get('name')}" for c in cands]
            if ids:
                pick = st.selectbox("候補", ids, key="kinjou_pick")
                cid = pick.split("|", 1)[0].strip()
                paste = st.text_area(
                    "近況を丸ごと貼り付け", height=220, placeholder="クラブ近況文をそのまま…"
                )
                note = st.text_input("メモ（任意）", "")
                if st.button("保存して再スコア", type="primary"):
                    if not paste.strip():
                        st.error("貼り付け内容が空です。")
                    else:
                        append_kinjou(cid, paste.strip(), note=note)
                        st.success("保存しました。ランキングを更新します。")
                        st.rerun()
                target = next((c for c in cands if str(c.get("id")) == cid), None)
                if target:
                    st.json(score_candidate(target, rules))
            else:
                st.info("候補がありません。")

        with col_b:
            st.subheader("募集馬の追加／更新（WEB情報）")
            with st.form("cand_form"):
                new_id = st.text_input("募集コード", "2025xx-1")
                new_name = st.text_input("募集名", "")
                new_trainer = st.text_input("入厩予定・調教師", "")
                new_sire = st.text_input("父", "")
                new_family_mare = st.text_input(
                    "母母名（牝系キー・DB照合）",
                    help="例: Dollar Bird / ハイアーラヴ。空なら手ラベルを使用",
                )
                new_price = st.number_input("一口価格（万円）", min_value=0.0, value=1.5, step=0.1)
                new_family = st.selectbox("牝系ラベル（フォールバック）", ["S", "A", "B", "C", "unknown"])
                new_status = st.selectbox("募集状況", ["募集中", "残口わずか", "満口"])
                new_pool = st.text_input("プール名", pool)
                new_area = st.text_input("美浦/栗東", "")
                submitted = st.form_submit_button("登録")
                if submitted:
                    upsert_candidate(
                        {
                            "id": new_id.strip(),
                            "name": new_name.strip(),
                            "trainer": new_trainer.strip(),
                            "sire": new_sire.strip(),
                            "family_mare": new_family_mare.strip(),
                            "price_man_yen": float(new_price),
                            "family_label": new_family,
                            "status": new_status,
                            "pool": new_pool.strip() or "default",
                            "stable_area": new_area.strip(),
                            "kinjou_latest": "",
                            "kinjou_history": [],
                        }
                    )
                    st.success("登録しました。")
                    st.rerun()

st.markdown("---")
st.caption(
    "出典カタログ: https://www.hirootc.jp/sellhorses/　／ "
    "牝系キー=母母(ketto6)　／ ランク再生成: python build_family_ranks.py"
)
