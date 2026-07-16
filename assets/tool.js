/* Club Scout companion tool — suggest + unknown follow-up */
(function () {
  const D = window.CLUB_DATA;
  if (!D) return;
  const gj = D.meta.grade_ja;
  const sj = D.meta.sire_ja;
  const labelG = (g) => (g && gj[g] ? gj[g].short : g || "未設定");
  const labelS = (t) => (t && sj[t] ? sj[t].short : t || "下位（low）");
  const norm = (s) =>
    String(s || "")
      .toLowerCase()
      .replace(/\s+/g, "")
      .replace(/[ァ-ン]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60));

  function el(id) {
    return document.getElementById(id);
  }

  function fillLists() {
    const t = el("trainerList");
    const s = el("sireList");
    const f = el("familyList");
    if (t) t.innerHTML = D.trainers.map((x) => `<option value="${x.name}">`).join("");
    if (s) s.innerHTML = D.sires.map((x) => `<option value="${x.name}">`).join("");
    if (f) {
      const famNames = [...D.families.map((x) => x.name), ...D.family_aliases.map((x) => x.alias)];
      f.innerHTML = famNames.map((n) => `<option value="${n}">`).join("");
    }
    if (el("ver")) {
      el("ver").textContent = `${D.meta.version || ""} / ranks ${D.meta.ranks_generated_at || ""}`;
    }
  }

  function scoreMatch(q, name) {
    const nq = norm(q);
    const nn = norm(name);
    if (!nq) return 0;
    if (nn === nq) return 100;
    if (nn.startsWith(nq)) return 80;
    if (nn.includes(nq)) return 60;
    // char overlap for partial JP
    let hit = 0;
    for (const ch of nq) if (nn.includes(ch)) hit++;
    return hit >= Math.min(2, nq.length) ? 20 + hit : 0;
  }

  function findTrainer(name) {
    const n = (name || "").trim();
    if (!n) return null;
    return (
      D.trainers.find((t) => t.name === n) ||
      D.trainers.find((t) => scoreMatch(n, t.name) >= 60) ||
      null
    );
  }
  function findSire(name) {
    const n = (name || "").trim();
    if (!n) return null;
    let hit = D.sires.find((s) => s.name === n);
    if (hit) return { ...hit, unlisted: false };
    hit = D.sires.find((s) => scoreMatch(n, s.name) >= 60);
    if (hit) return { ...hit, unlisted: false };
    return {
      name: n,
      score: D.sire_default,
      tier: D.sire_default >= 2.8 ? "mid" : "low",
      tier_ja: labelS(D.sire_default >= 2.8 ? "mid" : "low"),
      unlisted: true,
    };
  }
  function findFamily(name) {
    const n = (name || "").trim();
    if (!n) return { hit: null, alias: null, missing: false };
    const alias = D.family_aliases.find((a) => scoreMatch(n, a.alias) >= 60 || a.alias === n);
    const hit =
      D.families.find((f) => f.name === n) ||
      D.families.find((f) => scoreMatch(n, f.name) >= 60) ||
      null;
    return { hit, alias, missing: !hit && !alias && !!n };
  }
  function findCross(trainer, family) {
    if (!trainer || !family) return null;
    const exact = D.crosses.find((c) => c.trainer === trainer && c.family === family);
    if (exact) return exact;
    return (
      D.crosses.find(
        (c) => scoreMatch(trainer, c.trainer) >= 60 && scoreMatch(family, c.family) >= 60
      ) || null
    );
  }

  function pickProfiles(trainer, sire) {
    const tb = (D.weight.trainer_bands || []).find((x) => scoreMatch(trainer, x.name) >= 60);
    const sb = (D.weight.sire_bands || []).find((x) => scoreMatch(sire, x.name) >= 60);
    const ids = new Set();
    if (tb) ids.add(tb.profile_id);
    if (sb) ids.add(sb.profile_id);
    let picked = D.weight.profiles.filter((p) => ids.has(p.id));
    if (!picked.length) picked = [D.weight.profiles.find((p) => p.id === "default")];
    const okMin = Math.max(...picked.map((p) => p.ok_min));
    const okMax = Math.min(...picked.map((p) => p.ok_max));
    return { picked, okMin, okMax, tb, sb };
  }

  /** Attach partial-match suggestion UI under an input */
  function attachSuggest(input, getItems, onPick) {
    if (!input || input.dataset.suggestBound) return;
    input.dataset.suggestBound = "1";
    const wrap = document.createElement("div");
    wrap.className = "suggest";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const list = document.createElement("div");
    list.className = "suggest-list";
    wrap.appendChild(list);

    const render = () => {
      const q = input.value.trim();
      const items = getItems(q).slice(0, 10);
      if (!q || !items.length) {
        list.classList.remove("on");
        list.innerHTML = "";
        return;
      }
      list.innerHTML = items
        .map(
          (it) =>
            `<button type="button" data-v="${it.value.replace(/"/g, "&quot;")}">
              ${it.label}<span class="meta">${it.meta || ""}</span>
            </button>`
        )
        .join("");
      list.classList.add("on");
    };

    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    list.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-v]");
      if (!btn) return;
      input.value = btn.getAttribute("data-v");
      list.classList.remove("on");
      if (onPick) onPick(input.value);
      input.dispatchEvent(new Event("change"));
    });
    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) list.classList.remove("on");
    });
  }

  function trainerItems(q) {
    return D.trainers
      .map((t) => ({
        value: t.name,
        label: t.name,
        meta: `${labelG(t.effective_grade)} / 加点+${D.points_trainer[t.effective_grade] ?? 0}`,
        score: scoreMatch(q, t.name),
      }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
  }
  function sireItems(q) {
    return D.sires
      .map((s) => ({
        value: s.name,
        label: s.name,
        meta: `${s.tier_ja} / +${D.points_sire[s.tier]}`,
        score: scoreMatch(q, s.name),
      }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
  }
  function familyItems(q) {
    const base = D.families.map((f) => ({
      value: f.name,
      label: f.name,
      meta: `全体${labelG(f.overall_grade)}${f.hiroo_unique ? " / 独自" + labelG(f.hiroo_family_grade) : ""}`,
      score: scoreMatch(q, f.name),
    }));
    const al = D.family_aliases.map((a) => ({
      value: a.alias,
      label: a.alias + "（運用）",
      meta: a.note,
      score: scoreMatch(q, a.alias),
    }));
    return [...base, ...al]
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
  }

  function followupHtml({ trainer, sire, family, famObj, trainerObj, sireObj, cross }) {
    const notes = [];
    if (trainer && !trainerObj) {
      notes.push(
        `厩舎「${trainer}」は過去データ未収録。等級を手動で選ぶか、近い候補を候補リストから選んでください（未照合時はデータ不足扱い）。`
      );
    }
    if (sireObj && sireObj.unlisted) {
      notes.push(
        `父「${sire}」は登録表になし → 既定値（${sireObj.tier_ja}）で採点。上位だと思えば手動で意識し、価格帯とセットで判断を。`
      );
    }
    if (family && famObj && famObj.missing) {
      notes.push(
        `牝系「${family}」はランクJSON未収録。全体/独自を手動上書きしてください。看板が分かれば看板欄へ（例: Stitching）。`
      );
    }
    if (famObj && famObj.alias && !famObj.hit) {
      notes.push(`運用別名ヒット: ${famObj.alias.alias} — ${famObj.alias.note}`);
    }
    if (trainer && family && !cross) {
      notes.push("この厩舎×牝系のクロス実績はデータにありません（クロス加点なし）。C1/C3で補えるか確認。");
    }
    if (!notes.length) return "";
    return `<div class="warn-box"><strong>未収録・フォロー</strong><ul class="list">${notes
      .map((n) => `<li>${n}</li>`)
      .join("")}</ul></div>`;
  }

  // lookup
  if (el("lookupQ")) {
    el("lookupQ").addEventListener("input", () => {
      const q = el("lookupQ").value.trim();
      const out = el("lookupOut");
      if (!q) {
        out.textContent = "入力すると候補を表示";
        out.classList.add("muted");
        return;
      }
      const tr = trainerItems(q).slice(0, 8);
      const si = sireItems(q).slice(0, 8);
      const fa = familyItems(q).slice(0, 8);
      const cx = D.crosses
        .filter((c) => scoreMatch(q, c.trainer) || scoreMatch(q, c.family))
        .slice(0, 8);
      out.classList.remove("muted");
      out.innerHTML = `
        <h3>厩舎候補</h3>
        ${tr.length ? tr.map((t) => `<div>${t.label} — <span class="muted">${t.meta}</span></div>`).join("") : "<div class='muted'>候補なし（手入力＋手動等級でフォロー）</div>"}
        <h3>父候補</h3>
        ${si.length ? si.map((s) => `<div>${s.label} — <span class="muted">${s.meta}</span></div>`).join("") : "<div class='muted'>候補なし（未登録は下位寄り既定）</div>"}
        <h3>牝系候補</h3>
        ${fa.length ? fa.map((f) => `<div>${f.label} — <span class="muted">${f.meta}</span></div>`).join("") : "<div class='muted'>候補なし（手動等級を推奨）</div>"}
        <h3>クロス</h3>
        ${cx.length ? cx.map((c) => `<div>${c.trainer} × ${c.family} — ${labelG(c.grade)}</div>`).join("") : "<div class='muted'>なし</div>"}
      `;
    });
  }

  if (el("btnWeight")) {
    el("btnWeight").addEventListener("click", () => {
      const kg = Number(el("wKg").value);
      const trainer = el("wTrainer").value.trim();
      const sire = el("wSire").value.trim();
      const family = el("wFamily").value.trim();
      const out = el("weightOut");
      if (!kg) {
        out.textContent = "体重を入力してください";
        return;
      }
      const alertKg = D.weight.canonical.alert_kg;
      const light = kg <= alertKg;
      const { picked, okMin, okMax, tb, sb } = pickProfiles(trainer, sire);
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
        <p>統合OK目安: ${okMin}〜${okMax} kg（競合時は狭い帯）</p>
        <p>正本採点: ${
          light
            ? `<span class="badge-pass">軽量アラート（≤${alertKg}） ${D.weight.canonical.checklist_pts}</span>`
            : `<span class="badge-go">軽量アラートなし</span>`
        }</p>
        <p class="note">厩舎帯: ${tb ? `${tb.name} → ${tb.profile_title} ${tb.ok_min}–${tb.ok_max}` : "未割当→標準"} ／ 父帯: ${
          sb ? `${sb.name} → ${sb.profile_title} ${sb.ok_min}–${sb.ok_max}` : "未割当→標準"
        }</p>
        ${followupHtml({ trainer, sire, family, famObj: f, trainerObj: t, sireObj: s, cross: findCross(trainer, family) })}
      `;
    });
  }

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

  function runDecide() {
    if (!el("btnDecide")) return;
    const name = el("dName").value.trim();
    const price = Number(el("dPrice").value || 0);
    const trainerName = el("dTrainer").value.trim();
    const sireName = el("dSire").value.trim();
    const familyName = el("dFamily").value.trim();
    const sigName = el("dSig").value.trim();
    const status = el("dStatus").value;
    const kinjou = el("dKinjou").value;
    const weight = el("dWeight").value;
    const injury = el("dInjury").checked;
    const out = el("decideOut");

    let hard = null;
    if (status === "満口") hard = "満口";
    if (price > 4.0) hard = hard || "一口4万円超は原則見送り";
    if (injury) hard = hard || "近況に重大リスク語";

    const t = findTrainer(trainerName);
    const s = findSire(sireName);
    const fam = findFamily(familyName);
    const sig = findFamily(sigName);
    const crossAuto = findCross(trainerName, fam.hit ? fam.hit.name : familyName);

    let overall = el("dOverall").value;
    let unique = el("dUnique").value;
    let cross = el("dCross").value;
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
    if (cross === "auto") cross = crossAuto ? crossAuto.grade : "none";
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
    add("広尾×調教師", gradePts(D.points_trainer, trainerG), labelG(trainerG) + (t ? "" : "・未収録"));
    add("クロス", gradePts(D.points_cross, cross === "none" ? "none" : cross), labelG(cross));
    add("父", Number(D.points_sire[sireTier] ?? 0), labelS(sireTier) + (s && s.unlisted ? "・未登録" : ""));
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
    if (["S", "A"].includes(unique) && ["S", "A"].includes(trainerG))
      combos.push({ id: "C1", text: "C1 独自牝系×実績厩舎 → GO寄り" });
    if (["S", "A"].includes(cross)) combos.push({ id: "C2", text: "C2 クロス本命 → GO寄り" });
    if (["S", "A"].includes(overall) && sireTier === "top" && price <= 2.0)
      combos.push({ id: "C3", text: "C3 強牝系×上位父×手頃 → GO寄り" });
    if (["S", "A"].includes(signature) && ["B", "C", "none", "U"].includes(overall))
      combos.push({ id: "C4", text: "C4 看板が一段深い → HOLD〜条件付き" });
    if (price >= 2.5 && !["S", "A"].includes(cross) && !["S", "A"].includes(unique))
      combos.push({ id: "C5", text: "C5 高額なのに独自/クロス弱い → PASS寄り" });

    let verdict = "PASS";
    if (!hard) {
      if (points >= 12) verdict = "GO";
      else if (points >= 8) verdict = "HOLD";
    }
    const cls = verdict === "GO" ? "badge-go" : verdict === "HOLD" ? "badge-hold" : "badge-pass";
    out.classList.remove("muted");
    out.innerHTML = `
      <p><span class="${cls}" style="font-size:1.4rem;font-family:var(--font-d)">${verdict}</span>
      <strong style="margin-left:8px">${points} pt</strong>
      ${name ? ` — ${name}` : ""}</p>
      ${hard ? `<p class="badge-pass">即PASS: ${hard}</p>` : ""}
      <ul class="list">
        ${detail
          .map(
            (d) =>
              `<li>${d.item}: <strong>${d.pts >= 0 ? "+" : ""}${d.pts}</strong> <span class="muted">(${d.note})</span></li>`
          )
          .join("")}
      </ul>
      <p><strong>点灯コンボ</strong></p>
      ${
        combos.length
          ? `<ul class="list">${combos.map((c) => `<li><strong>${c.id}</strong> ${c.text.replace(/^C\d\s*/, "")}</li>`).join("")}</ul>`
          : "<p class='muted'>なし</p>"
      }
      <p class="note">クロス自動: ${
        crossAuto ? `${crossAuto.trainer}×${crossAuto.family} = ${labelG(crossAuto.grade)}` : "データなし"
      }</p>
      ${followupHtml({
        trainer: trainerName,
        sire: sireName,
        family: familyName,
        famObj: fam,
        trainerObj: t,
        sireObj: s,
        cross: crossAuto,
      })}
    `;

    // sync combo panel if present
    if (el("comboOut")) {
      el("comboOut").classList.remove("muted");
      el("comboOut").innerHTML = combos.length
        ? combos.map((c) => `<div><strong>${c.id}</strong> — ${c.text}</div>`).join("")
        : "点灯なし（条件未達 or 未収録で等級が弱い）";
    }
  }

  if (el("btnDecide")) el("btnDecide").addEventListener("click", runDecide);

  // combo-only checker
  if (el("btnCombo")) {
    el("btnCombo").addEventListener("click", () => {
      // reuse decide fields if filled; else combo-specific
      if (el("dTrainer") && el("dTrainer").value) {
        runDecide();
        return;
      }
    });
  }

  // wire suggests
  [
    ["wTrainer", trainerItems],
    ["dTrainer", trainerItems],
    ["wSire", sireItems],
    ["dSire", sireItems],
    ["wFamily", familyItems],
    ["dFamily", familyItems],
    ["dSig", familyItems],
  ].forEach(([id, fn]) => {
    const input = el(id);
    if (input) attachSuggest(input, fn);
  });

  fillLists();
  if (location.hash === "#weight" && el("weight")) {
    el("weight").scrollIntoView();
  }
})();
