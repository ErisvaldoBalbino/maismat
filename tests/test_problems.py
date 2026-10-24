import random

import pytest

from maismat import problems


@pytest.mark.parametrize("op", problems.OPERATIONS)
@pytest.mark.parametrize("difficulty", problems.DIFFICULTIES)
def test_random_problems_are_valid(op, difficulty):
    rng = random.Random(1)
    for _ in range(300):
        p = problems.random_problem(op, difficulty, rng)
        assert p["op"] == op
        assert p["answer"] == problems.compute(op, p["a"], p["b"])
        assert p["answer"] >= 0
        if op == "div":
            assert p["a"] % p["b"] == 0


def test_table_problems_use_chosen_tables():
    rng = random.Random(2)
    for _ in range(200):
        p = problems.table_problem(["mul", "div"], [7, 8], rng)
        if p["op"] == "mul":
            assert 7 in (p["a"], p["b"]) or 8 in (p["a"], p["b"])
        else:
            assert p["b"] in (7, 8) and p["a"] % p["b"] == 0


def test_generate_avoids_immediate_repeats():
    items = problems.generate("table", ["mul"], "easy", 100, tables=[2], rng=random.Random(3))
    assert len(items) == 100
    for prev, cur in zip(items, items[1:]):
        assert (prev["a"], prev["b"]) != (cur["a"], cur["b"])


def test_generate_weak_uses_given_facts():
    facts = [{"op": "mul", "a": 7, "b": 8}, {"op": "sub", "a": 15, "b": 9}]
    items = problems.generate("weak", [], "easy", 30, weak_facts=facts, rng=random.Random(4))
    assert {(p["op"], p["a"], p["b"]) for p in items} <= {("mul", 7, 8), ("sub", 15, 9)}
