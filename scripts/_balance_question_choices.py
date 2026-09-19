"""Can dap an dung deu A/B/C/D — khong con toan A hoac toan ABC."""
from __future__ import annotations

from collections import Counter
from itertools import cycle

from assessment.models import Choice, Question

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def key_for(choices) -> str:
    return "".join(
        LETTERS[idx] for idx, choice in enumerate(choices) if choice.is_correct
    ) or "-"


def apply_order(choices) -> None:
    for idx, choice in enumerate(choices, start=1):
        choice.sort_order = idx
    Choice.objects.bulk_update(choices, ["sort_order"])


def arrange(choices, correct_positions: set[int]):
    goods = [c for c in choices if c.is_correct]
    bads = [c for c in choices if not c.is_correct]
    out = []
    gi = bi = 0
    for i in range(len(choices)):
        if i in correct_positions:
            out.append(goods[gi])
            gi += 1
        else:
            out.append(bads[bi])
            bi += 1
    if gi != len(goods) or bi != len(bads):
        raise ValueError("pattern mismatch")
    return out


qs = list(
    Question.objects.filter(q_type__in=("single", "multiple")).prefetch_related("choices")
)

singles4 = []
multi3 = []
other = []
for q in qs:
    choices = list(q.choices.all())
    n_ok = sum(1 for c in choices if c.is_correct)
    if q.q_type == "single" and len(choices) == 4 and n_ok == 1:
        singles4.append((q, choices))
    elif q.q_type == "multiple" and len(choices) == 4 and n_ok == 3:
        multi3.append((q, choices))
    else:
        other.append((q, choices, n_ok))

pos_cycle = cycle((0, 1, 2, 3))
for q, choices in singles4:
    pos = next(pos_cycle)
    apply_order(arrange(choices, {pos}))

wrong_cycle = cycle((0, 1, 2, 3))
for q, choices in multi3:
    wrong = next(wrong_cycle)
    apply_order(arrange(choices, {0, 1, 2, 3} - {wrong}))

print("SINGLE4", len(singles4), "MULTI3", len(multi3), "OTHER", len(other))
for q, choices, n_ok in other:
    print("LEAVE", q.id, q.q_type, "n", len(choices), "ok", n_ok, "key", key_for(choices))

after_single = Counter()
after_multi = Counter()
qs = Question.objects.filter(q_type__in=("single", "multiple")).prefetch_related("choices")
for q in qs:
    choices = list(q.choices.order_by("sort_order", "id"))
    bucket = after_single if q.q_type == "single" else after_multi
    bucket[key_for(choices)] += 1
print("AFTER_SINGLE", dict(after_single))
print("AFTER_MULTI", dict(after_multi))
print("BALANCE_DONE")
