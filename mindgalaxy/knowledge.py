"""
mindgalaxy.knowledge
=====================

Gives every star its "gas cloud" of related knowledge.

* detect_topics(text)  -> which curated topics a thought is about
                          ("i love milk" -> milk; "lost track of time" -> watch)
* solve_math(text)     -> a worked solution when a thought is a maths problem
                          ("solve 2x + 3 = 11", "what is 15% of 240")
* attach_knowledge(g)  -> enriches a computed galaxy in place: per-star topics
                          and maths, a top-level `topics` dictionary holding
                          the facets for only the topics actually used, and
                          extra `topic` edges that interconnect thoughts whose
                          topics are the same or related, even when they share
                          no words (e.g. "I love milk" <-> "I like to cook").

All local and deterministic -- no network, no API. (Thoughts that match no
curated topic get a Wikipedia lookup in the browser instead; see the
template.)
"""
from __future__ import annotations

import ast
import math
import operator
import re
from fractions import Fraction
from typing import Any, Optional

from .knowledge_base import RELATIONS, TOPICS

# ---------------------------------------------------------------------------
# Topic detection
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[a-z][a-z'\-]*")


def _variants(word: str) -> set[str]:
    """The word plus light de-pluralised forms, so 'watches' finds 'watch'."""
    w = word.strip("'-")
    out = {w}
    if w.endswith("'s"):
        out.add(w[:-2])
    if len(w) > 4 and w.endswith("ies"):
        out.add(w[:-3] + "y")
    if len(w) > 4 and w.endswith("es"):
        out.add(w[:-2])
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        out.add(w[:-1])
    return out


def _compile_topics() -> dict[str, dict[str, Any]]:
    compiled = {}
    for tid, t in TOPICS.items():
        single, phrases = set(), []
        for kw in t.get("keywords", []):
            kw = kw.lower()
            (phrases.append(kw) if " " in kw else single.add(kw))
        phrases += [p.lower() for p in t.get("phrases", [])]
        compiled[tid] = {
            "single": single,
            "phrases": [re.compile(r"\b" + re.escape(p) + r"\b") for p in phrases],
            "exclude": [re.compile(x) for x in t.get("exclude", [])],
            "priority": float(t.get("priority", 1.0)),
        }
    return compiled


_COMPILED = _compile_topics()

# topic -> {other_topic: reason}
RELATED: dict[str, dict[str, str]] = {tid: {} for tid in TOPICS}
for _a, _b, _why in RELATIONS:
    RELATED[_a][_b] = _why
    RELATED[_b][_a] = _why


def detect_topics(text: str, max_topics: int = 3) -> list[str]:
    """Return topic ids ranked by relevance (strongest first)."""
    low = " " + text.lower() + " "
    tokens: set[str] = set()
    for w in _WORD_RE.findall(low):
        tokens |= _variants(w)
    scores: dict[str, float] = {}
    for tid, c in _COMPILED.items():
        cleaned = low
        for rx in c["exclude"]:
            cleaned = rx.sub(" ", cleaned)
        if c["exclude"]:
            tok = set()
            for w in _WORD_RE.findall(cleaned):
                tok |= _variants(w)
        else:
            tok = tokens
        hits = len(c["single"] & tok) + 1.5 * sum(1 for rx in c["phrases"] if rx.search(cleaned))
        if hits:
            scores[tid] = hits * c["priority"]
    ranked = sorted(scores, key=lambda k: (-scores[k], k))
    return ranked[:max_topics]


# ---------------------------------------------------------------------------
# Maths solver: arithmetic, percentages, linear & quadratic equations
# ---------------------------------------------------------------------------
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log10, "ln": math.log, "abs": abs,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}

_WORD_OPS = [
    (r"\bmultiplied by\b", "*"), (r"\btimes\b", "*"), (r"\bdivided by\b", "/"), (r"\bover\b", "/"),
    (r"\bplus\b", "+"), (r"\bminus\b", "-"), (r"\bequals\b", "="), (r"\bis equal to\b", "="),
    (r"\bto the power of\b", "^"), (r"\bsquared\b", "^2"), (r"\bcubed\b", "^3"),
    (r"\bsquare root of\s*([\d.]+)", r"sqrt(\1)"), (r"\bmod\b", "%"),
    ("×", "*"), ("÷", "/"), ("−", "-"), ("√\\s*([\\d.]+)", r"sqrt(\1)"), ("²", "^2"), ("³", "^3"),
]
_CUE = re.compile(r"\b(solve|calculate|compute|evaluate|what is|what's|whats|how much is|simplify|find x|"
                  r"math|maths|equation|sqrt)\b|=|\?")
