"""Indicators the atlas calculates from other indicators (config/indicators.json "derived").

A formula is arithmetic over indicator ids and numbers, for example
"SH.XPD.CHEX.PP.CD * SH.XPD.OOPC.CH.ZS / NY.GDP.PCAP.PP.CD". The result takes the
oldest year among its inputs. Only + - * / and parentheses are allowed.
"""
from __future__ import annotations

import ast
import operator
import re

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def inputs(formula: str) -> list[str]:
    """Indicator ids used by a formula, in order of first use."""
    seen: list[str] = []
    for t in TOKEN.findall(formula):
        if t not in seen:
            seen.append(t)
    return seen


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    raise ValueError(f"unsupported expression element: {ast.dump(node)}")


def evaluate(formula: str, records: dict[str, dict]) -> dict | None:
    """{"value", "year"} from input records ({id: {"value", "year"}}), or None if any input is missing."""
    ids = inputs(formula)
    recs = [records.get(i) for i in ids]
    if not ids or any(r is None or r.get("value") is None or r.get("year") is None for r in recs):
        return None
    names = {i: f"v{n}" for n, i in enumerate(ids)}
    expr = TOKEN.sub(lambda m: names[m.group(0)], formula)
    env = {names[i]: float(r["value"]) for i, r in zip(ids, recs)}
    try:
        value = _eval(ast.parse(expr, mode="eval"), env)
    except ZeroDivisionError:
        return None
    return {"value": value, "year": min(int(r["year"]) for r in recs)}
