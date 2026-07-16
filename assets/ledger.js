(() => {
  const STORAGE_KEY = "club-scout-ledger-v1";

  function $(id) {
    const el = document.getElementById(id);
    if (!el) throw new Error("missing element: #" + id);
    return el;
  }

  const els = {
    openingForm: $("openingForm"),
    openingBalance: $("openingBalance"),
    openingDate: $("openingDate"),
    openingNote: $("openingNote"),
    sumOpening: $("sumOpening"),
    sumIncome: $("sumIncome"),
    sumExpense: $("sumExpense"),
    sumBalance: $("sumBalance"),
    entryForm: $("entryForm"),
    entryDate: $("entryDate"),
    entryType: $("entryType"),
    entryName: $("entryName"),
    entryAmount: $("entryAmount"),
    entryMemo: $("entryMemo"),
    entryNote: $("entryNote"),
    filterType: $("filterType"),
    btnClearAll: $("btnClearAll"),
    entryList: $("entryList"),
  };

  function todayISO() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function parseAmount(raw) {
    if (raw == null) return NaN;
    const s = String(raw).trim().replace(/,/g, "").replace(/[￥¥]/g, "");
    if (s === "") return NaN;
    return Number(s);
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { opening: null, entries: [] };
      const parsed = JSON.parse(raw);
      return {
        opening: parsed.opening && typeof parsed.opening === "object" ? parsed.opening : null,
        entries: Array.isArray(parsed.entries) ? parsed.entries : [],
      };
    } catch (err) {
      console.warn("ledger load failed", err);
      return { opening: null, entries: [] };
    }
  }

  function saveState(next) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return true;
    } catch (err) {
      console.warn("ledger save failed", err);
      return false;
    }
  }

  function formatYen(n) {
    if (!Number.isFinite(n)) return "—";
    return new Intl.NumberFormat("ja-JP", {
      style: "currency",
      currency: "JPY",
      maximumFractionDigits: 0,
    }).format(Math.round(n));
  }

  function formatSignedYen(n, type) {
    const body = formatYen(n).replace(/[￥¥]/g, "");
    return (type === "income" ? "+" : "−") + body;
  }

  function uid() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let state = loadState();

  function ensureDefaults() {
    if (!els.entryDate.value) els.entryDate.value = todayISO();
    if (state.opening) {
      els.openingBalance.value = String(state.opening.amount);
      els.openingDate.value = state.opening.date;
    } else if (!els.openingDate.value) {
      els.openingDate.value = todayISO();
    }
  }

  function totals() {
    let income = 0;
    let expense = 0;
    for (const e of state.entries) {
      if (e.type === "income") income += Number(e.amount) || 0;
      else expense += Number(e.amount) || 0;
    }
    const opening = state.opening ? Number(state.opening.amount) : null;
    const balance = opening == null || !Number.isFinite(opening) ? null : opening + income - expense;
    return { opening, income, expense, balance };
  }

  function renderSummary() {
    const t = totals();
    els.sumOpening.textContent = t.opening == null || !Number.isFinite(t.opening) ? "未設定" : formatYen(t.opening);
    els.sumIncome.textContent = formatYen(t.income);
    els.sumExpense.textContent = formatYen(t.expense);
    els.sumBalance.textContent = t.balance == null ? "—" : formatYen(t.balance);
    els.sumBalance.classList.toggle("amt-neg", t.balance != null && t.balance < 0);
    els.sumBalance.classList.toggle("amt-pos", t.balance != null && t.balance >= 0);

    if (state.opening) {
      els.openingNote.textContent = `保存済み: ${state.opening.date} 時点で ${formatYen(state.opening.amount)}`;
      els.openingNote.classList.remove("warn");
    } else {
      els.openingNote.textContent = "未設定です。先に初期残高と基準日を入れてください。";
      els.openingNote.classList.add("warn");
    }
  }

  function sortedEntries() {
    const filter = els.filterType.value;
    return state.entries
      .filter((e) => filter === "all" || e.type === filter)
      .slice()
      .sort((a, b) => {
        if (a.date !== b.date) return b.date.localeCompare(a.date);
        return (b.createdAt || 0) - (a.createdAt || 0);
      });
  }

  function renderList() {
    const rows = sortedEntries();
    if (!rows.length) {
      els.entryList.className = "ledger-list muted";
      els.entryList.textContent = state.entries.length
        ? "この絞り込みでは表示する記録がありません。"
        : "まだ記録がありません。";
      return;
    }

    els.entryList.className = "ledger-list";
    els.entryList.innerHTML = "";
    for (const e of rows) {
      const row = document.createElement("article");
      row.className = "ledger-row";
      row.dataset.id = e.id;

      const typeLabel = e.type === "income" ? "収入" : "支出";
      const amtClass = e.type === "income" ? "amt-in" : "amt-out";

      row.innerHTML = `
        <div class="ledger-row-main">
          <div class="ledger-row-top">
            <span class="ledger-date">${escapeHtml(e.date)}</span>
            <span class="ledger-type ${e.type}">${typeLabel}</span>
          </div>
          <div class="ledger-name">${escapeHtml(e.name)}</div>
          ${e.memo ? `<div class="ledger-memo">${escapeHtml(e.memo)}</div>` : ""}
        </div>
        <div class="ledger-row-side">
          <div class="ledger-amount ${amtClass}">${formatSignedYen(e.amount, e.type)}</div>
          <button type="button" class="ghost danger" data-del="${escapeHtml(e.id)}">削除</button>
        </div>
      `;
      els.entryList.appendChild(row);
    }
  }

  function render() {
    renderSummary();
    renderList();
  }

  function setEntryNote(msg, isError) {
    els.entryNote.textContent = msg || "";
    els.entryNote.classList.toggle("warn", !!isError);
  }

  function saveOpeningFromInputs() {
    const amount = parseAmount(els.openingBalance.value);
    const date = (els.openingDate.value || "").trim();
    if (!date) {
      els.openingNote.textContent = "基準日は必須です。";
      els.openingNote.classList.add("warn");
      return false;
    }
    if (!Number.isFinite(amount)) {
      els.openingNote.textContent = "初期残高（数値）は必須です。空欄は不可です。";
      els.openingNote.classList.add("warn");
      return false;
    }
    state.opening = { amount: Math.round(amount), date };
    if (!saveState(state)) {
      els.openingNote.textContent = "保存に失敗しました（プライベートモード等でストレージが使えない可能性があります）。";
      els.openingNote.classList.add("warn");
      return false;
    }
    render();
    return true;
  }

  els.openingForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    saveOpeningFromInputs();
  });

  els.entryForm.addEventListener("submit", (ev) => {
    ev.preventDefault();

    if (!state.opening) {
      // 初期残高欄に値が入っていれば、追加時にまとめて保存する
      if (!saveOpeningFromInputs()) {
        setEntryNote("先に初期残高と基準日を入れてください。", true);
        els.openingBalance.focus();
        return;
      }
    }

    const date = (els.entryDate.value || "").trim();
    const name = (els.entryName.value || "").trim();
    const amount = parseAmount(els.entryAmount.value);
    const type = els.entryType.value === "income" ? "income" : "expense";
    const memo = (els.entryMemo.value || "").trim();

    if (!date) {
      setEntryNote("日付は必須です。", true);
      els.entryDate.focus();
      return;
    }
    if (!name) {
      setEntryNote("項目名は必須です。", true);
      els.entryName.focus();
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setEntryNote("金額は1円以上の数値で入力してください。", true);
      els.entryAmount.focus();
      return;
    }

    state.entries.push({
      id: uid(),
      date,
      name,
      type,
      amount: Math.round(amount),
      memo,
      createdAt: Date.now(),
    });
    if (!saveState(state)) {
      setEntryNote("保存に失敗しました。", true);
      state.entries.pop();
      return;
    }
    els.entryName.value = "";
    els.entryAmount.value = "";
    els.entryMemo.value = "";
    els.entryDate.value = todayISO();
    setEntryNote("追加しました。", false);
    render();
    els.entryName.focus();
  });

  els.entryList.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-del]");
    if (!btn) return;
    const id = btn.getAttribute("data-del");
    if (!window.confirm("この記録を削除しますか？")) return;
    state.entries = state.entries.filter((e) => e.id !== id);
    saveState(state);
    render();
  });

  els.filterType.addEventListener("change", render);

  els.btnClearAll.addEventListener("click", () => {
    if (!state.entries.length) return;
    if (!window.confirm("すべての記録を削除しますか？（初期残高は残ります）")) return;
    state.entries = [];
    saveState(state);
    render();
  });

  try {
    ensureDefaults();
    render();
  } catch (err) {
    console.error(err);
    els.entryNote.textContent = "初期化に失敗しました: " + (err && err.message ? err.message : err);
    els.entryNote.classList.add("warn");
  }
})();