_TOKEN = re.compile(r"[a-z]+|\d+(?:\.\d+)?|[+\-*/^().%=]|\s+|.")


def _math_runs(e: str, allowed: set[str]) -> list[str]:
    """Split text into maximal runs of maths-looking tokens: numbers, operators,
    parentheses, function names and single-letter unknowns. Any ordinary word
    ("need", "apples") ends a run."""
    runs, cur = [], []
    for tok in _TOKEN.findall(e):
        mathy = (tok.isspace() or tok[0].isdigit() or tok in "+-*/^().%="
                 or tok in allowed or (tok.isalpha() and len(tok) == 1))
        if mathy:
            cur.append(tok)
        else:
            if cur:
                runs.append("".join(cur))
            cur = []
    if cur:
        runs.append("".join(cur))
    out = []
    for r in runs:
        r = r.strip()
        # drop a dangling lone letter at either end ("i 2+2", "2+2 a")
        r = re.sub(r"^[a-z]\s+(?=[\d(])", "", r)
        r = re.sub(r"(?<=[\d)])\s+[a-z]$", "", r).strip(" .")
        if r:
            out.append(r)
    return out


def _to_num(v):
    if isinstance(v, Fraction) and v.denominator == 1:
        return int(v)
    return v


def _eval(node, x=None):
    if isinstance(node, ast.Expression):
        return _eval(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
    if isinstance(node, ast.Name):
        if node.id == "x":
            if x is None:
                raise ValueError("unbound x")
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unknown name {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, x)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        a, b = _eval(node.left, x), _eval(node.right, x)
        if isinstance(node.op, ast.Pow):
            if abs(float(b)) > 64 or abs(float(a)) > 1e12:
                raise ValueError("power too large")
            if isinstance(a, Fraction) and isinstance(b, Fraction) and b.denominator == 1:
                return a ** int(b)
            return float(a) ** float(b)
        if isinstance(node.op, ast.Div) and b == 0:
            raise ZeroDivisionError
        return _BINOPS[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and len(node.args) == 1:
        v = float(_eval(node.args[0], x))
        r = _FUNCS[node.func.id](v)
        if isinstance(r, float) and r.is_integer():
            return Fraction(int(r))
        return r
    raise ValueError("unsupported expression")


def _fmt(v) -> str:
    v = _to_num(v)
    if isinstance(v, Fraction):
        f = float(v)
        return f"{v.numerator}/{v.denominator} (≈ {f:.6g})"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def _prep(expr: str) -> str:
    """Turn human maths into Python syntax: 2x -> 2*x, ^ -> **, 3(4) -> 3*(4)."""
    e = expr.strip().replace("^", "**")
    e = re.sub(r"(\d)\s*([a-z(])", r"\1*\2", e)       # 2x, 2(…)
    e = re.sub(r"\)\s*([\da-z(])", r")*\1", e)          # )(…), )x
    e = re.sub(r"\bx\s*\(", "x*(", e)
    return e


def _poly_coeffs(f):
    """Fit f(x) = a x^2 + b x + c exactly from 3 points and verify on 3 more."""
    f0, f1, f2 = f(Fraction(0)), f(Fraction(1)), f(Fraction(2))
    a = (f2 - 2 * f1 + f0) / 2
    b = f1 - f0 - a
    c = f0
    for t in (Fraction(3), Fraction(-2), Fraction(7, 2)):
        want = a * t * t + b * t + c
        if abs(float(f(t)) - float(want)) > 1e-9 * max(1.0, abs(float(want))):
            return None
    return a, b, c


def _term(coef, var: str) -> str:
    coef = _to_num(coef)
    if coef == 1:
        return var
    if coef == -1:
        return "-" + var
    return f"{coef}{var}"


def _solve_equation(lhs: str, rhs: str, shown: str) -> Optional[dict[str, Any]]:
    L = ast.parse(_prep(lhs), mode="eval")
    R = ast.parse(_prep(rhs), mode="eval")

    def f(t):
        v = _eval(L, t) - _eval(R, t)
        return v if isinstance(v, Fraction) else Fraction(v).limit_denominator(10**9)

    coeffs = _poly_coeffs(f)
    if coeffs is None:
        return {"kind": "equation", "input": shown, "answer": "Only linear and quadratic equations are solved here.",
                "steps": []}
    a, b, c = coeffs
    steps = [f"Start: {shown}"]
    if a == 0:
        if b == 0:
            ans = "Every x works (identity)" if c == 0 else "No solution"
            return {"kind": "equation", "input": shown, "answer": ans, "steps": steps}
        steps.append(f"Collect everything on one side: {_term(b, 'x')} {'+' if c >= 0 else '-'} {_to_num(abs(c))} = 0")
        steps.append(f"{'Subtract' if c >= 0 else 'Add'} {_to_num(abs(c))} on both sides: {_term(b, 'x')} = {_to_num(-c)}")
        x = -c / b
        if b != 1:
            steps.append(f"Divide both sides by {_to_num(b)}: x = {_to_num(-c)} / {_to_num(b)}")
        steps.append(f"x = {_fmt(x)}")
        return {"kind": "equation", "input": shown, "answer": f"x = {_fmt(x)}", "steps": steps}
    d = b * b - 4 * a * c
    steps.append(f"Standard form: {_term(a, 'x²')} {'+' if b >= 0 else '-'} {_term(abs(b), 'x') if b else '0'} "
                 f"{'+' if c >= 0 else '-'} {_to_num(abs(c))} = 0  →  a = {_to_num(a)}, b = {_to_num(b)}, c = {_to_num(c)}")
    steps.append(f"Discriminant: b² − 4ac = {_to_num(b * b)} − {_to_num(4 * a * c)} = {_to_num(d)}")
    steps.append("Quadratic formula: x = (−b ± √(b² − 4ac)) / 2a")
    if d < 0:
        re_ = -b / (2 * a)
        im = math.sqrt(-float(d)) / (2 * abs(float(a)))
        ans = f"No real roots: x = {float(re_):.6g} ± {im:.6g}i"
        steps.append(ans)
        return {"kind": "equation", "input": shown, "answer": ans, "steps": steps}
    sd = Fraction(math.isqrt(d.numerator), math.isqrt(d.denominator)) \
        if d >= 0 and math.isqrt(d.numerator) ** 2 == d.numerator and math.isqrt(d.denominator) ** 2 == d.denominator \
        else None
    if sd is not None:
        r1, r2 = (-b + sd) / (2 * a), (-b - sd) / (2 * a)
        roots = [_fmt(r1)] if r1 == r2 else [_fmt(r1), _fmt(r2)]
    else:
        s = math.sqrt(float(d))
        roots = [f"{(-float(b) + s) / (2 * float(a)):.6g}", f"{(-float(b) - s) / (2 * float(a)):.6g}"]
    ans = "x = " + " or x = ".join(roots)
    steps.append(ans)
    return {"kind": "equation", "input": shown, "answer": ans, "steps": steps}


def solve_math(text: str) -> Optional[dict[str, Any]]:
    """Return {kind, input, answer, steps} if the thought is a maths problem."""
    low = text.lower()
    if not re.search(r"\d", low):
        return None
    cued = bool(_CUE.search(low))

    # "15% of 240" / "15 percent of 240"
    m = re.search(r"(-?[\d.]+)\s*(%|percent|per cent)\s+of\s+(-?[\d.,]+)", low)
    if m:
        p, n = Fraction(m.group(1)), Fraction(m.group(3).replace(",", ""))
        v = p / 100 * n
        return {"kind": "percent", "input": m.group(0), "answer": _fmt(v),
                "steps": [f"{_to_num(p)}% = {_to_num(p)} / 100 = {_fmt(p / 100)}",
                          f"{_fmt(p / 100)} × {_to_num(n)} = {_fmt(v)}"]}

    e = low
    for pat, rep in _WORD_OPS:
        e = re.sub(pat, rep, e)
    allowed = set(_FUNCS) | set(_CONSTS)
    candidates = sorted(_math_runs(e, allowed), key=len, reverse=True)
    for run in candidates:
        letters = set(re.findall(r"[a-z]+", run))
        unknowns = {w for w in letters if w not in allowed}
        if len(unknowns) > 1:
            continue
        has_op = bool(re.search(r"[+\-*/^%=]|sqrt|\bsin|\bcos|\btan|\blog|\bln", run))
        if not has_op or not re.search(r"\d", run):
            continue
        share = len(run.replace(" ", "")) / max(1, len(re.sub(r"\s", "", low)))
        if not cued and share < 0.6:
            continue
        var = next(iter(unknowns), None)
        norm = run
        if var and var != "x":
            norm = re.sub(rf"(?<![a-z]){var}(?![a-z])", "x", run)
        try:
            if "=" in norm:
                if norm.count("=") != 1 or var is None:
                    continue
                lhs, rhs = norm.split("=")
                if not lhs.strip() or not rhs.strip():
                    continue
                sol = _solve_equation(lhs, rhs, run)
                if sol and var != "x":
                    sub = lambda t: re.sub(r"(?<![a-z])x(?![a-z])", var, t)
                    sol["answer"] = sub(sol["answer"])
                    sol["steps"] = [sol["steps"][0]] + [sub(t) for t in sol["steps"][1:]]
                return sol
            if var is not None:
                continue
            val = _eval(ast.parse(_prep(norm), mode="eval"))
            return {"kind": "expression", "input": run, "answer": _fmt(val),
                    "steps": [f"{run} = {_fmt(val)}"]}
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Galaxy enrichment
# ---------------------------------------------------------------------------
def _topic_payload(tid: str) -> dict[str, Any]:
    t = TOPICS[tid]
    out = {"id": tid, "label": t["label"], "facets": t["facets"],
           "related": RELATED.get(tid, {})}
    if t.get("note"):
        out["note"] = t["note"]
    return out


def attach_knowledge(galaxy: dict[str, Any], max_links_per_star: int = 4) -> dict[str, Any]:
    stars = galaxy.get("stars", [])
    used: set[str] = set()
    for s in stars:
        topics = detect_topics(s["text"])
        mathsol = solve_math(s["text"])
        if mathsol and "maths" not in topics:
            topics = ["maths"] + topics[:2]
        s["topics"] = topics
        s["math"] = mathsol
        used.update(topics)
    galaxy["topics"] = {tid: _topic_payload(tid) for tid in sorted(used)}

    edges = galaxy.setdefault("edges", [])
    existing = {(min(e["source"], e["target"]), max(e["source"], e["target"])): e for e in edges}
    links_per_star = [0] * len(stars)
    candidates = []
    for i in range(len(stars)):
        ti = stars[i]["topics"]
        if not ti:
            continue
        for j in range(i + 1, len(stars)):
            tj = stars[j]["topics"]
            if not tj:
                continue
            shared = [t for t in ti if t in tj]
            if shared:
                label = TOPICS[shared[0]]["label"]
                strength = 2.0 if shared[0] in (ti[0], tj[0]) else 1.2
                candidates.append((strength, i, j, f"Both about {label}", shared[0], shared[0]))
                continue
            best = None
            for a in ti:
                for b in tj:
                    why = RELATED.get(a, {}).get(b)
                    if why:
                        score = 1.0 + (0.3 if a == ti[0] else 0) + (0.3 if b == tj[0] else 0)
                        if best is None or score > best[0]:
                            best = (score, a, b, why)
            if best:
                score, a, b, why = best
                candidates.append((score, i, j, f"{TOPICS[a]['label']} ↔ {TOPICS[b]['label']}: {why}", a, b))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    for strength, i, j, reason, a, b in candidates:
        key = (i, j)
        if key in existing:
            existing[key].setdefault("reason", reason)
            continue
        if links_per_star[i] >= max_links_per_star or links_per_star[j] >= max_links_per_star:
            continue
        links_per_star[i] += 1
        links_per_star[j] += 1
        edges.append({"source": i, "target": j, "weight": min(1.0, 0.35 + 0.2 * strength),
                      "type": "topic", "reason": reason, "topics": [a, b]})
    return galaxy
