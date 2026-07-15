# -*- coding: utf-8 -*-
"""候補馬の保存・近況追記（ローカルJSON）。"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CLUB = Path(__file__).resolve().parent
CANDIDATES_PATH = CLUB / "data" / "candidates.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_candidates(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or CANDIDATES_PATH
    if not path.exists():
        return {"updated_at": None, "candidates": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_candidates(data: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or CANDIDATES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = deepcopy(data)
    data["updated_at"] = _now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def upsert_candidate(candidate: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    data = load_candidates(path)
    cid = str(candidate.get("id") or "").strip()
    if not cid:
        raise ValueError("candidate.id が必要です")
    found = False
    for i, c in enumerate(data.get("candidates", [])):
        if str(c.get("id")) == cid:
            merged = deepcopy(c)
            merged.update(candidate)
            data["candidates"][i] = merged
            found = True
            break
    if not found:
        data.setdefault("candidates", []).append(candidate)
    save_candidates(data, path)
    return data


def append_kinjou(
    candidate_id: str,
    paste_text: str,
    note: str = "",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    data = load_candidates(path)
    for c in data.get("candidates", []):
        if str(c.get("id")) == str(candidate_id):
            hist: List[Dict[str, Any]] = list(c.get("kinjou_history") or [])
            hist.append(
                {
                    "at": _now(),
                    "text": paste_text,
                    "note": note,
                }
            )
            c["kinjou_history"] = hist
            c["kinjou_latest"] = paste_text
            save_candidates(data, path)
            return data
    raise KeyError(f"candidate_id={candidate_id} が見つかりません")
