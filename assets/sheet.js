/* Club Scout sheet renderers — reads window.CLUB_DATA */
(function () {
  const D = () => window.CLUB_DATA;
  const gja = (g) => (D().meta.grade_ja[g] || D().meta.grade_ja.none || { short: g || "-" }).short;
  const badge = (g) => {
    if (!g) return '<span class="grade U">-</span>';
    const cls = ["S", "A", "B", "C", "U", "top", "mid", "low"].includes(g) ? g : "U";
    const label = D().meta.grade_ja[g]
      ? D().meta.grade_ja[g].ja
      : D().meta.sire_ja[g]
        ? D().meta.sire_ja[g].ja
        : g;
    return `<span class="grade ${cls}">${label}</span>`;
  };

  function bindFilter(inputId, rowsSelector) {
    const input = document.getElementById(inputId || "q");
    if (!input) return;
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      document.querySelectorAll(rowsSelector).forEach((row) => {
        const hay = (row.getAttribute("data-q") || row.textContent || "").toLowerCase();
        const ok = !q || hay.includes(q);
        row.style.display = ok ? "" : "none";
        row.classList.toggle("hit", ok && !!q);
      });
    });
  }

  const SheetApp = {
    renderToc() {
      const items = [
        ["01-tiers.html", "01 段階名称", "最上級/上級/標準… と 上位/中位/下位"],
        ["02-trainer.html", "02 厩舎グレード", "DB優先＋YAMLフォールバックの一覧"],
        ["03-sire.html", "03 父グレード", "父スコア→日本語段階"],
        ["04-family.html", "04 牝系グレード", "全体・広尾独自・看板候補"],
        ["05-cross.html", "05 クロス組み合わせ", "厩舎×牝系の等級表"],
        ["06-combo.html", "06 各コンボ表", "C1〜C5 の条件と傾き"],
        ["07-weight.html", "07 馬体重OK範囲", "正本420＋統合プロファイル"],
        ["08-points.html", "08 配点・即PASS", "見る順と加点テーブル"],
        ["../tool.html", "補完ツール", "検索・体重判定・点数試算"],
      ];
      document.getElementById("toc").innerHTML = items
        .map(
          ([href, title, desc]) =>
            `<a href="${href}"><strong>${title}</strong><span>${desc}</span></a>`
        )
        .join("");
    },

    renderTiers() {
      const gj = D().meta.grade_ja;
      const sj = D().meta.sire_ja;
      const def = D().meta.definition || {};
      document.getElementById("tiers").innerHTML = `
        <section class="card">
          <h2>共通等級（S〜U）</h2>
          <p class="note">定義: ${def.grade || "上位15%=S / 40%=A / 75%=B / 他=C（標本不足=U）"}</p>
          <table class="tbl">
            <thead><tr><th>記号</th><th>日本語</th><th>読み方</th></tr></thead>
            <tbody>
              ${["S", "A", "B", "C", "U"]
                .map(
                  (k) =>
                    `<tr><td>${badge(k)}</td><td>${gj[k].short}</td><td class="muted">${gj[k].hint}</td></tr>`
                )
                .join("")}
            </tbody>
          </table>
        </section>
        <section class="card">
          <h2>父の段階（top / mid / low）</h2>
          <table class="tbl">
            <thead><tr><th>記号</th><th>日本語</th><th>ルール</th></tr></thead>
            <tbody>
              ${["top", "mid", "low"]
                .map(
                  (k) =>
                    `<tr><td>${badge(k)}</td><td>${sj[k].short}</td><td class="muted">${sj[k].hint}</td></tr>`
                )
                .join("")}
            </tbody>
          </table>
        </section>
        <section class="card">
          <h2>広尾独自牝系の定義</h2>
          <p>${def.hiroo_unique || "広尾頭数≥3 かつ 広尾比率≥0.35"}</p>
          <p class="note">牝系キー: ${def.family_key || "ketto6（母母）"}</p>
        </section>`;
    },

    renderTrainers() {
      const pts = D().points_trainer;
      const rows = D().trainers
        .map((t) => {
          const db = t.db
            ? `DB:${t.db.grade || "-"}`
            : "DB:なし";
          const y = t.yaml ? `YAML:${t.yaml.grade}` : "YAML:なし";
          return `<tr class="row" data-q="${t.name}">
            <td><strong>${t.name}</strong><div class="note">${db} / ${y} / 採用=${t.effective_source}</div></td>
            <td>${badge(t.effective_grade)}<div class="note">${gja(t.effective_grade)}</div></td>
            <td class="num">${t.effective_score ?? "-"}</td>
            <td class="num">${t.n_horses ?? "-"}</td>
            <td class="num">${pts[t.effective_grade] ?? pts.none ?? 0}</td>
          </tr>`;
        })
        .join("");
      document.getElementById("trainers").innerHTML = `
        <section class="card">
          <h2>判定ポイント換算（checklist）</h2>
          <p>最上級+${pts.S} / 上級+${pts.A} / 標準+${pts.B} / 控えめ+${pts.C} / 不足 ${pts.U} / 未設定 ${pts.none}</p>
        </section>
        <section class="card">
          <h2>厩舎一覧（${D().trainers.length}）</h2>
          <table class="tbl">
            <thead><tr><th>厩舎</th><th>段階</th><th>スコア</th><th>頭数</th><th>加点</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </section>`;
      bindFilter("q", "#trainers tr.row");
    },

    renderSires() {
      const pts = D().points_sire;
      const rows = D()
        .sires.map(
          (s) => `<tr>
            <td><strong>${s.name}</strong></td>
            <td>${badge(s.tier)} <span class="muted">${s.tier_ja}</span></td>
            <td class="num">${s.score}</td>
            <td class="num">+${pts[s.tier] ?? 0}</td>
          </tr>`
        )
        .join("");
      document.getElementById("sires").innerHTML = `
        <section class="card">
          <h2>変換ルール</h2>
          <ul class="list">
            <li>父スコア ≥ 3.5 → <strong>上位（top）</strong> → 加点 +${pts.top}</li>
            <li>父スコア ≥ 2.8 → <strong>中位（mid）</strong> → 加点 +${pts.mid}</li>
            <li>それ未満 / 未登録寄り → <strong>下位（low）</strong> → 加点 +${pts.low}（default=${D().sire_default}）</li>
          </ul>
        </section>
        <section class="card">
          <h2>父一覧（登録分）</h2>
          <table class="tbl">
            <thead><tr><th>父</th><th>段階</th><th>ルール値</th><th>加点</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <p class="note">未登録の父は default=${D().sire_default}（中位未満＝下位扱い）。</p>
        </section>`;
    },

    renderFamilies() {
      const po = D().points_family_overall;
      const pu = D().points_hiroo_unique;
      const rows = D()
        .families.map((f) => {
          const uniq = f.hiroo_unique
            ? `${badge(f.hiroo_family_grade)} ${gja(f.hiroo_family_grade)}`
            : '<span class="muted">独自対象外</span>';
          return `<tr class="row" data-q="${f.name}">
            <td><strong>${f.name}</strong>
              <div class="note">全体順位 ${f.overall_rank ?? "-"} / 頭数 ${f.n_horses ?? "-"}</div>
            </td>
            <td>${badge(f.overall_grade)}<div class="note">${gja(f.overall_grade)} / 加点+${po[f.overall_grade] ?? 0}</div></td>
            <td>${uniq}<div class="note">${f.hiroo_unique ? "独自加点+" + (pu[f.hiroo_family_grade] ?? 0) : ""}</div></td>
          </tr>`;
        })
        .join("");
      const aliases = (D().family_aliases || [])
        .map(
          (a) =>
            `<li><strong>${a.alias}</strong> — ${a.note}${
              a.suggest_signature ? ` / 看板候補: ${a.suggest_signature}` : ""
            }${a.manual_unique ? ` / 運用上の独自: ${gja(a.manual_unique)}` : ""}</li>`
        )
        .join("");
      document.getElementById("families").innerHTML = `
        <section class="card">
          <h2>見方</h2>
          <ul class="list">
            <li><strong>全体等級</strong>: 中央ベースの牝系の強さ（加点 family_overall）</li>
            <li><strong>広尾独自</strong>: 広尾比率が高い血統。独自等級があるとき追加加点</li>
            <li>カタログでは母名→母母を解決して照合する</li>
          </ul>
        </section>
        <section class="card">
          <h2>ランクJSON未収録だが運用上重要な名前</h2>
          <ul class="list">${aliases}</ul>
          <p class="note">これらは正本JSONにキーが無いため、ツールでは手動等級または看板参照で補完します。</p>
        </section>
        <section class="card">
          <h2>牝系列表（${D().families.length}）</h2>
          <table class="tbl">
            <thead><tr><th>母母名</th><th>全体</th><th>広尾独自</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </section>`;
      bindFilter("q", "#families tr.row");
    },

    renderCrosses() {
      const pc = D().points_cross;
      const rows = D()
        .crosses.map((c) => {
          return `<tr class="row" data-q="${c.trainer} ${c.family}">
            <td><strong>${c.trainer}</strong><div class="note">× ${c.family}</div></td>
            <td>${badge(c.grade)}<div class="note">${gja(c.grade)}</div></td>
            <td class="num">${c.score ?? "-"}</td>
            <td class="num">${c.n_horses ?? "-"}</td>
            <td class="num">+${pc[c.grade] ?? 0}</td>
          </tr>`;
        })
        .join("");
      document.getElementById("crosses").innerHTML = `
        <section class="card">
          <h2>クロスとは</h2>
          <p>同じ牝系を、特定厩舎が広尾で結果を出している組合せ。データがある組だけ等級化。</p>
          <p class="note">checklist加点: 最上級+${pc.S} / 上級+${pc.A} / 標準+${pc.B} / 控えめ+${pc.C}</p>
        </section>
        <section class="card">
          <h2>クロス一覧（${D().crosses.length}組）</h2>
          <table class="tbl">
            <thead><tr><th>厩舎 × 牝系</th><th>段階</th><th>スコア</th><th>頭数</th><th>加点</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <p class="note">表に無い組合せはクロスなし（加点0）。片方の強さでGOすることはある（コンボC1/C3）。</p>
        </section>`;
      bindFilter("q", "#crosses tr.row");
    },

    renderCombos() {
      const mapHint = { GO: "badge-go", HOLD: "badge-hold", PASS: "badge-pass" };
      const lists = D().combo_lists || {};
      const rules = D().meta.combo_rules || [];
      const blocks = rules
        .map((c) => {
          const cls = mapHint[c.verdict_hint] || "";
          const L = lists[c.id] || {};
          let body = "";
          if (c.id === "C1") {
            body = `
              <h3>独自牝系側（${(L.unique_families || []).length}）</h3>
              <ul class="list">${(L.unique_families || [])
                .map((x) => `<li>${x.name} — ${badge(x.grade)} ${gja(x.grade)}</li>`)
                .join("")}</ul>
              <h3>厩舎側（${(L.trainers || []).length}）</h3>
              <ul class="list">${(L.trainers || [])
                .map((x) => `<li>${x.name} — ${badge(x.grade)} ${gja(x.grade)}</li>`)
                .join("")}</ul>
              <p class="note">上×下がそろったとき <strong>C1点灯</strong>。</p>`;
          } else if (c.id === "C2") {
            body = `
              <h3>点灯するクロス組（データ上のS/A）</h3>
              <table class="tbl"><thead><tr><th>厩舎</th><th>牝系</th><th>段階</th></tr></thead><tbody>
              ${(L.pairs || [])
                .map(
                  (p) =>
                    `<tr><td>${p.trainer}</td><td>${p.family}</td><td>${badge(p.grade)} ${gja(p.grade)}</td></tr>`
                )
                .join("")}
              </tbody></table>
              <p class="note">この表に無い組合せはクロスなし（C2は点灯しない）。</p>`;
          } else if (c.id === "C3") {
            body = `
              <h3>全体牝系S/A</h3>
              <ul class="list">${(L.families || [])
                .map((x) => `<li>${x.name} — ${badge(x.grade)}</li>`)
                .join("")}</ul>
              <h3>父・上位</h3>
              <ul class="list">${(L.sires || [])
                .map((x) => `<li>${x.name} — ${x.tier_ja}</li>`)
                .join("")}</ul>
              <p class="note">＋ 一口 ≦ 2.0 万円 で <strong>C3点灯</strong>。</p>`;
          } else if (c.id === "C4") {
            body = `
              <h3>看板候補（深い層）</h3>
              <ul class="list">${(L.signature_candidates || [])
                .map((x) => `<li>${x.name} — ${badge(x.grade)}</li>`)
                .join("")}</ul>
              <p class="note">看板がS/Aで、全体牝系がB/Cのとき点灯。</p>`;
          } else if (c.id === "C5") {
            body = `<p>一口 ≧ 2.5 かつ 独自もクロスも S/A でない → <strong>C5点灯（PASS寄り）</strong></p>`;
          }
          return `<article class="card">
            <h2>${c.id} ${c.name}</h2>
            <p><span class="${cls}">傾き: ${c.verdict_hint}</span></p>
            <p><strong>条件式</strong><br><code style="font-size:.78rem;color:var(--muted)">${c.when}</code></p>
            ${L.note ? `<p class="note">${L.note}</p>` : ""}
            ${c.note ? `<p class="note">${c.note}</p>` : ""}
            ${body}
          </article>`;
        })
        .join("");
      document.getElementById("combos").innerHTML =
        `<section class="card">
          <h2>コンボの見方</h2>
          <ul class="list">
            <li>下の各カードが「どのリストの組合せで点灯するか」です。</li>
            <li>C1〜C3点灯 → GO寄り / C5点灯 → PASS寄り。最終は合計点と即PASS優先。</li>
            <li>補完ツールの「コンボ判定」でも、入力から点灯確認できます。</li>
          </ul>
        </section>` + blocks;
    },

    renderWeight() {
      const w = D().weight;
      const profiles = w.profiles
        .map((p) => {
          const tRows = (p.trainers || [])
            .map((n) => {
              const b = (w.trainer_bands || []).find((x) => x.name === n);
              return `<tr><td>${n}</td><td>${b ? badge(b.grade) : "-"}</td><td class="num">${p.ok_min}–${p.ok_max}</td></tr>`;
            })
            .join("");
          const sRows = (p.sires || [])
            .map((n) => {
              const b = (w.sire_bands || []).find((x) => x.name === n);
              return `<tr><td>${n}</td><td>${b ? badge(b.tier) : "-"}</td><td class="num">${p.ok_min}–${p.ok_max}</td></tr>`;
            })
            .join("");
          return `<article class="card">
            <h2>${p.title}</h2>
            <p><strong>OK目安</strong> ${p.ok_min}〜${p.ok_max} kg</p>
            <p class="note">${p.note}</p>
            <h3>厩舎（この帯に割当・全件）</h3>
            ${
              p.trainers.length
                ? `<table class="tbl"><thead><tr><th>厩舎</th><th>等級</th><th>帯</th></tr></thead><tbody>${tRows}</tbody></table>`
                : "<p class=\"muted\">なし</p>"
            }
            <h3>父（この帯に割当・登録全件）</h3>
            ${
              p.sires.length
                ? `<table class="tbl"><thead><tr><th>父</th><th>段階</th><th>帯</th></tr></thead><tbody>${sRows}</tbody></table>`
                : "<p class=\"muted\">登録父はこの帯に未割当（標準帯へ）</p>"
            }
          </article>`;
        })
        .join("");
      const allT = (w.trainer_bands || [])
        .map(
          (b) =>
            `<tr class="row" data-q="${b.name}"><td>${b.name}</td><td>${badge(b.grade)}</td><td>${b.profile_title}</td><td class="num">${b.ok_min}–${b.ok_max}</td></tr>`
        )
        .join("");
      const allS = (w.sire_bands || [])
        .map(
          (b) =>
            `<tr class="row" data-q="${b.name}"><td>${b.name}</td><td>${badge(b.tier)}</td><td>${b.profile_title}</td><td class="num">${b.ok_min}–${b.ok_max}</td></tr>`
        )
        .join("");
      document.getElementById("weight").innerHTML = `
        <section class="card">
          <h2>正本ルール（採点に効く）</h2>
          <ul class="list">
            <li>軽量警戒線: <strong>${w.canonical.alert_kg} kg 以下</strong></li>
            <li>checklist: ${w.canonical.checklist_pts} 点</li>
            <li>相対scorer: ${w.canonical.scorer_delta}</li>
          </ul>
          <p class="note">${w.canonical.note}</p>
          <p class="note">${w.assignment_note || ""}</p>
        </section>
        <section class="card">
          <h2>統合ルール</h2>
          <ol class="list">${w.integration_rules.map((x) => `<li>${x}</li>`).join("")}</ol>
        </section>
        ${profiles}
        <section class="card">
          <h2>厩舎×体重帯 全一覧</h2>
          <div class="searchbox"><label class="field">絞り込み<input id="qw-t" placeholder="須貝" /></label></div>
          <table class="tbl"><thead><tr><th>厩舎</th><th>等級</th><th>プロファイル</th><th>OK帯</th></tr></thead><tbody id="w-t-body">${allT}</tbody></table>
        </section>
        <section class="card">
          <h2>父×体重帯 全一覧</h2>
          <div class="searchbox"><label class="field">絞り込み<input id="qw-s" placeholder="カナロア" /></label></div>
          <table class="tbl"><thead><tr><th>父</th><th>段階</th><th>プロファイル</th><th>OK帯</th></tr></thead><tbody id="w-s-body">${allS}</tbody></table>
        </section>`;
      const bind = (id, sel) => {
        const input = document.getElementById(id);
        if (!input) return;
        input.addEventListener("input", () => {
          const q = input.value.trim().toLowerCase();
          document.querySelectorAll(sel).forEach((row) => {
            const hay = (row.getAttribute("data-q") || "").toLowerCase();
            row.style.display = !q || hay.includes(q) ? "" : "none";
          });
        });
      };
      bind("qw-t", "#w-t-body tr.row");
      bind("qw-s", "#w-s-body tr.row");
    },

    renderPoints() {
      const m = D().meta;
      const v = m.verdict;
      const steps = (m.instant_checklist || [])
        .map(
          (s) => `<li><strong>${s.step}. ${s.title}</strong><br>
            ${s.go ? `<span class="badge-go">GO</span> ${s.go} ` : ""}
            ${s.hold ? `<span class="badge-hold">HOLD</span> ${s.hold} ` : ""}
            ${s.pass ? `<span class="badge-pass">PASS</span> ${s.pass}` : ""}
            ${s.careful ? `／注意: ${s.careful}` : ""}
            ${s.how ? `<div class="note">${s.how}</div>` : ""}
          </li>`
        )
        .join("");
      const hard = (m.hard_pass || [])
        .map((h) => `<li>${h.reason}</li>`)
        .join("");
      const pt = m.buy_points;
      document.getElementById("points").innerHTML = `
        <section class="card">
          <h2>判定尺</h2>
          <p><span class="badge-go">GO</span> ${v.GO.min}点以上 — ${v.GO.meaning}</p>
          <p><span class="badge-hold">HOLD</span> ${v.HOLD.min}点以上 — ${v.HOLD.meaning}</p>
          <p><span class="badge-pass">PASS</span> 未満 — ${v.PASS.meaning}</p>
        </section>
        <section class="card">
          <h2>即PASS</h2>
          <ul class="list">${hard}</ul>
        </section>
        <section class="card">
          <h2>カタログで見る順</h2>
          <ol class="list">${steps}</ol>
        </section>
        <section class="card">
          <h2>加点テーブル要約</h2>
          <table class="tbl">
            <tbody>
              <tr><td>牝系全体 S/A/B/C/U</td><td class="num">${pt.family_overall.S}/${pt.family_overall.A}/${pt.family_overall.B}/${pt.family_overall.C}/${pt.family_overall.U}</td></tr>
              <tr><td>広尾独自 S/A/B/C</td><td class="num">${pt.hiroo_unique.S}/${pt.hiroo_unique.A}/${pt.hiroo_unique.B}/${pt.hiroo_unique.C}</td></tr>
              <tr><td>看板 S/A</td><td class="num">${pt.signature_line.S}/${pt.signature_line.A}</td></tr>
              <tr><td>厩舎 S/A/B/C</td><td class="num">${pt.trainer_hiroo.S}/${pt.trainer_hiroo.A}/${pt.trainer_hiroo.B}/${pt.trainer_hiroo.C}</td></tr>
              <tr><td>クロス S/A/B/C</td><td class="num">${pt.cross.S}/${pt.cross.A}/${pt.cross.B}/${pt.cross.C}</td></tr>
              <tr><td>父 上位/中位/下位</td><td class="num">${pt.sire_tier.top}/${pt.sire_tier.mid}/${pt.sire_tier.low}</td></tr>
            </tbody>
          </table>
        </section>
        <section class="card">
          <h2>ポケットカード</h2>
          <ol class="list">${(m.pocket_card || []).map((x) => `<li>${x}</li>`).join("")}</ol>
        </section>`;
    },
  };

  window.SheetApp = SheetApp;
})();
