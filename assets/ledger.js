(() => {
  const STORAGE_KEY = "club-scout-ledger-v1";

  const els = {
    openingBalance: document.getElementById("openingBalance"),
    openingDate: document.getElementById("openingDate"),
    btnSaveOpening: document.getElementById("btnSaveOpening"),
    openingNote: document.getElementById("openingNote"),
    sumOpening: document.getElementById("sumOpening"),
    sumIncome: document.getElementById("sumIncome"),
    sumExpense: document.getElementById("sumExpense"),
    sumBalance: document.getElementById("sumBalance"),
    entryDate: document.getElementById("entryDate"),
    entryType: document.getElementById("entryType"),
    entryName: document.getElementById("entryName"),
    entryAmount: document.getElementById("entryAmount"),
    entryMemo: document.getElementById("entryMemo"),
    btnAddEntry: document.getElementById("btnAddEntry"),
    entryNote: document.getElementById("entryNote"),
    filterType: document.getElementById("filterType"),
    btnClearAll: document.getElementById("btnClearAll"),
    entryList: document.getElementById("entryList"),
  };

  function todayISO() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
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
    } catch {
      return { opening: null, entries: [] };
    }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
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
      if (e.type === "income") income += e.amount;
      else expense += e.amount;
    }
    const opening = state.opening ? Number(state.opening.amount) : null;
    const balance = opening == null ? null : opening + income - expense;
    return { opening, income, expense, balance };
  }

  function renderSummary() {
    const t = totals();
    els.sumOpening.textContent = t.opening == null ? "未設定" : formatYen(t.opening);
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
            <span class="ledger-date">${e.date}</span>
            <span class="ledger-type ${e.type}">${typeLabel}</span>
          </div>
          <div class="ledger-name">${escapeHtml(e.name)}</div>
          ${e.memo ? `<div class="ledger-memo">${escapeHtml(e.memo)}</div>` : ""}
        </div>
        <div class="ledger-row-side">
          <div class="ledger-amount ${amtClass}">${formatSignedYen(e.amount, e.type)}</div>
          <button type="button" class="ghost danger" data-del="${e.id}">削除</button>
        </div>
      `;
      els.entryList.appendChild(row);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function render() {
    renderSummary();
    renderList();
  }

  function setEntryNote(msg, isError) {
    els.entryNote.textContent = msg || "";
    els.entryNote.classList.toggle("warn", !!isError);
  }

  els.btnSaveOpening.addEventListener("click", () => {
    const amount = Number(els.openingBalance.value);
    const date = els.openingDate.value;
    if (!date) {
      els.openingNote.textContent = "基準日は必須です。";
      els.openingNote.classList.add("warn");
      return;
    }
    if (!Number.isFinite(amount)) {
      els.openingNote.textContent = "初期残高（数値）は必須です。";
      els.openingNote.classList.add("warn");
      return;
    }
    state.opening = { amount: Math.round(amount), date };
    saveState(state);
    render();
  });

  els.btnAddEntry.addEventListener("click", () => {
    if (!state.opening) {
      setEntryNote("先に初期残高と基準日を保存してください。", true);
      return;
    }
    const date = els.entryDate.value;
    const name = (els.entryName.value || "").trim();
    const amount = Number(els.entryAmount.value);
    const type = els.entryType.value === "income" ? "income" : "expense";
    const memo = (els.entryMemo.value || "").trim();

    if (!date) {
      setEntryNote("日付は必須です。", true);
      return;
    }
    if (!name) {
      setEntryNote("項目名は必須です。", true);
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setEntryNote("金額は1円以上の数値で入力してください。", true);
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
    saveState(state);
    els.entryName.value = "";
    els.entryAmount.value = "";
    els.entryMemo.value = "";
    els.entryDate.value = todayISO();
    setEntryNote("追加しました。", false);
    render();
  });

  els.entryList.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-del]");
    if (!btn) return;
    const id = btn.getAttribute("data-del");
    if (!confirm("この記録を削除しますか？")) return;
    state.entries = state.entries.filter((e) => e.id !== id);
    saveState(state);
    render();
  });

  els.filterType.addEventListener("change", render);

  els.btnClearAll.addEventListener("click", () => {
    if (!state.entries.length) return;
    if (!confirm("すべての記録を削除しますか？（初期残高は残ります）")) return;
    state.entries = [];
    saveState(state);
    render();
  });

  ensureDefaults();
  render();
})();
