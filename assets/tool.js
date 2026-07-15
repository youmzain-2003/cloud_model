/* Club Scout companion tool */
(function () {
  const D = window.CLUB_DATA;
  const gj = D.meta.grade_ja;
  const sj = D.meta.sire_ja;
  const labelG = (g) => (g && gj[g] ? gj[g].short : g || "未設定");
  const labelS = (t) => (t && sj[t] ? sj[t].short : t || "下位（low）");

  function fillLists() {
    const t = document.getElementById("trainerList");
    const s = document.getElementById("sireList");
    const f = document.getElementById("familyList");
    t.innerHTML = D.trainers.map((x) => `<option value="${x.name}">`).join("");
    s.innerHTML = D.sires.map((x) => `<option value="${x.name}">`).join("");
    const famNames = [
      ...D.families.map((x) => x.name),
      ...D.family_aliases.map((x) => x.alias),
    ];
    f.innerHTML = famNames.map((n) => `<option value="${n}">`).join("");
    document.getElementById("ver").textContent =
      `${D.meta.version || ""} / ranks ${D.meta.ranks_generated_at || ""}`;
  }

  function findTrainer(name) {
    const n = (name || "").trim();
    if (!n) return null;
    return (
      D.trainers.find((t) => t.name === n) ||
      D.trainers.find((t) => n.includes(t.name) || t.name.includes(n)) ||
      null
    );
  }
  function findSire(name) {
    const n = (name || "").trim();
    if (!n) return null;
    let hit = D.sires.find((s) => s.name === n);
    if (hit) return hit;
    hit = D.sires.find((s) => n.includes(s.name) || s.name.includes(n));
    if (hit) return hit;
    return { name: n, score: D.sire_default, tier: D.sire_default >= 2.8 ? "mid" : "low", tier_ja: labelS(D.sire_default >= 2.8 ? "mid" : "low"), unlisted: true };
  }
  function findFamily(name) {
    const n = (name || "").trim();
    if (!n) return null;
    const alias = D.family_aliases.find((a) => a.alias === n || n.includes(a.alias));
    const hit =
      D.families.find((f) => f.name === n) ||
      D.families.find((f) => n.includes(f.name) || f.name.includes(n));
    return { hit, alias };
  }
  function findCross(trainer, family) {
    if (!trainer || !family) return null;
    const exact = D.crosses.find((c) => c.trainer === trainer && c.family === family);
    if (exact) return exact;
    return (
      D.crosses.find(
        (c) =>
          (trainer.includes(c.trainer) || c.trainer.includes(trainer)) &&
          (family.includes(c.family) || c.family.includes(family))
      ) || null
    );
  }

  function pickProfiles(trainer, sire) {
    const picked = [];
    for (const p of D.weight.profiles) {
      if (p.id === "default") continue;
      const tHit = p.trainers.some((t) => trainer && (trainer.includes(t) || t.includes(trainer)));
      const sHit = p.sires_hint.some((s) => sire && (sire.includes(s) || s.includes(sire)));
      if (tHit || sHit) picked.push({ ...p, tHit, sHit });
    }
    if (!picked.length) picked.push(D.weight.profiles.find((p) => p.id === "default"));
    // conservative merge: narrowest band
    const okMin = Math.max(...picked.map((p) => p.ok_min));
    const okMax = Math.min(...picked.map((p) => p.ok_max));
    return { picked, okMin, okMax };
  }

  // lookup
  document.getElementById("lookupQ").addEventListener("input", () => {
    const q = document.getElementById("lookupQ").value.trim().toLowerCase();
    const out = document.getElementById("lookupOut");
    if (!q) {
      out.textContent = "入力すると候補を表示";
      out.classList.add("muted");
      return;
    }
    const tr = D.trainers.filter((t) => t.name.toLowerCase().includes(q)).slice(0, 8);
    const si = D.sires.filter((s) => s.name.toLowerCase().includes(q)).slice(0, 8);
    const fa = D.families.filter((f) => f.name.toLowerCase().includes(q)).slice(0, 8);
    const cx = D.crosses
      .filter((c) => `${c.trainer} ${c.family}`.toLowerCase().includes(q))
      .slice(0, 8);
    const al = D.family_aliases.filter((a) => a.alias.toLowerCase().includes(q));
    out.classList.remove("muted");
    out.innerHTML = `
      <h3>厩舎</h3>
      ${tr.length ? tr.map((t) => `<div>${t.name} — ${labelG(t.effective_grade)}（加点候補 ${D.points_trainer[t.effective_grade] ?? 0}）</div>`).join("") : "<div class='muted'>なし</div>"}
      <h3>父</h3>
      ${si.length ? si.map((s) => `<div>${s.name} — ${s.tier_ja}（+${D.points_sire[s.tier]}）</div>`).join("") : "<div class='muted'>なし</div>"}
      <h3>牝系</h3>
      ${fa.length ? fa.map((f) => `<div>${f.name} — 全体${labelG(f.overall_grade)}${f.hiroo_unique ? " / 独自" + labelG(f.hiroo_family_grade) : ""}</div>`).join("") : "<div class='muted'>なし</div>"}
      ${al.length ? `<h3>運用別名</h3>${al.map((a) => `<div>${a.alias}: ${a.note}</div>`).join("")}` : ""}
      <h3>クロス</h3>
      ${cx.length ? cx.map((c) => `<div>${c.trainer} × ${c.family} — ${labelG(c.grade)}</div>`).join("") : "<div class='muted'>なし</div>"}
    `;
  });

  document.getElementById("btnWeight").addEventListener("click", () => {
    const kg = Number(document.getElementById("wKg").value);
    const trainer = document.getElementById("wTrainer").value.trim();
    const sire = document.getElementById("wSire").value.trim();
    const family = document.getElementById("wFamily").value.trim();
    const out = document.getElementById("weightOut");
    if (!kg) {
      out.textContent = "体重を入力してください";
      return;
    }
    const alertKg = D.weight.canonical.alert_kg;
    const light = kg <= alertKg;
    const { picked, okMin, okMax } = pickProfiles(trainer, sire);
    let band = "OK帯";
    if (kg < okMin) band = "下限注意";
    if (kg > okMax) band = "上限注意";
    if (kg <= D.weight.base_band.watch_low || kg >= D.weight.base_band.watch_high) {
      if (band === "OK帯") band = "警戒線付近";
    }
    const t = findTrainer(trainer);
    const s = findSire(sire);
    const f = findFamily(family);
    out.classList.remove("muted");
    out.innerHTML = `
      <p><strong>体重 ${kg} kg</strong> — 統合帯判定: <strong>${band}</strong></p>
      <p>統合OK目安: ${okMin}〜${okMax} kg（競合時は狭い帯を採用）</p>
      <p>正本採点: ${light ? `<span class="badge-pass">軽量アラート発動（≤${alertKg}） checklist ${D.weight.canonical.checklist_pts}</span>` : `<span class="badge-go">軽量アラートなし</span>`}</p>
      <p class="note">適用プロファイル: ${picked.map((p) => p.title).join(" ／ ")}</p>
      <p class="note">厩舎: ${t ? labelG(t.effective_grade) : "未照合"} ／ 父: ${s ? labelS(s.tier) : "-"} ／ 牝系: ${
        f.hit ? labelG(f.hit.overall_grade) : f.alias ? "運用別名あり" : "未照合"
      }</p>
      <p class="note">※プロファイル帯は運用ガイド。点数に効くのは正本の ${alertKg}kg 線のみ。</p>
    `;
  });

  function gradePts(table, g) {
    if (!g || g === "none") return Number(table.none ?? 0);
    return Number(table[g] ?? table.none ?? 0);
  }

  function pricePts(price) {
    for (const tier of D.points_price) {
      if (price <= Number(tier.max)) return Number(tier.pts);
    }
    return -2;
  }

  document.getElementById("btnDecide").addEventListener("click", () => {
    const name = document.getElementById("dName").value.trim();
    const price = Number(document.getElementById("dPrice").value || 0);
    const trainerName = document.getElementById("dTrainer").value.trim();
    const sireName = document.getElementById("dSire").value.trim();
    const familyName = document.getElementById("dFamily").value.trim();
    const sigName = document.getElementById("dSig").value.trim();
    const status = document.getElementById("dStatus").value;
    const kinjou = document.getElementById("dKinjou").value;
    const weight = document.getElementById("dWeight").value;
    const injury = document.getElementById("dInjury").checked;
    const out = document.getElementById("decideOut");

    let hard = null;
    if (status === "満口") hard = "満口";
    if (price > 4.0) hard = hard || "一口4万円超は原則見送り";
    if (injury) hard = hard || "近況に重大リスク語";

    const t = findTrainer(trainerName);
    const s = findSire(sireName);
    const fam = findFamily(familyName);
    const sig = findFamily(sigName);
    const crossAuto = findCross(trainerName, fam.hit ? fam.hit.name : familyName);

    let overall = document.getElementById("dOverall").value;
    let unique = document.getElementById("dUnique").value;
    let cross = document.getElementById("dCross").value;
    let signature = "none";

    if (overall === "auto") {
      if (fam.hit) overall = fam.hit.overall_grade || "U";
      else if (fam.alias && fam.alias.manual_unique) overall = fam.alias.manual_unique;
      else overall = familyName ? "U" : "none";
    }
    if (unique === "auto") {
      if (fam.hit && fam.hit.hiroo_unique) unique = fam.hit.hiroo_family_grade || "none";
      else if (fam.alias && fam.alias.manual_unique) unique = fam.alias.manual_unique;
      else unique = "none";
    }
    if (cross === "auto") {
      cross = crossAuto ? crossAuto.grade : "none";
    }
    if (sig.hit) {
      signature = sig.hit.hiroo_unique
        ? sig.hit.hiroo_family_grade || sig.hit.overall_grade || "none"
        : sig.hit.overall_grade || "none";
    } else if (fam.alias && fam.alias.suggest_signature) {
      const sug = D.families.find((f) => f.name === fam.alias.suggest_signature);
      if (sug) signature = sug.hiroo_family_grade || sug.overall_grade || "none";
    }

    const trainerG = t ? t.effective_grade : trainerName ? "U" : "none";
    const sireTier = s ? s.tier : "low";

    const detail = [];
    let points = 0;
    const add = (item, pts, note) => {
      points += pts;
      detail.push({ item, pts, note });
    };
    add("牝系全体", gradePts(D.points_family_overall, overall), labelG(overall));
    add("広尾独自", gradePts(D.points_hiroo_unique, unique === "none" ? "none" : unique), labelG(unique));
    add("看板牝系", gradePts(D.points_signature, signature), labelG(signature));
    add("広尾×調教師", gradePts(D.points_trainer, trainerG), labelG(trainerG));
    add("クロス", gradePts(D.points_cross, cross === "none" ? "none" : cross), labelG(cross));
    add("父", Number(D.points_sire[sireTier] ?? 0), labelS(sireTier));
    add("価格", pricePts(price), `${price || 0}万円`);

    let kpts = 0;
    let knote = "なし";
    if (kinjou === "good") {
      kpts += D.points_kinjou.positive_hit;
      knote = "好調";
    }
    if (kinjou === "mild") {
      kpts += D.points_kinjou.negative_mild;
      knote = "注意語";
    }
    const w = weight === "" ? null : Number(weight);
    if (w != null && !Number.isNaN(w) && w <= D.weight.canonical.alert_kg) {
      kpts += D.points_kinjou.light_weight;
      knote = knote === "なし" ? "軽量帯" : knote + "／軽量帯";
    }
    add("近況・体重", kpts, knote);

    const combos = [];
    if (["S", "A"].includes(unique) && ["S", "A"].includes(trainerG)) combos.push("C1 独自牝系×実績厩舎 → GO寄り");
    if (["S", "A"].includes(cross)) combos.push("C2 クロス本命 → GO寄り");
    if (["S", "A"].includes(overall) && sireTier === "top" && price <= 2.0) combos.push("C3 強牝系×上位父×手頃 → GO寄り");
    if (["S", "A"].includes(signature) && ["B", "C", "none", "U"].includes(overall)) combos.push("C4 看板が一段深い → HOLD〜条件付き");
    if (price >= 2.5 && !["S", "A"].includes(cross) && !["S", "A"].includes(unique)) combos.push("C5 高額なのに独自/クロス弱い → PASS寄り");

    let verdict = "PASS";
    if (!hard) {
      if (points >= 12) verdict = "GO";
      else if (points >= 8) verdict = "HOLD";
    } else {
      verdict = "PASS";
    }
    const cls = verdict === "GO" ? "badge-go" : verdict === "HOLD" ? "badge-hold" : "badge-pass";
    out.classList.remove("muted");
    out.innerHTML = `
      <p><span class="${cls}" style="font-size:1.4rem;font-family:var(--font-d)">${verdict}</span>
      <strong style="margin-left:8px">${points} pt</strong>
      ${name ? ` — ${name}` : ""}</p>
      ${hard ? `<p class="badge-pass">即PASS: ${hard}</p>` : ""}
      <ul class="list">
        ${detail.map((d) => `<li>${d.item}: <strong>${d.pts >= 0 ? "+" : ""}${d.pts}</strong> <span class="muted">(${d.note})</span></li>`).join("")}
      </ul>
      ${combos.length ? `<p><strong>コンボ</strong><br>${combos.join("<br>")}</p>` : "<p class='muted'>コンボ点灯なし</p>"}
      <p class="note">クロス自動: ${crossAuto ? `${crossAuto.trainer}×${crossAuto.family} = ${labelG(crossAuto.grade)}` : "データなし"}</p>
    `;
  });

  fillLists();
  if (location.hash === "#weight") {
    document.getElementById("weight").scrollIntoView();
  }
})();
