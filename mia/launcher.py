from __future__ import annotations
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

import json
import math
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
import ast

from action_monitor import SecurityStop, guard_path_operation, log_effect, log_security_event
from workspace_security import (
    ALLOWED_SHARED_JSON,
    ensure_session_dir,
    ensure_within_workspace,
    get_workspace_dir,
    list_session_dirs,
    session_dir as workspace_session_dir,
    validate_session_name,
)

from config import RuntimeConfig
from memory_store import MemoryStore
from shared_memory import SharedResearchMemory, SharedEquation
from variable_debate_orchestrator import VariableDebateOrchestrator
from variable_repair_orchestrator import VariableRepairOrchestrator
from equation_debate_orchestrator import EquationDebateOrchestrator
from mutation_equation_orchestrator import MutationEquationOrchestrator
from repair_equation_orchestrator import RepairEquationOrchestrator
from test_debate_orchestrator import TestDebateOrchestrator


# ---------- Session helpers ----------
def normalize_target_equation(value) -> str:
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    value = str(value or "").strip()
    m = re.match(r"^T\d+\s*\|\s*(.+)$", value)
    if m:
        return m.group(1).strip()
    if " | " in value:
        return value.split(" | ", 1)[1].strip()
    return value

def _new_session_dir(base_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return ensure_session_dir(base_dir / f"alchemy_session_{timestamp}")


def list_sessions(base_dir: Path) -> list[Path]:
    ensure_within_workspace(base_dir)
    return list_session_dirs()


def resolve_session_dir(
    base_dir: Path,
    *,
    session_name: str | None = None,
    resume_latest: bool = False,
    create_new: bool = False,
    strict: bool = False,
) -> Path:
    sessions = list_sessions(base_dir)
    sessions_by_name = {p.name: p for p in sessions}

    if session_name:
        wanted = sessions_by_name.get(session_name)
        if wanted is None:
            if strict:
                raise FileNotFoundError(f"Session introuvable: {session_name}")
            return workspace_session_dir(session_name)
        return wanted

    if resume_latest:
        if not sessions:
            raise FileNotFoundError("Aucune session existante à reprendre.")
        return sessions[-1]

    if create_new:
        return _new_session_dir(base_dir)

    raise ValueError("Aucune stratégie de session fournie.")


def _cfg(
    *,
    session_name: str | None = None,
    resume_latest: bool = False,
    create_new: bool = False,
    strict: bool = False,
) -> RuntimeConfig:
    base_dir = get_workspace_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    cfg = RuntimeConfig(base_dir=base_dir)
    cfg.session_dir = resolve_session_dir(
        base_dir,
        session_name=session_name,
        resume_latest=resume_latest,
        create_new=create_new,
        strict=strict,
    )
    cfg.session_dir = ensure_session_dir(cfg.session_dir)
    log_security_event(risk='low', category='session', action='resolve', target=str(cfg.session_dir), reason='session selected')
    return cfg


# ---------- Generic utils ----------


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_eval_math(expr: str, safe_env: dict[str, Any]) -> float:
    allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
    allowed_unary = (ast.UAdd, ast.USub)

    def _eval(node: ast.AST):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.BinOp) and isinstance(node.op, allowed_binops):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
            if isinstance(node.op, ast.Mod):
                return left % right
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, allowed_unary):
            value = _eval(node.operand)
            return +value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.Name) and node.id in safe_env and isinstance(safe_env[node.id], (int, float)):
            return safe_env[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in safe_env:
            fn = safe_env[node.func.id]
            args = [_eval(arg) for arg in node.args]
            return fn(*args)
        raise ValueError(f"Expression interdite: {ast.dump(node, include_attributes=False)}")

    tree = ast.parse(expr, mode="eval")
    return float(_eval(tree))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalized_symbol(symbol: str) -> str:
    return str(symbol or "").strip().lower()


def _normalized_equation(eq: str) -> str:
    return "".join(str(eq or "").strip().lower().split())


def _structure_signature(eq: str) -> str:
    text = str(eq or "")
    text = text.lower()
    text = __import__("re").sub(r"\b\d+(?:[\.,]\d+)?\b", "N", text)
    text = __import__("re").sub(r"[a-zA-ZÀ-ÿ_][a-zA-ZÀ-ÿ0-9_Δ]*", "X", text)
    text = __import__("re").sub(r"\s+", "", text)
    return text


def _union_list(values: list[Any], limit: int | None = None) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in values:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    if limit is not None:
        out = out[-limit:]
    return out


def _sum_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    result = dict(a or {})
    for key, value in (b or {}).items():
        try:
            result[key] = result.get(key, 0) + value
        except Exception:
            result[key] = value
    return result


def _step(index: int, total: int, label: str) -> None:
    print(f"[STEP {index}/{total}] {label}")


def _step_done(index: int, total: int, label: str) -> None:
    print(f"[STEP {index}/{total}] OK - {label}")


def _extract_equation_from_block(block: str) -> str:
    import re

    patterns = [
        r"(?im)^\s*(?:\*\*)?(?:Équation|Equation)(?:\*\*)?\s*:\s*(.+?)\s*$",
        r"(?im)^\s*(?:Équation|Equation)\s*=\s*(.+?)\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, block or "")
        if m:
            eq = str(m.group(1) or "").strip().strip("*")
            if eq and eq.lower() not in {"-", "?", "aucune", "none"}:
                return eq
    return ""


def _extract_status_from_block(block: str) -> str:
    import re

    m = re.search(r"(?im)^\s*(?:\*\*)?Statut(?:\*\*)?\s*:\s*(.+?)\s*$", block or "")
    return str(m.group(1) if m else "").strip().lower()


def _infer_equations_from_log(session_dir: Path) -> list[dict[str, Any]]:
    import re

    log_path = session_dir / "equation_debate_log.txt"
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    matches = list(re.finditer(r"(?m)^---\s*equation tour\s+(\d+)\s*---\s*$", text))
    if not matches:
        return []

    by_turn: dict[int, list[str]] = {}
    for idx, m in enumerate(matches):
        turn = int(m.group(1))
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        by_turn.setdefault(turn, []).append(block)

    inferred: list[dict[str, Any]] = []
    seen: set[str] = set()
    priority = ["FinalValidator", "Synthetiseur", "Sentinelle", "Basilide", "Aurelius"]

    for turn in sorted(by_turn):
        blocks = by_turn[turn]
        chosen_eq = ""
        chosen_status = ""
        chosen_agent = ""
        chosen_block = ""
        for agent in priority:
            for block in blocks:
                if f"{agent}:" not in block:
                    continue
                eq = _extract_equation_from_block(block)
                if eq:
                    chosen_eq = eq
                    chosen_status = _extract_status_from_block(block)
                    chosen_agent = agent
                    chosen_block = block
                    break
            if chosen_eq:
                break
        if not chosen_eq:
            for block in blocks:
                eq = _extract_equation_from_block(block)
                if eq:
                    chosen_eq = eq
                    chosen_status = _extract_status_from_block(block)
                    chosen_agent = "log_recovery"
                    chosen_block = block
                    break
        key = _normalized_equation(chosen_eq)
        if not key or key in seen:
            continue
        seen.add(key)

        low = chosen_status.lower()
        approved = any(tok in low for tok in ["approuv", "valid", "consolid"])
        rejected = any(tok in low for tok in ["rejet", "absente"])
        repaired = "répar" in low or "repar" in low
        partial = any(tok in low for tok in ["partiel", "partielle"])
        fallback = "fallback" in (chosen_block or "").lower()
        repair_required = bool(rejected or repaired or partial or not approved)
        inferred.append({
            "equation": chosen_eq,
            "definitions": {},
            "mechanism": "",
            "experiment": "",
            "links": [],
            "remark": f"recovered_from_log:{session_dir.name}",
            "approved": bool(approved and not rejected),
            "source_turn": turn,
            "source_agent": chosen_agent or "log_recovery",
            "validation_summary": chosen_status or "recovered_from_log",
            "required_next": ["merge_log_recovery"],
            "status": "approved" if approved and not rejected else "partial",
            "fallback_used": fallback,
            "stable_parent": bool(approved and not repair_required and not fallback),
            "repair_required": repair_required,
            "memory_decision": "recovered_from_log",
            "object_calculated": "",
            "law_type": "",
            "architecture": "",
            "parent_equation": "",
            "parent_variable": "",
            "exploratory_parent": not approved,
            "repair_log": {
                "turn": turn,
                "status": chosen_status or "recovered_from_log",
                "original_equation": "",
                "fixed_equation": chosen_eq,
                "main_issue": "recovered_from_log",
                "fix_applied": "merge_log_import",
                "pattern": "merge_log_recovery",
            } if repair_required else {},
        })
    return inferred


def _enrich_shared_with_log_equations(session_dir: Path, shared: dict[str, Any]) -> tuple[dict[str, Any], int]:
    enriched = dict(shared or {})
    approved = list(enriched.get("approved_equations", []) or [])
    partial = list(enriched.get("partial_equations", []) or [])
    existing = {_normalized_equation(row.get("equation", "")) for row in approved + partial if row.get("equation")}
    recovered = 0
    for row in _infer_equations_from_log(session_dir):
        key = _normalized_equation(row.get("equation", ""))
        if not key or key in existing:
            continue
        existing.add(key)
        if row.get("approved"):
            approved.append(row)
        else:
            partial.append(row)
        recovered += 1
    if recovered:
        approved.sort(key=lambda r: int(r.get("source_turn", 0) or 0))
        partial.sort(key=lambda r: int(r.get("source_turn", 0) or 0))
        enriched["approved_equations"] = approved[-40:]
        enriched["partial_equations"] = partial[-40:]
    return enriched, recovered


# ---------- Reset / observability ----------


def reset_all_memory(base_dir: Path) -> None:
    base_dir = get_workspace_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []

    for path in list_session_dirs():
        try:
            guard_path_operation(path, action='rmtree')
            shutil.rmtree(path)
            log_effect('session_deleted', target=str(path), risk='medium')
            removed.append(str(path.name) + '/')
        except Exception:
            pass

    for path in base_dir.glob("*.json"):
        try:
            if path.name in ALLOWED_SHARED_JSON:
                guard_path_operation(path, action='unlink')
                path.unlink()
                log_effect('file_deleted', target=str(path), risk='medium')
                removed.append(path.name)
        except Exception:
            pass

    if removed:
        print("[RESET] Mémoire supprimée :")
        for item in sorted(set(removed)):
            print(" -", item)
    else:
        print("[RESET] Rien à supprimer.")


def _cleanup_shared(cfg: RuntimeConfig) -> None:
    try:
        SharedResearchMemory(cfg.session_dir).cleanup_memory()
    except Exception:
        pass


def _mutation_ready(cfg: RuntimeConfig) -> tuple[bool, str]:
    try:
        shared = SharedResearchMemory(cfg.session_dir)
        target = str(getattr(cfg, 'target_equation', '') or '').strip()
        return shared.can_start_mutation_for_equation(target) if target else shared.can_start_mutation()
    except Exception as exc:
        return False, f"erreur mémoire mutation: {exc}"


def _repair_ready(cfg: RuntimeConfig) -> tuple[bool, str]:
    try:
        shared = SharedResearchMemory(cfg.session_dir)
        target = str(getattr(cfg, 'target_equation', '') or '').strip()
        return shared.can_start_repair_for_equation(target) if target else shared.can_start_repair()
    except Exception as exc:
        return False, f"erreur mémoire repair: {exc}"


def _maybe_run_repair(cfg: RuntimeConfig, eq_turns: int = 1) -> bool:
    ok, reason = _repair_ready(cfg)
    if not ok:
        print(f"[INFO] Repair non lancé: {reason}")
        return False
    print(f"\n[INFO] Équation à vérifier détectée: passage en phase de réparation ({reason})\n")
    RepairEquationOrchestrator(cfg).run(turns=max(1, eq_turns))
    _cleanup_shared(cfg)
    return True


def _print_lineages(cfg: RuntimeConfig, limit: int = 5) -> None:
    shared = SharedResearchMemory(cfg.session_dir)
    print(shared.build_lineage_report(limit=limit))


# ---------- Merge helpers ----------


def _merge_variable_payload(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a or {})
    for field in [
        "definition",
        "unit",
        "measure",
        "role",
        "validation_summary",
        "family",
        "micro_equation",
        "experiment",
        "source_agent",
        "status",
        "kind",
        "description",
        "confidence",
        "justification",
    ]:
        if not out.get(field) and b.get(field):
            out[field] = b[field]
    for field in ["links", "remarks", "required_next", "usages"]:
        out[field] = _union_list(list(out.get(field, []) or []) + list(b.get(field, []) or []))
    for field in ["approved"]:
        out[field] = bool(out.get(field, False) or b.get(field, False))
    for field in ["source_turn", "first_seen", "turn"]:
        out[field] = max(int(out.get(field, 0) or 0), int(b.get(field, 0) or 0))
    if "last_seen" in out or "last_seen" in b:
        out["last_seen"] = max(int(out.get("last_seen", 0) or 0), int(b.get("last_seen", 0) or 0))
    if not out.get("name") and b.get("name"):
        out["name"] = b["name"]
    if not out.get("variable_name") and b.get("variable_name"):
        out["variable_name"] = b["variable_name"]
    return out


def _equation_memory_score(entry: dict[str, Any], shared: dict[str, Any]) -> float:
    eq = str(entry.get("equation", "") or "")
    score = 0.0
    score += 40 if entry.get("approved") else 0
    score += 20 if entry.get("stable_parent") else 0
    score -= 25 if entry.get("fallback_used") else 0
    score -= 20 if entry.get("repair_required") else 0
    score += 12 if entry.get("parent_equation") else 0
    score += 6 if entry.get("mechanism") else 0
    score += 5 if entry.get("experiment") else 0
    score += 4 if entry.get("object_calculated") else 0
    score += 4 if entry.get("architecture") else 0
    score += 3 if entry.get("law_type") else 0
    score += min(6, len(entry.get("links", []) or []))
    score += min(6, len(entry.get("definitions", {}) or {}))
    score += 4 if entry.get("validation_summary") else 0
    score += 3 if entry.get("repair_log") else 0
    score += 0.01 * int(entry.get("source_turn", 0) or 0)
    score += 2 * float((shared.get("equation_scores", {}) or {}).get(eq, 0) or 0)
    score += float((shared.get("equation_usage_count", {}) or {}).get(eq, 0) or 0)
    score -= 2 * float((shared.get("equation_failures", {}) or {}).get(eq, 0) or 0)
    return score


def _merge_equation_entry(winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, Any]:
    out = dict(winner or {})
    for field in [
        "mechanism",
        "experiment",
        "remark",
        "validation_summary",
        "memory_decision",
        "object_calculated",
        "law_type",
        "architecture",
        "parent_equation",
        "parent_variable",
        "source_agent",
        "status",
    ]:
        if not out.get(field) and loser.get(field):
            out[field] = loser[field]
    out["approved"] = bool(out.get("approved", False) or loser.get("approved", False))
    out["stable_parent"] = bool(out.get("stable_parent", False) or loser.get("stable_parent", False))
    out["exploratory_parent"] = bool(out.get("exploratory_parent", False) or loser.get("exploratory_parent", False))
    out["links"] = _union_list(list(out.get("links", []) or []) + list(loser.get("links", []) or []), limit=24)
    out["required_next"] = _union_list(list(out.get("required_next", []) or []) + list(loser.get("required_next", []) or []), limit=24)
    defs = dict(loser.get("definitions", {}) or {})
    defs.update(dict(out.get("definitions", {}) or {}))
    out["definitions"] = defs
    repair_log = dict(loser.get("repair_log", {}) or {})
    repair_log.update(dict(out.get("repair_log", {}) or {}))
    out["repair_log"] = repair_log
    out["source_turn"] = max(int(out.get("source_turn", 0) or 0), int(loser.get("source_turn", 0) or 0))
    if not out.get("remark") and loser.get("remark"):
        out["remark"] = loser["remark"]
    if loser.get("parent_equation") and out.get("parent_equation") and loser.get("parent_equation") != out.get("parent_equation"):
        notes = list(out.get("required_next", []) or [])
        notes.append(f"merge_alt_parent:{loser.get('parent_equation')}")
        out["required_next"] = _union_list(notes, limit=24)
    return out


def _merge_equation_lists(shared_a: dict[str, Any], shared_b: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    all_entries = []
    for store in ("approved_equations", "partial_equations"):
        for row in list(shared_a.get(store, []) or []):
            all_entries.append((dict(row), shared_a))
        for row in list(shared_b.get(store, []) or []):
            all_entries.append((dict(row), shared_b))

    winners: dict[str, dict[str, Any]] = {}
    nearby_structures: set[str] = set()
    exact_dupes_removed = 0
    structure_families = 0

    for entry, source_shared in all_entries:
        eq_key = _normalized_equation(entry.get("equation", ""))
        if not eq_key:
            continue
        sig = _structure_signature(entry.get("equation", ""))
        if sig in nearby_structures and eq_key not in winners:
            structure_families += 1
        nearby_structures.add(sig)
        current = winners.get(eq_key)
        if current is None:
            winners[eq_key] = dict(entry)
            continue
        exact_dupes_removed += 1
        current_score = _equation_memory_score(current, shared_a)
        new_score = _equation_memory_score(entry, source_shared)
        if new_score > current_score:
            winners[eq_key] = _merge_equation_entry(dict(entry), current)
        else:
            winners[eq_key] = _merge_equation_entry(current, entry)

    approved: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for row in winners.values():
        if bool(row.get("approved", False)):
            approved.append(row)
        else:
            partial.append(row)
    approved.sort(key=lambda row: int(row.get("source_turn", 0) or 0))
    partial.sort(key=lambda row: int(row.get("source_turn", 0) or 0))
    return approved, partial, exact_dupes_removed, structure_families


def merge_shared_memory_dicts(shared_a: dict[str, Any], shared_b: dict[str, Any], session_a: str, session_b: str) -> tuple[dict[str, Any], dict[str, Any]]:
    blank = SharedResearchMemory(_new_session_dir(get_workspace_dir()))._blank()
    merged = dict(blank)
    merged.update(shared_a or {})

    variable_dupes_removed = 0
    variables_store: dict[str, dict[str, Any]] = {}
    approved_names: set[str] = set()
    for approved_flag, store_name in [(True, "approved_variables"), (False, "candidate_variables")]:
        for source in [shared_a, shared_b]:
            for name, payload in (source.get(store_name, {}) or {}).items():
                key = _normalized_symbol(name)
                if not key:
                    continue
                clean = dict(payload or {})
                clean.setdefault("name", name)
                clean["approved"] = bool(clean.get("approved", False) or approved_flag)
                existing = variables_store.get(key)
                if existing is None:
                    variables_store[key] = clean
                else:
                    variable_dupes_removed += 1
                    variables_store[key] = _merge_variable_payload(existing, clean)
                if approved_flag:
                    approved_names.add(key)

    merged["approved_variables"] = {}
    merged["candidate_variables"] = {}
    for key, payload in variables_store.items():
        name = payload.get("name") or payload.get("variable_name") or key
        if key in approved_names or payload.get("approved"):
            payload["approved"] = True
            payload["status"] = payload.get("status") or "approved"
            merged["approved_variables"][name] = payload
        else:
            payload["status"] = payload.get("status") or "candidate"
            merged["candidate_variables"][name] = payload

    approved_eq, partial_eq, exact_dupes_removed, structure_families = _merge_equation_lists(shared_a, shared_b)
    merged["approved_equations"] = approved_eq
    merged["partial_equations"] = partial_eq

    for field, limit in [
        ("rejected_fragments", 200),
        ("approved_links", 120),
        ("priority_variables", 40),
        ("recent_links", 120),
        ("recent_remarks", 120),
        ("final_validations", 120),
        ("debate_summaries", 120),
        ("stagnation_events", 120),
    ]:
        merged[field] = _union_list(list(shared_a.get(field, []) or []) + list(shared_b.get(field, []) or []), limit=limit)

    for field in [
        "equation_scores",
        "variable_scores",
        "equation_usage_count",
        "variable_usage_count",
        "equation_failures",
        "variable_failures",
    ]:
        merged[field] = _sum_dict(dict(shared_a.get(field, {}) or {}), dict(shared_b.get(field, {}) or {}))

    merged["pending_variables"] = dict(shared_a.get("pending_variables", {}) or {})
    merged["pending_variables"].update(dict(shared_b.get("pending_variables", {}) or {}))

    merged["turn_metrics"] = _union_list(list(shared_a.get("turn_metrics", []) or []) + list(shared_b.get("turn_metrics", []) or []), limit=200)
    merged["repair_logs"] = _union_list(list(shared_a.get("repair_logs", []) or []) + list(shared_b.get("repair_logs", []) or []), limit=120)
    merged["repair_patterns"] = _union_list(list(shared_a.get("repair_patterns", []) or []) + list(shared_b.get("repair_patterns", []) or []), limit=80)

    mutation_seen: set[tuple[str, str, str]] = set()
    mutation_rows: list[dict[str, Any]] = []
    for row in list(shared_a.get("mutation_history", []) or []) + list(shared_b.get("mutation_history", []) or []):
        clean = dict(row or {})
        key = (
            str(clean.get("parent_equation", "") or ""),
            str(clean.get("child_equation", "") or clean.get("equation", "") or ""),
            str(clean.get("decision", "") or clean.get("memory_decision", "") or ""),
        )
        if key in mutation_seen:
            continue
        mutation_seen.add(key)
        mutation_rows.append(clean)
    merged["mutation_history"] = mutation_rows[-120:]

    last_var_a = dict(shared_a.get("last_validated_variable", {}) or {})
    last_var_b = dict(shared_b.get("last_validated_variable", {}) or {})
    merged["last_validated_variable"] = last_var_a if int(last_var_a.get("source_turn", 0) or 0) >= int(last_var_b.get("source_turn", 0) or 0) else last_var_b

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_sessions": [session_a, session_b],
        "variables_final": len(merged["approved_variables"]) + len(merged["candidate_variables"]),
        "equations_final": len(merged["approved_equations"]) + len(merged["partial_equations"]),
        "mutation_links_final": len(merged["mutation_history"]),
        "variable_duplicates_removed": variable_dupes_removed,
        "equation_duplicates_removed": exact_dupes_removed,
        "structure_families_detected": structure_families,
    }
    history = list(shared_a.get("merge_history", []) or []) + list(shared_b.get("merge_history", []) or [])
    history.append(summary)
    merged["last_merge_summary"] = summary
    merged["merge_history"] = history[-30:]
    return merged, summary


def _merge_memory_store_files(session_a: Path, session_b: Path, target: Path) -> dict[str, int]:
    stats = {
        "variables_memory": 0,
        "validations_memory": 0,
        "roles_memory": 0,
        "symbolic_memory": 0,
    }

    # variables_memory.json
    vars_a = _load_json(session_a / "variables_memory.json", {})
    vars_b = _load_json(session_b / "variables_memory.json", {})
    merged_vars: dict[str, dict[str, Any]] = {}
    for source in [vars_a, vars_b]:
        for name, payload in (source or {}).items():
            key = _normalized_symbol(name)
            clean = dict(payload or {})
            clean.setdefault("name", name)
            if key in merged_vars:
                stats["variables_memory"] += 1
                merged_vars[key] = _merge_variable_payload(merged_vars[key], clean)
            else:
                merged_vars[key] = clean
    _save_json(target / "variables_memory.json", {row.get("name") or key: row for key, row in merged_vars.items()})

    # validations_memory.json
    val_a = _load_json(session_a / "validations_memory.json", [])
    val_b = _load_json(session_b / "validations_memory.json", [])
    val_seen: set[tuple[Any, ...]] = set()
    merged_validations: list[dict[str, Any]] = []
    for row in list(val_a or []) + list(val_b or []):
        clean = dict(row or {})
        key = (
            clean.get("element_name"),
            clean.get("element_type"),
            clean.get("turn"),
            clean.get("status"),
            clean.get("reason"),
            clean.get("correction"),
        )
        if key in val_seen:
            stats["validations_memory"] += 1
            continue
        val_seen.add(key)
        merged_validations.append(clean)
    _save_json(target / "validations_memory.json", merged_validations)

    # roles_memory.json
    roles_a = _load_json(session_a / "roles_memory.json", {})
    roles_b = _load_json(session_b / "roles_memory.json", {})
    merged_roles: dict[str, dict[str, Any]] = {}
    for source in [roles_a, roles_b]:
        for name, payload in (source or {}).items():
            key = _normalized_symbol(name)
            clean = dict(payload or {})
            clean.setdefault("variable_name", name)
            if key in merged_roles:
                stats["roles_memory"] += 1
                prev = merged_roles[key]
                prev_turn = int(prev.get("turn", 0) or 0)
                new_turn = int(clean.get("turn", 0) or 0)
                merged_roles[key] = clean if new_turn >= prev_turn else _merge_variable_payload(prev, clean)
            else:
                merged_roles[key] = clean
    _save_json(target / "roles_memory.json", {row.get("variable_name") or key: row for key, row in merged_roles.items()})

    # symbolic_memory.json
    sym_a = _load_json(session_a / "symbolic_memory.json", [])
    sym_b = _load_json(session_b / "symbolic_memory.json", [])
    sym_seen: set[str] = set()
    merged_symbolic: list[dict[str, Any]] = []
    for row in list(sym_a or []) + list(sym_b or []):
        clean = dict(row or {})
        key = json.dumps(
            {
                "turn": clean.get("turn"),
                "source_agent": clean.get("source_agent"),
                "source_equation": clean.get("source_equation"),
                "correspondences": clean.get("correspondences"),
                "mechanism": clean.get("mechanism"),
                "principle_active": clean.get("principle_active"),
                "principle_passive": clean.get("principle_passive"),
                "operation": clean.get("operation"),
                "observable_sign": clean.get("observable_sign"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if key in sym_seen:
            stats["symbolic_memory"] += 1
            continue
        sym_seen.add(key)
        merged_symbolic.append(clean)
    _save_json(target / "symbolic_memory.json", merged_symbolic[-60:])
    return stats


def merge_full_sessions(session_a_name: str, session_b_name: str, *, target_session_name: str | None = None, create_new_target: bool = True) -> Path:
    base_dir = get_workspace_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    total_steps = 7

    _step(1, total_steps, "validation des sessions source")
    session_a = resolve_session_dir(base_dir, session_name=session_a_name, strict=True)
    session_b = resolve_session_dir(base_dir, session_name=session_b_name, strict=True)
    if session_a.name == session_b.name:
        raise ValueError("Les deux sessions à fusionner doivent être différentes.")
    _step_done(1, total_steps, f"sources = {session_a.name} + {session_b.name}")

    _step(2, total_steps, "résolution de la session cible")
    if create_new_target:
        target = _new_session_dir(base_dir)
    else:
        if not target_session_name:
            raise ValueError("Une session cible doit être fournie si on ne crée pas une nouvelle session.")
        target = resolve_session_dir(base_dir, session_name=target_session_name, strict=True)
    target.mkdir(parents=True, exist_ok=True)
    _step_done(2, total_steps, f"cible = {target.name}")

    _step(3, total_steps, "chargement des shared memories")
    shared_a = _load_json(session_a / "shared_research_memory.json", {})
    shared_b = _load_json(session_b / "shared_research_memory.json", {})
    shared_a, recovered_a = _enrich_shared_with_log_equations(session_a, shared_a)
    shared_b, recovered_b = _enrich_shared_with_log_equations(session_b, shared_b)
    _step_done(3, total_steps, f"shared memories chargées | équations récupérées depuis logs: {recovered_a} + {recovered_b}")

    _step(4, total_steps, "fusion de shared_research_memory.json")
    merged_shared, shared_summary = merge_shared_memory_dicts(shared_a, shared_b, session_a.name, session_b.name)
    shared_summary["recovered_equations_from_logs"] = recovered_a + recovered_b
    _step_done(4, total_steps, "shared memory fusionnée")

    _step(5, total_steps, "fusion des mémoires variables / validations / rôles / symbolique")
    memstore_stats = _merge_memory_store_files(session_a, session_b, target)
    _step_done(5, total_steps, "mémoires secondaires fusionnées")

    _step(6, total_steps, "écriture des fichiers finaux")
    merged_shared["last_merge_summary"].update(memstore_stats)
    merged_shared["last_merge_summary"]["target_session"] = target.name
    _save_json(target / "shared_research_memory.json", merged_shared)
    for fname, default in [
        ("variables_memory.json", {}),
        ("validations_memory.json", []),
        ("roles_memory.json", {}),
        ("symbolic_memory.json", []),
    ]:
        path = target / fname
        if not path.exists():
            _save_json(path, default)
    _step_done(6, total_steps, "fichiers écrits")

    _step(7, total_steps, "résumé final")
    print(f"[MERGE] Sessions fusionnées : {session_a.name} + {session_b.name}")
    print(f"[MERGE] Cible : {target}")
    print(f"[MERGE] Variables finales : {shared_summary['variables_final']} | doublons retirés : {shared_summary['variable_duplicates_removed']}")
    print(f"[MERGE] Équations finales : {shared_summary['equations_final']} | doublons retirés : {shared_summary['equation_duplicates_removed']} | récupérées depuis logs : {shared_summary.get('recovered_equations_from_logs', 0)}")
    print(f"[MERGE] Liens de mutation : {shared_summary['mutation_links_final']}")
    print(f"[MERGE] Fichiers mémoire fusionnés : variables={memstore_stats['variables_memory']} validations={memstore_stats['validations_memory']} rôles={memstore_stats['roles_memory']} symbolique={memstore_stats['symbolic_memory']}")
    _step_done(7, total_steps, "merge terminé")
    return target


# ---------- Run modes ----------


def run_repair(turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False, target_equation: str | None = None) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    cfg.target_equation = str(target_equation or "").strip()
    turns = max(1, turns)
    print(f"[MODE] Repair | turns={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    if cfg.target_equation:
        print(f"[TARGET] {cfg.target_equation}")
    _step(1, 2, "validation repair")
    ok, reason = _repair_ready(cfg)
    if not ok:
        print(f"[INFO] Repair bloqué: {reason}")
        return
    _step_done(1, 2, "validation repair")
    _step(2, 2, "phase repair")
    RepairEquationOrchestrator(cfg).run(turns=turns)
    _step_done(2, 2, "phase repair")


def run_lineages(limit: int = 5, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    limit = max(1, limit)
    print(f"[MODE] Lineages | limit={limit}")
    print(f"[SESSION] {cfg.session_dir}")
    _step(1, 1, "construction du rapport de lignée")
    _print_lineages(cfg, limit=limit)
    _step_done(1, 1, "construction du rapport de lignée")


def run_status(*, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    print("[MODE] Status")
    print(f"[SESSION] {cfg.session_dir}")
    shared = SharedResearchMemory(cfg.session_dir)
    snap = shared.get_observability_snapshot()
    latest_eq = snap.get("latest_equation", {}) or {}
    latest_var = snap.get("latest_variable", {}) or {}
    mut_ready = snap.get("mutation_ready", (False, ""))
    rep_ready = snap.get("repair_ready", (False, ""))
    print("=== SNAPSHOT ===")
    print(f"Variable récente : {latest_var.get('symbol', '-')}")
    print(f"Équation récente : {latest_eq.get('equation', '-')}")
    print(f"Mutation : {'OK' if mut_ready[0] else 'BLOQUÉE'} | {mut_ready[1]}")
    print(f"Repair   : {'OK' if rep_ready[0] else 'BLOQUÉE'} | {rep_ready[1]}")

    data = shared.data
    approved_eq = list(data.get("approved_equations", []) or [])
    partial_eq = list(data.get("partial_equations", []) or [])
    mutation_history = list(data.get("mutation_history", []) or [])
    eq_nodes = approved_eq + partial_eq
    parent_count = sum(1 for row in eq_nodes if row.get("parent_equation"))
    root_count = sum(1 for row in eq_nodes if not row.get("parent_equation"))
    eq_set = {_normalized_equation(row.get("equation", "")) for row in eq_nodes}
    parent_set = {_normalized_equation(row.get("parent_equation", "")) for row in eq_nodes if row.get("parent_equation")}
    leaf_count = sum(1 for row in eq_nodes if _normalized_equation(row.get("equation", "")) not in parent_set)
    print("=== LINEAGE ===")
    print(f"Nœuds totaux        : {len(eq_nodes)}")
    print(f"Nœuds avec parent   : {parent_count}")
    print(f"Racines / isolées   : {root_count}")
    print(f"Feuilles            : {leaf_count}")
    print(f"Liens de mutation   : {len(mutation_history)}")

    merge_summary = dict(data.get("last_merge_summary", {}) or {})
    if merge_summary:
        print("=== DERNIER MERGE ===")
        print(f"Sources             : {', '.join(merge_summary.get('source_sessions', []))}")
        print(f"Cible               : {merge_summary.get('target_session', '-')}")
        print(f"Variables finales   : {merge_summary.get('variables_final', 0)} | doublons retirés : {merge_summary.get('variable_duplicates_removed', 0)}")
        print(f"Équations finales   : {merge_summary.get('equations_final', 0)} | doublons retirés : {merge_summary.get('equation_duplicates_removed', 0)}")
        print(f"Familles proches    : {merge_summary.get('structure_families_detected', 0)}")
        print(f"Mutations finales   : {merge_summary.get('mutation_links_final', 0)}")
        print(f"MemoryStore dups    : variables={merge_summary.get('variables_memory', 0)} validations={merge_summary.get('validations_memory', 0)} rôles={merge_summary.get('roles_memory', 0)} symbolique={merge_summary.get('symbolic_memory', 0)}")
    _step_done(1, 2, "lecture du snapshot")
    _step(2, 2, "rapport de lignée")
    _print_lineages(cfg, limit=3)
    _step_done(2, 2, "rapport de lignée")



def _equation_test_symbols(equation: str) -> list[str]:
    raw = re.findall(r"[A-Za-zÀ-ÿ_Δ][A-Za-zÀ-ÿ0-9_Δ]*", str(equation or ""))
    blocked = {"equation", "equationtest", "exp", "log", "ln", "sin", "cos", "tan", "sqrt", "abs", "min", "max"}
    out: list[str] = []
    seen: set[str] = set()
    for token in raw:
        key = token.strip()
        if not key or key.lower() in blocked:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _lookup_variable_info(shared: SharedResearchMemory, symbol: str) -> dict[str, Any]:
    for bucket in (shared.data.get("approved_variables", {}) or {}, shared.data.get("candidate_variables", {}) or {}):
        for key, value in bucket.items():
            if _normalized_symbol(key) == _normalized_symbol(symbol):
                return dict(value or {})
    return {}


def _build_demo_calculation(equation: str) -> dict[str, Any]:
    eq = str(equation or "").strip()
    if "=" not in eq:
        return {"ok": False, "reason": "No '=' sign available for a demonstration."}
    lhs, rhs = eq.split("=", 1)
    lhs = lhs.strip()
    rhs = rhs.strip()
    expr = rhs.replace("^", "**").replace("·", "*").replace("×", "*").replace("−", "-")
    symbols = _equation_test_symbols(expr)
    values: dict[str, float] = {}
    seed = 2.0
    for sym in symbols:
        values[sym] = seed
        seed += 1.0
    expr_num = expr
    for sym in sorted(values.keys(), key=len, reverse=True):
        expr_num = re.sub(rf"(?<![A-Za-zÀ-ÿ0-9_Δ]){re.escape(sym)}(?![A-Za-zÀ-ÿ0-9_Δ])", str(values[sym]), expr_num)
    safe_env = {name: getattr(math, name) for name in ["exp", "log", "sqrt", "sin", "cos", "tan", "pi", "e"] if hasattr(math, name)}
    safe_env.update({"abs": abs, "min": min, "max": max})
    try:
        result = _safe_eval_math(expr_num, safe_env)
        return {"ok": True, "lhs": lhs, "rhs": rhs, "values": values, "expr_num": expr_num, "result": result}
    except Exception as exc:
        return {"ok": False, "lhs": lhs, "rhs": rhs, "values": values, "expr_num": expr_num, "reason": f"Illustrative substitution prepared, but evaluation failed: {type(exc).__name__}: {exc}"}


def _equation_test_report(cfg: RuntimeConfig, shared: SharedResearchMemory, payload: dict[str, Any]) -> str:
    equation = str(payload.get("equation", "") or "").strip()
    defs = dict(payload.get("definitions", {}) or {})
    links = list(payload.get("links", []) or [])
    mechanism = str(payload.get("mechanism", "") or "")
    experiment = str(payload.get("experiment", "") or "")
    parent = str(payload.get("parent_equation", "") or "")
    architecture = str(payload.get("architecture", "") or "")
    law_type = str(payload.get("law_type", "") or "")
    obj = str(payload.get("object_calculated", "") or "")
    approved = bool(payload.get("approved", False) or str(payload.get("status", "")).lower() == "approved")
    stable_parent = bool(payload.get("stable_parent", False))
    repair_required = bool(payload.get("repair_required", False))
    fallback_used = bool(payload.get("fallback_used", False))
    can_mutate, mutate_reason = shared.can_start_mutation_for_equation(equation)
    can_repair, repair_reason = shared.can_start_repair_for_equation(equation)
    lineage = shared.get_equation_lineage(equation)
    symbols = _equation_test_symbols(equation)
    symbol_lines = []
    for sym in symbols[:10]:
        info = _lookup_variable_info(shared, sym)
        definition = str(defs.get(sym, "") or info.get("definition", "") or "definition missing")
        unit = str(info.get("unit", "") or "")
        measure = str(info.get("measure", "") or "")
        tail = []
        if unit:
            tail.append(f"unit={unit}")
        if measure:
            tail.append(f"measure={measure}")
        suffix = f" ({', '.join(tail)})" if tail else ""
        symbol_lines.append(f"- {sym}: {definition}{suffix}")
    demo = _build_demo_calculation(equation)
    lhs = equation.split("=", 1)[0].strip() if "=" in equation else equation
    verdict = "READY FOR MUTATION" if can_mutate else ("NEEDS REPAIR" if can_repair else "REVIEW MANUALLY")
    lines: list[str] = []
    lines.append("=== EQUATION TEST | MULTI-AGENT DEBATE ===")
    lines.append(f"Session: {cfg.session_dir.name}")
    lines.append(f"Equation: {equation}")
    lines.append(f"Verdict: {verdict}")
    lines.append("")
    lines.append("[Aurelius | mathematical structure]")
    lines.append(f"- Target quantity: {obj or lhs or 'missing'}")
    lines.append(f"- Architecture: {architecture or 'missing'}")
    lines.append(f"- Law type: {law_type or 'missing'}")
    lines.append(f"- Parent equation: {parent or 'none'}")
    if '=' in equation:
        rhs = equation.split('=', 1)[1].strip()
        lines.append(f"- Demonstration path: compute RHS '{rhs}' then compare with LHS '{lhs}'.")
    else:
        lines.append("- Demonstration path: missing explicit equality, so algebraic proof is incomplete.")
    lines.append("")
    lines.append("[Basilide | mechanism and experiment]")
    lines.append(f"- Mechanism: {mechanism or 'missing'}")
    lines.append(f"- Experiment: {experiment or 'missing'}")
    lines.append(f"- Linked observations: {len(links)}")
    if symbol_lines:
        lines.append("- Variable grounding:")
        lines.extend(symbol_lines)
    else:
        lines.append("- Variable grounding: missing")
    lines.append("")
    lines.append("[Chymicus | critique]")
    critiques = []
    if not approved:
        critiques.append("equation is not approved")
    if repair_required:
        critiques.append("equation is marked for repair")
    if fallback_used:
        critiques.append("equation comes from fallback output")
    if not mechanism:
        critiques.append("mechanism is missing")
    if not experiment:
        critiques.append("experiment is missing")
    if not defs and not symbol_lines:
        critiques.append("definitions are missing")
    if not critiques:
        critiques.append("no major blocker detected in the stored payload")
    for item in critiques:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("[Sentinelle | validation]")
    lines.append(f"- Approved: {approved}")
    lines.append(f"- Stable parent: {stable_parent}")
    lines.append(f"- Repair required: {repair_required}")
    lines.append(f"- Mutation readiness: {can_mutate} ({mutate_reason})")
    lines.append(f"- Repair readiness: {can_repair} ({repair_reason})")
    lines.append(f"- Lineage depth: {len(lineage)}")
    lines.append("")
    lines.append("[Hermes | synthesis]")
    if parent:
        lines.append("- The equation belongs to a lineage and can be interpreted as a branch of an existing family.")
    else:
        lines.append("- The equation is isolated in lineage memory; debate should focus on anchoring it to a parent or test result.")
    lines.append(f"- Scientific reading: compute {lhs or 'the target'} from the coupled variables, then validate against a measurable observation.")
    lines.append("")
    lines.append("[Demonstration | illustrative calculation]")
    if demo.get("ok"):
        values = ", ".join(f"{k}={v}" for k, v in (demo.get("values", {}) or {}).items()) or "no symbolic substitution needed"
        lines.append(f"- Substitution set: {values}")
        lines.append(f"- Numeric RHS: {demo.get('expr_num', '')}")
        lines.append(f"- Result: {demo.get('lhs', lhs)} = {demo.get('result')}")
        lines.append("- Note: this is an illustrative computation with synthetic values to show how the equation resolves.")
    else:
        if demo.get("values"):
            values = ", ".join(f"{k}={v}" for k, v in (demo.get("values", {}) or {}).items())
            lines.append(f"- Prepared substitution set: {values}")
            lines.append(f"- Numeric RHS attempt: {demo.get('expr_num', '')}")
        lines.append(f"- {demo.get('reason', 'No calculation available.')}" )
    lines.append("")
    lines.append("[Debate conclusion]")
    if can_mutate:
        lines.append("- Consensus: the equation is coherent enough to serve as a mutation parent.")
    elif can_repair:
        lines.append("- Consensus: the equation should go through repair before any new mutation.")
    else:
        lines.append("- Consensus: review manually and enrich the equation with mechanism, experiment, or validation data.")
    return "\n".join(lines)


def run_equation_test(*, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False, target_equation: str | None = None) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    raw_equation = str(target_equation or "").strip()
    equation = normalize_target_equation(raw_equation)
    if not equation:
        raise ValueError("equation-test requires --target-equation")
    shared = SharedResearchMemory(cfg.session_dir)
    payload = shared.get_equation_payload(equation) or {}
    if not payload and raw_equation and raw_equation != equation:
        payload = shared.get_equation_payload(raw_equation) or {}
    if not payload:
        raise ValueError(f"Target equation not found in selected session: {equation}")
    equation = str(payload.get("equation", "") or equation).strip()
    print("[MODE] Equation Test")
    print(f"[SESSION] {cfg.session_dir}")
    print(f"[TARGET] {equation}")
    _step(1, 3, "load target equation")
    _step_done(1, 3, "load target equation")
    _step(2, 3, "run multi-agent debate")
    debate = TestDebateOrchestrator(cfg, payload)
    debate.run(turns=1)
    report = debate.render_report()
    report_path = cfg.session_dir / "equation_test_report.txt"
    report_path.write_text(report, encoding="utf-8")
    _step_done(2, 3, "run multi-agent debate")
    _step(3, 3, "publish report")
    print(report, end="" if report.endswith("\n") else "\n")
    print(f"[REPORT] Saved to {report_path.name}")
    _step_done(3, 3, "publish report")


def run_variables(turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    turns = max(1, turns)
    print(f"[MODE] Variables | turns={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    _step(1, 1, "phase variables")
    VariableDebateOrchestrator(cfg).run(turns=turns)
    _step_done(1, 1, "phase variables")


def run_equations(turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    turns = max(1, turns)
    print(f"[MODE] Equations | turns={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    _step(1, 1, "phase équations")
    EquationDebateOrchestrator(cfg).run(turns=turns)
    _step_done(1, 1, "phase équations")


def run_mutation(turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False, target_equation: str | None = None) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    cfg.target_equation = str(target_equation or "").strip()
    turns = max(1, turns)
    print(f"[MODE] Mutation | turns={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    if cfg.target_equation:
        print(f"[TARGET] {cfg.target_equation}")
    _step(1, 2, "validation mutation")
    ok, reason = _mutation_ready(cfg)
    if not ok:
        print(f"[INFO] Mutation bloquée: {reason}")
        return
    _step_done(1, 2, "validation mutation")
    _step(2, 2, "phase mutation")
    MutationEquationOrchestrator(cfg).run(turns=turns)
    _step_done(2, 2, "phase mutation")




def _pick_auto_repair_target(cfg: RuntimeConfig) -> dict[str, Any] | None:
    shared = SharedResearchMemory(cfg.session_dir)
    candidates = []
    for row in shared.get_all_equation_entries():
        needs_repair, _reason = shared.can_start_repair_for_equation(str(row.get("equation", "") or ""))
        if not needs_repair:
            continue
        score = 0
        score += 100 if bool(row.get("repair_required", False)) else 0
        score += 35 if bool(row.get("fallback_used", False)) else 0
        score += 25 if str(row.get("status", "")).lower() == "partial" else 0
        score += min(20, int((SharedResearchMemory(cfg.session_dir).data.get("equation_failures", {}) or {}).get(str(row.get("equation", "")).strip(), 0) or 0) * 5)
        score += int(row.get("source_turn", 0) or 0)
        candidates.append((score, dict(row)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]




def _is_placeholder_like_equation(eq: str) -> bool:
    text = str(eq or "").strip().lower()
    if not text or "=" not in text:
        return True

    rhs = text.split("=", 1)[1].strip()

    simple_placeholders = {
        "k_eff", "q_eff", "x_eff", "j_eff", "c_eff", "d_eff", "a_eff", "tau_eff", "τ_eff",
        "k", "q", "x", "j", "c", "d", "a", "tau", "τ",
    }

    if rhs in simple_placeholders:
        return True

    if rhs.endswith("_eff") and all(op not in rhs for op in ["+", "-", "*", "/", "(", ")"]):
        return True

    return False


def _count_recent_mutations_for_parent(shared, equation: str) -> int:
    eq = str(equation or "").strip()
    count = 0
    for row in shared.data.get("mutation_history", []) or []:
        parent = str(row.get("parent_equation", "") or "").strip()
        if parent == eq:
            count += 1
    return count


def _count_recent_repairs_for_equation(shared, equation: str) -> int:
    eq = str(equation or "").strip()
    count = 0
    for row in shared.data.get("repair_logs", []) or []:
        target = str(row.get("target_equation", "") or "").strip()
        if target == eq:
            count += 1
    return count


def _mutation_score(shared, row: dict) -> tuple[int, list[str]]:
    eq = str(row.get("equation", "") or "").strip()
    score = 0
    reasons: list[str] = []

    approved = bool(row.get("approved", False))
    stable_parent = bool(row.get("stable_parent", False))
    fallback_used = bool(row.get("fallback_used", False))
    repair_required = bool(row.get("repair_required", False))
    status = str(row.get("status", "") or "").strip().lower()
    source_turn = int(row.get("source_turn", 0) or 0)

    if approved:
        score += 120
        reasons.append("approved")
    if stable_parent:
        score += 60
        reasons.append("stable_parent")
    if status == "partial":
        score -= 80
        reasons.append("partial")
    if fallback_used:
        score -= 120
        reasons.append("fallback_used")
    if repair_required:
        score -= 120
        reasons.append("repair_required")

    if _is_placeholder_like_equation(eq):
        score -= 140
        reasons.append("placeholder_like")

    repair_count = _count_recent_repairs_for_equation(shared, eq)
    if repair_count > 0:
        score -= 25 * repair_count
        reasons.append(f"recent_repairs={repair_count}")

    mutation_count = _count_recent_mutations_for_parent(shared, eq)
    if mutation_count > 0:
        score -= 35 * mutation_count
        reasons.append(f"recent_mutations={mutation_count}")

    score += min(source_turn, 40)

    if any(op in eq for op in ["(", "*", "/", "+", "-"]):
        score += 15
        reasons.append("structural_complexity")

    return score, reasons

def _pick_auto_mutation_target(cfg: RuntimeConfig) -> dict[str, Any] | None:
    shared = SharedResearchMemory(cfg.session_dir)
    candidates = []
    for row in shared.get_all_equation_entries():
        eq = str(row.get("equation", "") or "").strip()
        ok, _reason = shared.can_start_mutation_for_equation(eq)
        if not ok:
            continue
        score, reasons = _mutation_score(shared, row)
        enriched = dict(row)
        enriched["_mutation_score"] = score
        enriched["_mutation_reasons"] = reasons
        candidates.append((score, enriched))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]



def _row_mutation_block_reason(shared: SharedResearchMemory, row: dict[str, Any]) -> str:
    eq = str(row.get("equation", "") or "").strip()
    if not eq:
        return "empty_equation"
    if bool(row.get("fallback_used", False)):
        return "fallback_parent"
    if bool(row.get("repair_required", False)):
        return "needs_equation_repair"
    if _is_placeholder_like_equation(eq):
        return "placeholder_parent"
    ok, reason = shared.can_start_mutation_for_equation(eq)
    return "ok" if ok else str(reason or "blocked")


def _upgrade_sterile_equation(eq: str) -> str:
    text = normalize_target_equation(eq)
    if text == "Ndot = J":
        return "Ndot = (D_eff * ΔC / L) * A"
    if text == "Ndot = J * A":
        return "Ndot = (D_eff * ΔC / L) * A"
    if text == "Ndot = k_eff":
        return "Ndot = (k_eff * ΔC / L) * A"
    if text == "Ndot = k_eff * A":
        return "Ndot = (k_eff * ΔC / L) * A"
    return text

def _force_enrich_parent_equation(eq: str) -> str:
    text = _upgrade_sterile_equation(eq)
    if not text or "=" not in text:
        return text
    lhs, rhs = [part.strip() for part in text.split("=", 1)]
    enriched_rhs = rhs
    if "k_eff" in enriched_rhs and "ΔC" not in enriched_rhs:
        enriched_rhs = enriched_rhs.replace("k_eff", "(k_eff * ΔC / L)", 1)
    elif "x_eff" in enriched_rhs:
        enriched_rhs = enriched_rhs.replace("x_eff", "(D_eff * ΔC / L)", 1)
    elif all(tok not in enriched_rhs for tok in ["ΔC", "J", "D_eff"]):
        enriched_rhs = f"({enriched_rhs}) * ΔC / L"
    if "/ (1 + R)" not in enriched_rhs and "R" in enriched_rhs and "/(1+R)" not in enriched_rhs.replace(" ", ""):
        enriched_rhs = f"({enriched_rhs}) / (1 + R)"
    enriched = f"{lhs} = {enriched_rhs}"
    return enriched if enriched != text else text


def _persist_consolidated_parent_equation(cfg: RuntimeConfig, original_eq: str, *, reason: str = "placeholder_parent") -> tuple[bool, str]:
    original = normalize_target_equation(original_eq)
    if not original:
        return False, "empty_parent"
    enriched = _force_enrich_parent_equation(original)
    if not enriched or enriched == original:
        return False, "no_structural_change"

    shared = SharedResearchMemory(cfg.session_dir)
    payload = shared.get_equation_payload(original) or {}
    shared.add_equation(
        SharedEquation(
            equation=enriched,
            approved=True,
            status="approved",
            fallback_used=False,
            stable_parent=True,
            repair_required=False,
            memory_decision="consolidated_parent",
            source_turn=int(payload.get("source_turn", 0) or 0),
            source_agent="consolidate_mutation",
            validation_summary=f"Consolidated from parent blocked for mutation ({reason}).",
            mechanism=str(payload.get("mechanism", "") or "consolidation"),
            experiment=str(payload.get("experiment", "") or ""),
            links=list(payload.get("links", []) or []),
            remark=f"Parent consolidated before mutation from: {original}",
            required_next=["mutation"],
            object_calculated=str(payload.get("object_calculated", "") or payload.get("object", "") or payload.get("objet", "") or ""),
            law_type=str(payload.get("law_type", "") or ""),
            architecture=str(payload.get("architecture", "") or "consolidated parent"),
            parent_equation=original,
            parent_variable=str(payload.get("parent_variable", "") or payload.get("variable", "") or ""),
            exploratory_parent=False,
        )
    )
    try:
        if hasattr(shared, "clear_sterile_consolidation_state"):
            shared.clear_sterile_consolidation_state(original)
        if hasattr(shared, "add_consolidation_log"):
            shared.add_consolidation_log(original, enriched, reason=reason)
    except Exception:
        pass
    try:
        shared.record_mutation(
            parent_equation=original,
            child_equation=enriched,
            decision="consolidated_parent",
            mechanism="consolidation",
            validation_summary=f"Consolidated from blocked parent ({reason}).",
            source_turn=int(payload.get("source_turn", 0) or 0),
        )
    except Exception:
        pass
    return True, enriched


def _consolidate_mutation_decision(cfg: RuntimeConfig) -> dict[str, str]:
    shared = SharedResearchMemory(cfg.session_dir)
    repair_decision = shared.choose_next_repair_action() if hasattr(shared, "choose_next_repair_action") else {"kind": "none", "target": "", "reason": ""}
    if str(repair_decision.get("kind", "") or "").strip() == "variable":
        target = str(repair_decision.get("target", "") or "").strip()
        if target:
            return {"kind": "variable", "target": target, "reason": str(repair_decision.get("reason", "") or "blocked_by_unvalidated_variables")}
    candidates: list[tuple[int, dict[str, str]]] = []
    for row in shared.get_all_equation_entries():
        eq = str(row.get("equation", "") or "").strip()
        if not eq:
            continue
        score, reasons = _mutation_score(shared, row)
        block_reason = _row_mutation_block_reason(shared, row)
        if block_reason == "ok":
            continue
        recent_valid = hasattr(shared, "was_recently_validated") and shared.was_recently_validated(eq, window=4)
        recent_cons = hasattr(shared, "was_recently_consolidated") and shared.was_recently_consolidated(eq, window=6)
        block_reason_l = block_reason.lower()
        if any(tok in block_reason_l for tok in ["fallback", "placeholder"]):
            if recent_cons:
                continue
            penalty = 220 if _is_placeholder_like_equation(eq) else 0
            candidates.append((score + 300 - penalty, {"kind": "consolidate", "target": eq, "reason": block_reason}))
        elif any(tok in block_reason_l for tok in ["variable", "non valid", "unvalidated"]):
            if str(repair_decision.get("kind", "") or "").strip() == "variable":
                target = str(repair_decision.get("target", "") or "").strip()
                if target:
                    candidates.append((score + 260, {"kind": "variable", "target": target, "reason": "blocked_by_unvalidated_variables", "equation": eq}))
        elif any(tok in block_reason_l for tok in ["repair", "partielle", "partial", "non approuv", "non stable"]):
            if recent_valid:
                continue
            candidates.append((score + 180, {"kind": "equation", "target": eq, "reason": block_reason}))
    if not candidates:
        return {"kind": "none", "target": "", "reason": "no_consolidatable_equation"}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

def _prepare_mutation_decision(cfg: RuntimeConfig) -> dict[str, str]:
    shared = SharedResearchMemory(cfg.session_dir)
    candidates: list[tuple[int, dict[str, str]]] = []
    for row in shared.get_all_equation_entries():
        eq = str(row.get("equation", "") or "").strip()
        if not eq:
            continue
        score, reasons = _mutation_score(shared, row)
        if score < -120:
            continue
        block_reason = _row_mutation_block_reason(shared, row)
        reason_l = str(block_reason or "").strip().lower()
        if block_reason == "ok":
            candidates.append((score + 500, {"kind": "ready", "target": eq, "reason": "ready_for_mutation"}))
            continue
        if any(k in reason_l for k in ["fallback", "placeholder"]):
            candidates.append((score + 320, {"kind": "consolidate", "target": eq, "reason": "needs_consolidation"}))
            continue
        if "variable" in reason_l or "non valid" in reason_l or "unvalidated" in reason_l:
            decision = shared.choose_next_repair_action()
            if str(decision.get("kind", "")).strip() == "variable":
                target = str(decision.get("target", "") or "").strip()
                if target:
                    candidates.append((score + 250, {"kind": "variable", "target": target, "reason": "needs_variable_preparation", "equation": eq}))
                    continue
        if any(k in reason_l for k in ["repair", "partielle", "partial", "parent", "non approuv", "non stable"]):
            candidates.append((score + 150, {"kind": "equation", "target": eq, "reason": "needs_equation_preparation"}))
    if not candidates:
        return {"kind": "none", "target": "", "reason": "no_preparable_equation"}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

def run_prepare_mutation(steps: int = 10, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    steps = max(1, int(steps))
    print(f"[MODE] Prepare Mutation | steps={steps}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    for index in range(1, steps + 1):
        decision = _prepare_mutation_decision(cfg)
        kind = str(decision.get("kind", "none") or "none")
        target = str(decision.get("target", "") or "")
        reason = str(decision.get("reason", "") or "")
        if kind == "none" or not target:
            print(f"[INFO] Prepare Mutation stopped: {reason or 'no_preparable_equation'}")
            break
        if kind == "ready":
            print(f"[PREP {index}/{steps}] target={target} | reason=ready_for_mutation")
            executed += 1
            break
        print(f"[ENGINE] action=prepare-mutation | target={target} | reason={reason}")
        print(f"[PREP {index}/{steps}] target={target} | reason={reason}")
        if kind == "variable":
            cfg.target_variable = target
            VariableRepairOrchestrator(cfg).run(turns=1, target_variable=target)
        else:
            cfg.target_equation = target
            RepairEquationOrchestrator(cfg).run(turns=1)
        _cleanup_shared(cfg)
        executed += 1
    print(f"[DONE] Prepare Mutation executed={executed}")


def run_auto_prepare_mutation(steps: int = 10, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    steps = max(1, int(steps))
    print(f"[MODE] Auto Prepare Mutation | steps={steps}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    ready_hits = 0
    for index in range(1, steps + 1):
        decision = _prepare_mutation_decision(cfg)
        kind = str(decision.get("kind", "none") or "none")
        target = str(decision.get("target", "") or "")
        reason = str(decision.get("reason", "") or "")
        print(f"[ENGINE] action=prepare-mutation | target={target} | reason={reason}")
        if kind == "none" or not target:
            print(f"[INFO] Auto Prepare Mutation stopped: {reason or 'no_preparable_equation'}")
            break
        if kind == "ready":
            print(f"[PREP {index}/{steps}] target={target} | reason=ready_for_mutation")
            ready_hits += 1
            executed += 1
            if ready_hits >= 2:
                break
            continue
        print(f"[PREP {index}/{steps}] target={target} | reason={reason}")
        if kind == "variable":
            cfg.target_variable = target
            VariableRepairOrchestrator(cfg).run(turns=1, target_variable=target)
        else:
            cfg.target_equation = target
            RepairEquationOrchestrator(cfg).run(turns=1)
        _cleanup_shared(cfg)
        executed += 1
    print(f"[DONE] Auto Prepare Mutation executed={executed}")

def run_auto_repair(turns: int = 3, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    turns = max(1, turns)
    print(f"[MODE] Auto Repair | steps={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    for index in range(1, turns + 1):
        shared = SharedResearchMemory(cfg.session_dir)
        decision = shared.choose_next_repair_action()
        kind = str(decision.get('kind', '') or '').strip()
        target = str(decision.get('target', '') or '').strip()
        reason = str(decision.get('reason', '') or '').strip()
        if kind == 'none' or not target:
            print(f"[INFO] Auto Repair stopped: {reason or 'no_repairable_target'}.")
            break

        if kind == 'variable':
            cfg.target_variable = target
            print(f"[ENGINE] action=variable | target={target} | reason={reason}")
            print(f"[AUTO {index}/{turns}] variable repair cycle on {target}")
            VariableRepairOrchestrator(cfg).run(turns=1, target_variable=target)
            _cleanup_shared(cfg)
            executed += 1
            continue

        cfg.target_equation = target
        print(f"[ENGINE] action=equation | target={cfg.target_equation} | reason={reason}")
        ok, ready_reason = _repair_ready(cfg)
        if not ok:
            print(f"[AUTO {index}/{turns}] skipped: {ready_reason}")
            break
        RepairEquationOrchestrator(cfg).run(turns=1)
        _cleanup_shared(cfg)

        post = SharedResearchMemory(cfg.session_dir)
        after = post.choose_next_repair_action()
        if str(after.get('kind', '')) == 'variable' and str(after.get('reason', '')).strip() == 'blocked_by_unvalidated_variables':
            print(f"[ENGINE] next=variable | target={str(after.get('target','')).strip()} | reason=blocked_by_unvalidated_variables")
        executed += 1
    print(f"[DONE] Auto Repair executed={executed}")


def run_all_repair(steps: int = 10, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    steps = max(1, int(steps))
    print(f"[MODE] All Repair | steps={steps}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    for index in range(1, steps + 1):
        shared = SharedResearchMemory(cfg.session_dir)
        if hasattr(shared, "choose_next_repair_action"):
            decision = shared.choose_next_repair_action()
        else:
            target = _pick_auto_repair_target(cfg)
            decision = {"kind": "equation", "target": str((target or {}).get("equation", "") or ""), "reason": "legacy_auto_repair"}
        kind = str(decision.get("kind", "none") or "none")
        target = str(decision.get("target", "") or "")
        reason = str(decision.get("reason", "") or "")
        print(f"[ENGINE] action={kind} | target={target} | reason={reason}")
        if kind == "none" or not target:
            print("[INFO] All Repair stopped: nothing actionable.")
            break
        if kind == "variable":
            print(f"[AUTO {index}/{steps}] variable repair cycle on {target}")
            from variable_repair_orchestrator import VariableRepairOrchestrator
            VariableRepairOrchestrator(cfg).run(turns=1, target_variable=target)
        else:
            cfg.target_equation = target
            print(f"[AUTO {index}/{steps}] equation repair cycle on {target}")
            RepairEquationOrchestrator(cfg).run(turns=1)
        _cleanup_shared(cfg)
        executed += 1
    print(f"[DONE] All Repair executed={executed}")

def run_auto_consolidate_mutation(steps: int = 5, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    steps = max(1, int(steps))
    print(f"[MODE] Auto Consolidate Mutation | steps={steps}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    sterile_targets: set[str] = set()
    processed_targets: set[str] = set()
    blocked_targets: set[str] = set()
    repeated_blocked_target = ""
    repeated_blocked_count = 0

    for index in range(1, steps + 1):
        decision = _consolidate_mutation_decision(cfg)
        kind = str(decision.get("kind", "none") or "none")
        target = str(decision.get("target", "") or "")
        reason = str(decision.get("reason", "") or "")
        shared = SharedResearchMemory(cfg.session_dir)

        if kind == "none" or not target:
            print(f"[INFO] Auto Consolidate Mutation stopped: {reason or 'no_consolidatable_equation'}")
            break

        raw_target = target
        raw_target_key = normalize_target_equation(raw_target)
        if raw_target_key and raw_target_key in blocked_targets:
            print(f"[SKIP] blocked consolidation target: {raw_target}")
            if repeated_blocked_target == raw_target_key:
                repeated_blocked_count += 1
            else:
                repeated_blocked_target = raw_target_key
                repeated_blocked_count = 1
            if repeated_blocked_count >= 3:
                print(f"[INFO] Auto Consolidate Mutation stopped: repeated blocked target {raw_target}")
                break
            continue

        if kind == "consolidate":
            upgraded = _upgrade_sterile_equation(target)
            if upgraded != normalize_target_equation(target):
                print(f"[RECOVER] sterile target upgraded: {target} -> {upgraded}")
                target = upgraded
                if raw_target_key:
                    blocked_targets.add(raw_target_key)

        target_key = normalize_target_equation(target)
        if (target_key and target_key in processed_targets) or (raw_target_key and raw_target_key in processed_targets):
            print(f"[SKIP] already processed consolidation target: {target}")
            if raw_target_key:
                blocked_targets.add(raw_target_key)
            continue
        if (target_key and target_key in sterile_targets) or (raw_target_key and raw_target_key in sterile_targets):
            print(f"[SKIP] blacklisted sterile consolidation target: {target}")
            if raw_target_key:
                blocked_targets.add(raw_target_key)
            continue

        if kind == "variable":
            print(f"[ENGINE] action=variable | target={target} | reason={reason}")
            print(f"[CONSOLIDATE {index}/{steps}] variable repair handoff on {target}")
            cfg.target_variable = target
            VariableRepairOrchestrator(cfg).run(turns=1, target_variable=target)
            _cleanup_shared(cfg)
            executed += 1
            repeated_blocked_target = ""
            repeated_blocked_count = 0
            continue

        if kind == "equation" and hasattr(shared, "was_recently_validated") and shared.was_recently_validated(target, window=4):
            print(f"[SKIP] equation already recently validated: {target}")
            if target_key:
                processed_targets.add(target_key)
            if raw_target_key:
                blocked_targets.add(raw_target_key)
            continue

        if kind == "consolidate" and hasattr(shared, "was_recently_consolidated") and shared.was_recently_consolidated(target, window=10):
            print(f"[SKIP] equation already recently consolidated: {target}")
            if target_key:
                processed_targets.add(target_key)
            if raw_target_key:
                blocked_targets.add(raw_target_key)
            continue

        if kind == "consolidate" and hasattr(shared, "was_recently_sterile_consolidation") and shared.was_recently_sterile_consolidation(target, window=10):
            print(f"[SKIP] sterile consolidation cached: {target}")
            if target_key:
                sterile_targets.add(target_key)
                processed_targets.add(target_key)
            if raw_target_key:
                sterile_targets.add(raw_target_key)
                processed_targets.add(raw_target_key)
                blocked_targets.add(raw_target_key)
            continue

        print(f"[ENGINE] action=consolidate-mutation | target={target} | reason={reason}")
        print(f"[CONSOLIDATE {index}/{steps}] target={target} | reason={reason}")

        if kind == "consolidate":
            ok, consolidated = _persist_consolidated_parent_equation(cfg, target, reason=reason)
            if ok:
                print(f"[CONSOLIDATE] parent enriched -> {consolidated}")
                cfg.target_equation = consolidated
                if target_key:
                    sterile_targets.discard(target_key)
                    processed_targets.add(target_key)
                if raw_target_key:
                    sterile_targets.discard(raw_target_key)
                    processed_targets.add(raw_target_key)
                    blocked_targets.add(raw_target_key)
                cons_key = normalize_target_equation(consolidated)
                if cons_key:
                    sterile_targets.discard(cons_key)
                    processed_targets.add(cons_key)
                repeated_blocked_target = ""
                repeated_blocked_count = 0
            else:
                print(f"[CONSOLIDATE] skipped: {consolidated}")
                cfg.target_equation = target
                if target_key:
                    sterile_targets.add(target_key)
                    processed_targets.add(target_key)
                if raw_target_key:
                    sterile_targets.add(raw_target_key)
                    processed_targets.add(raw_target_key)
                    blocked_targets.add(raw_target_key)
                try:
                    shared.add_sterile_consolidation_log(target, reason=str(consolidated or 'no_structural_change'))
                    if raw_target_key and raw_target_key != target_key:
                        shared.add_sterile_consolidation_log(raw_target, reason=str(consolidated or 'no_structural_change'))
                except Exception:
                    pass
            _cleanup_shared(cfg)
            executed += 1
            continue

        cfg.target_equation = target
        RepairEquationOrchestrator(cfg).run(turns=1)
        shared = SharedResearchMemory(cfg.session_dir)
        post = shared.choose_next_repair_action() if hasattr(shared, "choose_next_repair_action") else {"kind": "none", "target": "", "reason": ""}
        if str(post.get("kind", "") or "").strip() == "variable":
            next_var = str(post.get("target", "") or "").strip()
            next_reason = str(post.get("reason", "") or "blocked_by_unvalidated_variables")
            if next_var:
                print(f"[ENGINE] next=variable | target={next_var} | reason={next_reason}")
                cfg.target_variable = next_var
                VariableRepairOrchestrator(cfg).run(turns=1, target_variable=next_var)
        _cleanup_shared(cfg)
        executed += 1
        repeated_blocked_target = ""
        repeated_blocked_count = 0

    if executed == 0:
        print("[INFO] Auto Consolidate Mutation ended without execution; all candidate targets were blocked or already processed.")
    print(f"[DONE] Auto Consolidate Mutation executed={executed}")

def run_auto_mutation(turns: int = 3, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    turns = max(1, turns)
    print(f"[MODE] Auto Mutation | steps={turns}")
    print(f"[SESSION] {cfg.session_dir}")
    executed = 0
    blocked: set[str] = set()
    for index in range(1, turns + 1):
        shared = SharedResearchMemory(cfg.session_dir)
        scored: list[dict[str, Any]] = []
        for row in shared.get_all_equation_entries():
            eq = str(row.get('equation', '') or '').strip()
            if not eq or eq in blocked:
                continue
            score, reasons = _mutation_score(shared, row)
            block_reason = _row_mutation_block_reason(shared, row)
            if 'placeholder_like' in reasons and block_reason != 'ok':
                continue
            enriched = dict(row)
            enriched['_mutation_score'] = score
            enriched['_mutation_reasons'] = reasons
            enriched['_mutation_block_reason'] = block_reason
            scored.append(enriched)
        scored.sort(key=lambda row: int(row.get('_mutation_score', 0)), reverse=True)
        if not scored:
            print(f"[INFO] Auto Mutation stopped: no mutable parent equation found.")
            break
        mutated_this_round = False
        for target in scored:
            cfg.target_equation = str(target.get('equation', '') or '').strip()
            print(f"[AUTO {index}/{turns}] target={cfg.target_equation}")
            score = target.get("_mutation_score", "?")
            reasons = ", ".join(target.get("_mutation_reasons", []))
            print(f"[MUTATION SCORE] {score} | {reasons}")
            block_reason = str(target.get('_mutation_block_reason', '') or '')
            if block_reason == 'ok':
                MutationEquationOrchestrator(cfg).run(turns=1)
                _cleanup_shared(cfg)
                executed += 1
                mutated_this_round = True
                break
            blocked.add(cfg.target_equation)
            lower_reason = block_reason.lower()
            if any(token in lower_reason for token in ['fallback', 'placeholder']):
                print(f"[ENGINE] action=consolidate-mutation | target={cfg.target_equation} | reason={block_reason}")
                ok, consolidated = _persist_consolidated_parent_equation(cfg, cfg.target_equation, reason=block_reason)
                if ok:
                    print(f"[CONSOLIDATE] parent enriched -> {consolidated}")
                    _cleanup_shared(cfg)
                    continue
                run_auto_consolidate_mutation(1, session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
                _cleanup_shared(cfg)
                continue
            if any(token in lower_reason for token in ['réparer', 'repair', 'parent', 'partielle', 'partial']):
                print(f"[ENGINE] action=prepare-mutation | target={cfg.target_equation} | reason={block_reason}")
                run_prepare_mutation(1, session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
                _cleanup_shared(cfg)
                continue
            print(f"[AUTO {index}/{turns}] skipped: {block_reason}")
        if not mutated_this_round and len(blocked) >= len(scored):
            print(f"[INFO] Auto Mutation stopped: all candidate parents blocked in this run.")
            break
    print(f"[DONE] Auto Mutation executed={executed}")

def run_both(v_turns: int = 1, e_turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    v_turns = max(1, v_turns)
    e_turns = max(1, e_turns)
    print(f"[MODE] BOTH = variables -> equations | v_turns={v_turns} | e_turns={e_turns}")
    print(f"[SESSION] {cfg.session_dir}")
    VariableDebateOrchestrator(cfg).run(turns=v_turns)
    print("\n[INFO] Passage aux équations avec mémoire partagée\n")
    EquationDebateOrchestrator(cfg).run(turns=e_turns)
    _cleanup_shared(cfg)


def run_full(v_turns: int = 1, e_turns: int = 1, m_turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    v_turns = max(1, v_turns)
    e_turns = max(1, e_turns)
    m_turns = max(1, m_turns)
    print(f"[MODE] FULL = variables -> equations -> mutation | v_turns={v_turns} | e_turns={e_turns} | m_turns={m_turns}")
    print(f"[SESSION] {cfg.session_dir}")
    VariableDebateOrchestrator(cfg).run(turns=v_turns)
    print("\n[INFO] Passage aux équations avec mémoire partagée\n")
    EquationDebateOrchestrator(cfg).run(turns=e_turns)
    _cleanup_shared(cfg)
    _maybe_run_repair(cfg, e_turns)
    ok, reason = _mutation_ready(cfg)
    if ok:
        print("\n[INFO] Passage à la mutation d'équation\n")
        MutationEquationOrchestrator(cfg).run(turns=m_turns)
    else:
        print(f"\n[INFO] Mutation bloquée: {reason}\n")
    _cleanup_shared(cfg)
    _print_lineages(cfg, limit=3)


def run_loop(cycles: int = 0, v_turns: int = 1, e_turns: int = 1, m_turns: int = 0, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    v_turns = max(1, v_turns)
    e_turns = max(1, e_turns)
    m_turns = max(0, m_turns)
    infinite = cycles <= 0
    label = "∞" if infinite else str(cycles)
    print(f"[MODE] LOOP = {label} cycles | variables={v_turns} | equations={e_turns} | mutation={m_turns}")
    print(f"[SESSION] {cfg.session_dir}")

    i = 0
    try:
        while True:
            i += 1
            print(f"\n===== CYCLE {i}{'' if infinite else f'/{cycles}'} =====\n")
            VariableDebateOrchestrator(cfg).run(turns=v_turns)
            print("\n[INFO] Passage aux équations avec mémoire partagée\n")
            EquationDebateOrchestrator(cfg).run(turns=e_turns)
            _cleanup_shared(cfg)
            _maybe_run_repair(cfg, e_turns)
            if m_turns > 0:
                ok, reason = _mutation_ready(cfg)
                if ok:
                    print("\n[INFO] Passage à la mutation d'équation\n")
                    MutationEquationOrchestrator(cfg).run(turns=m_turns)
                else:
                    print(f"\n[INFO] Mutation bloquée: {reason}\n")
            _cleanup_shared(cfg)
            _print_lineages(cfg, limit=3)
            if not infinite and i >= cycles:
                break
    except KeyboardInterrupt:
        print("\n[STOP] Arrêt manuel détecté. Fin propre du launcher.")


def run_full_evolve(cycles: int = 3, v_turns: int = 1, e_turns: int = 1, prep_steps: int = 3, m_turns: int = 1, *, session_name: str | None = None, resume_latest: bool = False, create_new: bool = False) -> None:
    cfg = _cfg(session_name=session_name, resume_latest=resume_latest, create_new=create_new, strict=bool(session_name) or resume_latest)
    cycles = max(1, cycles)
    v_turns = max(1, v_turns)
    e_turns = max(1, e_turns)
    prep_steps = max(1, prep_steps)
    m_turns = max(1, m_turns)
    print(f"[MODE] FULL EVOLVE | cycles={cycles} | variables={v_turns} | equations={e_turns} | prepare={prep_steps} | mutation={m_turns}")
    print(f"[SESSION] {cfg.session_dir}")
    for cycle in range(1, cycles + 1):
        print(f"\n===== EVOLVE CYCLE {cycle}/{cycles} =====\n")
        VariableDebateOrchestrator(cfg).run(turns=v_turns)
        print("\n[INFO] Passage aux équations avec mémoire partagée\n")
        EquationDebateOrchestrator(cfg).run(turns=e_turns)
        _cleanup_shared(cfg)
        run_auto_repair(max(1, prep_steps), session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
        run_auto_prepare_mutation(max(1, prep_steps), session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
        run_auto_consolidate_mutation(max(1, prep_steps), session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
        run_auto_mutation(max(1, m_turns), session_name=Path(cfg.session_dir).name, resume_latest=False, create_new=False)
        _cleanup_shared(cfg)
        _print_lineages(cfg, limit=3)



# ---------- CLI ----------


def print_usage() -> None:
    print("Usage:")
    print("  python3 launcher.py reset")
    print("  python3 launcher.py list-sessions")
    print("  python3 launcher.py variables [turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py equations [turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py mutation [turns] [--create-new-session | --resume | --session NOM] [--target-equation TEXTE]")
    print("  python3 launcher.py repair [turns] [--create-new-session | --resume | --session NOM] [--target-equation TEXTE]")
    print("  python3 launcher.py auto-mutation [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py prepare-mutation [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py auto-prepare-mutation [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py auto-consolidate-mutation [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py auto-repair [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py all-repair [steps] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py equation-test --target-equation TEXTE [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py lineages [limit] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py status [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py both [variable_turns] [equation_turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py full [variable_turns] [equation_turns] [mutation_turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py loop [cycles] [variable_turns] [equation_turns] [mutation_turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py full-evolve [cycles] [variable_turns] [equation_turns] [prepare_steps] [mutation_turns] [--create-new-session | --resume | --session NOM]")
    print("  python3 launcher.py merge-sessions --session-a NOM --session-b NOM [--create-new-session | --target-session NOM]")


def _extract_option(args: list[str], flag: str) -> tuple[list[str], str | None]:
    items = list(args)
    if flag not in items:
        return items, None
    idx = items.index(flag)
    if idx + 1 >= len(items):
        raise ValueError(f"Option sans valeur: {flag}")
    value = items[idx + 1]
    del items[idx : idx + 2]
    return items, value


def main() -> None:
    args = sys.argv[1:]
    base_dir = get_workspace_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    if not args or args[0] in {"-h", "--help"}:
        print_usage()
        return

    mode = args[0].lower()
    remaining = list(args[1:])
    resume_latest = "--resume" in remaining
    create_new = "--create-new-session" in remaining
    remaining = [a for a in remaining if a not in {"--resume", "--create-new-session"}]
    remaining, session_name = _extract_option(remaining, "--session")
    remaining, session_a = _extract_option(remaining, "--session-a")
    remaining, session_b = _extract_option(remaining, "--session-b")
    remaining, target_session = _extract_option(remaining, "--target-session")
    remaining, target_equation = _extract_option(remaining, "--target-equation")

    try:
        if mode == "reset":
            reset_all_memory(base_dir)
            return
        if mode == "list-sessions":
            sessions = list_sessions(base_dir)
            if not sessions:
                print("[INFO] Aucune session.")
            for path in sessions:
                print(path.name)
            return
        if mode == "merge-sessions":
            print(f"[MODE] merge-sessions")
            if not session_a or not session_b:
                raise ValueError("merge-sessions exige --session-a et --session-b")
            merge_full_sessions(session_a, session_b, target_session_name=target_session, create_new_target=not bool(target_session))
            return

        if mode == "variables":
            run_variables(_safe_int(remaining[0], 1) if len(remaining) > 0 else 1, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "equations":
            run_equations(_safe_int(remaining[0], 1) if len(remaining) > 0 else 1, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "both":
            run_both(_safe_int(remaining[0], 1) if len(remaining) > 0 else 1, _safe_int(remaining[1], 1) if len(remaining) > 1 else 1, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "mutation":
            run_mutation(_safe_int(remaining[0], 1) if len(remaining) > 0 else 1, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name), target_equation=target_equation)
        elif mode == "repair":
            run_repair(_safe_int(remaining[0], 1) if len(remaining) > 0 else 1, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name), target_equation=target_equation)
        elif mode == "auto-mutation":
            run_auto_mutation(_safe_int(remaining[0], 3) if len(remaining) > 0 else 3, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "auto-repair":
            run_auto_repair(_safe_int(remaining[0], 3) if len(remaining) > 0 else 3, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "prepare-mutation":
            run_prepare_mutation(_safe_int(remaining[0], 10) if len(remaining) > 0 else 10, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "auto-prepare-mutation":
            run_auto_prepare_mutation(_safe_int(remaining[0], 10) if len(remaining) > 0 else 10, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "auto-consolidate-mutation":
            run_auto_consolidate_mutation(_safe_int(remaining[0], 5) if len(remaining) > 0 else 5, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "all-repair":
            run_all_repair(_safe_int(remaining[0], 10) if len(remaining) > 0 else 10, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "equation-test":
            run_equation_test(session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name), target_equation=target_equation)
        elif mode == "lineages":
            run_lineages(_safe_int(remaining[0], 5) if len(remaining) > 0 else 5, session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "status":
            run_status(session_name=session_name, resume_latest=resume_latest, create_new=create_new or not (resume_latest or session_name))
        elif mode == "full":
            run_full(
                _safe_int(remaining[0], 1) if len(remaining) > 0 else 1,
                _safe_int(remaining[1], 1) if len(remaining) > 1 else 1,
                _safe_int(remaining[2], 1) if len(remaining) > 2 else 1,
                session_name=session_name,
                resume_latest=resume_latest,
                create_new=create_new or not (resume_latest or session_name),
            )
        elif mode == "loop":
            run_loop(
                _safe_int(remaining[0], 0) if len(remaining) > 0 else 0,
                _safe_int(remaining[1], 1) if len(remaining) > 1 else 1,
                _safe_int(remaining[2], 1) if len(remaining) > 2 else 1,
                _safe_int(remaining[3], 0) if len(remaining) > 3 else 0,
                session_name=session_name,
                resume_latest=resume_latest,
                create_new=create_new or not (resume_latest or session_name),
            )
        elif mode == "full-evolve":
            run_full_evolve(
                _safe_int(remaining[0], 3) if len(remaining) > 0 else 3,
                _safe_int(remaining[1], 1) if len(remaining) > 1 else 1,
                _safe_int(remaining[2], 1) if len(remaining) > 2 else 1,
                _safe_int(remaining[3], 3) if len(remaining) > 3 else 3,
                _safe_int(remaining[4], 1) if len(remaining) > 4 else 1,
                session_name=session_name,
                resume_latest=resume_latest,
                create_new=create_new or not (resume_latest or session_name),
            )
        else:
            print_usage()
    except SecurityStop as exc:
        print(f'[SECURITY STOP] {exc}')
        raise
    except Exception as exc:
        print(f"[ERREUR] {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
