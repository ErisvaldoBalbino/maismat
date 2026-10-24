"""Geração de questões.

Todas as respostas são inteiros não negativos: subtração nunca dá negativo e
divisão é sempre exata.
"""

import random

OPERATIONS = ("add", "sub", "mul", "div")
SYMBOLS = {"add": "+", "sub": "−", "mul": "×", "div": "÷"}
OP_NAMES = {"add": "Adição", "sub": "Subtração", "mul": "Multiplicação", "div": "Divisão"}
DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_NAMES = {"easy": "Fácil", "medium": "Médio", "hard": "Difícil"}

# Faixas dos operandos (inclusive) por dificuldade.
ADD_RANGES = {
    "easy": ((1, 9), (1, 9)),
    "medium": ((10, 99), (10, 99)),
    "hard": ((100, 999), (100, 999)),
}
MUL_RANGES = {
    "easy": ((2, 9), (2, 9)),
    "medium": ((2, 12), (10, 99)),
    "hard": ((10, 99), (10, 99)),
}


def compute(op, a, b):
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        return a // b
    raise ValueError(f"operação inválida: {op}")


def make_problem(op, a, b):
    return {"op": op, "a": a, "b": b, "answer": compute(op, a, b), "symbol": SYMBOLS[op]}


def _rand(rng, bounds):
    return rng.randint(*bounds)


def random_problem(op, difficulty, rng=random):
    if op in ("add", "sub"):
        ra, rb = ADD_RANGES[difficulty]
        x, y = _rand(rng, ra), _rand(rng, rb)
        if op == "add":
            return make_problem("add", x, y)
        # Subtração como inverso da adição: (x + y) − y = x.
        return make_problem("sub", x + y, y)

    ra, rb = MUL_RANGES[difficulty]
    x, y = _rand(rng, ra), _rand(rng, rb)
    if rng.random() < 0.5:
        x, y = y, x
    if op == "mul":
        return make_problem("mul", x, y)
    # Divisão como inverso da multiplicação: (x · y) ÷ y = x.
    return make_problem("div", x * y, y)


def table_problem(ops, tables, rng=random, max_factor=10):
    """Questão de tabuada: um dos fatores pertence a `tables`."""
    ops = [op for op in ops if op in ("mul", "div")] or ["mul"]
    op = rng.choice(ops)
    t = rng.choice(tables)
    k = rng.randint(1, max_factor)
    if op == "mul":
        x, y = (t, k) if rng.random() < 0.5 else (k, t)
        return make_problem("mul", x, y)
    return make_problem("div", t * k, t)


def generate(mode, ops, difficulty, count, tables=None, weak_facts=None, rng=random):
    """Gera `count` questões, evitando repetir a mesma questão em sequência."""
    problems = []
    for _ in range(count):
        for _attempt in range(10):
            if mode == "table":
                p = table_problem(ops, tables, rng)
            elif mode == "weak" and weak_facts:
                f = rng.choice(weak_facts)
                p = make_problem(f["op"], f["a"], f["b"])
            else:
                p = random_problem(rng.choice(ops), difficulty, rng)
            if not problems or (p["op"], p["a"], p["b"]) != (
                problems[-1]["op"],
                problems[-1]["a"],
                problems[-1]["b"],
            ):
                break
        problems.append(p)
    return problems
