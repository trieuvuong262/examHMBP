"""Xao thu tu dap an trong thu vien: dung khong con luon o A / ABC."""
from __future__ import annotations

import random
from collections import Counter

from assessment.models import Choice, Question

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def shuffle_question_choices(question: Question) -> bool:
    choices = list(question.choices.all())
    if len(choices) < 2:
        return False
    rng = random.Random(question.id * 104729 + 17)
    rng.shuffle(choices)
    for idx, choice in enumerate(choices, start=1):
        choice.sort_order = idx
    Choice.objects.bulk_update(choices, ["sort_order"])
    return True


def key_for(question: Question) -> str:
    marks = [
        LETTERS[idx]
        for idx, choice in enumerate(question.choices.order_by("sort_order", "id"))
        if choice.is_correct
    ]
    return "".join(marks) or "-"


qs = Question.objects.filter(q_type__in=("single", "multiple")).prefetch_related("choices")
before_single = Counter()
before_multi = Counter()
for q in qs:
    bucket = before_single if q.q_type == "single" else before_multi
    bucket[key_for(q)] += 1

print("BEFORE_SINGLE", dict(before_single))
print("BEFORE_MULTI", dict(before_multi))

n = 0
for q in qs:
    if shuffle_question_choices(q):
        n += 1

qs = Question.objects.filter(q_type__in=("single", "multiple")).prefetch_related("choices")
after_single = Counter()
after_multi = Counter()
for q in qs:
    bucket = after_single if q.q_type == "single" else after_multi
    bucket[key_for(q)] += 1

print("SHUFFLED", n)
print("AFTER_SINGLE", dict(after_single))
print("AFTER_MULTI", dict(after_multi))
print("SHUFFLE_DONE")
