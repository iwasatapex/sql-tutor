"""Grading for the Explain SQL question type.

An explain exercise shows the learner a query and asks what it does. The
answer is prose, so it is graded locally against the exercise's reference
explanation: the learner's answer has to mention at least half of the
significant terms used by the model answer. That keeps grading
deterministic, offline and testable, and the feedback can name the ideas
that were missing instead of only saying "wrong".
"""

import re
from dataclasses import dataclass

#: Fraction of the reference explanation's key terms an answer must mention.
DEFAULT_THRESHOLD = 0.5

#: Shortest significant term; also the shortest stem a suffix may leave.
_MIN_TERM_LENGTH = 3

#: Grammatical filler, lead-in verbs every explanation uses, and other
#: words that carry no SQL meaning. Asking a learner to repeat these would
#: only make grading noisy, so they are not key terms.
_STOPWORDS = frozenset(
    """
    a an the and or but so if then than that this these those
    it its is are was were be been being am
    do does did doing done not no
    of to in into for from on at by with as
    each every all any some both either neither
    which who whom whose what when where how why whether
    you your yours we our ours us they them their theirs
    he she him her his
    one two three
    also only just then there here
    over under out up down
    more most less least
    other another same such per while because
    have has had
    must may might can could should would will shall
    query queries
    return returns returned returning
    list lists listing
    show shows shown
    give gives given
    display displays displayed
    output outputs
    """.split()
)

_SUFFIXES = ("ing", "ed", "es", "s")
_WORD = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class ExplanationGrade:
    """How well an explanation covered the reference answer."""

    is_correct: bool
    coverage: float
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    threshold: float = DEFAULT_THRESHOLD

    @property
    def key_term_count(self) -> int:
        return len(self.matched) + len(self.missing)

    @property
    def is_gradable(self) -> bool:
        """False when the reference answer has no usable key terms."""
        return bool(self.key_term_count)

    @property
    def missing_terms(self) -> str:
        """The missing key terms as a comma-separated list, capped for display."""
        return ", ".join(self.missing[:6])


def key_terms(reference: str) -> tuple[str, ...]:
    """Significant terms of a reference explanation, in first-seen order.

    Terms that differ only by a plural or verb ending are counted once,
    so ``name``/``names`` cannot double-weight the same idea.
    """
    terms: list[str] = []
    seen: set[str] = set()

    for token in _tokens(reference):
        stems = _stems(token)

        if stems & seen:
            continue

        seen |= stems
        terms.append(token)

    return tuple(terms)


def grade_explanation(
    learner: str,
    reference: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> ExplanationGrade:
    """Compare a learner's explanation with the reference answer.

    A reference term counts as mentioned when the learner uses the same
    word, ignoring simple plurals and verb endings (``row``/``rows``,
    ``group``/``grouped``). The answer is correct once it covers
    ``threshold`` of the reference terms.
    """
    terms = key_terms(reference)
    written: set[str] = set()

    for token in _tokens(learner):
        written |= _stems(token)

    matched = tuple(term for term in terms if _stems(term) & written)
    missing = tuple(term for term in terms if term not in matched)
    coverage = len(matched) / len(terms) if terms else 0.0

    return ExplanationGrade(
        is_correct=bool(terms) and coverage >= threshold,
        coverage=coverage,
        matched=matched,
        missing=missing,
        threshold=threshold,
    )


def _tokens(text: object) -> list[str]:
    """Lowercase word tokens, without stopwords or bare numbers.

    ``_`` inside identifiers is treated as a word boundary, so the column
    ``hire_year`` is matched by a learner who writes "hire year".
    """
    tokens = []

    for token in _WORD.findall(str(text or "").lower().replace("_", " ")):
        if len(token) < _MIN_TERM_LENGTH:
            continue

        if token in _STOPWORDS or token.isdigit():
            continue

        tokens.append(token)

    return tokens


def _stems(token: str) -> frozenset[str]:
    """The token plus any common plural/verb ending stripped from it.

    Returning every candidate avoids picking the wrong rule: ``names``
    yields ``names``/``nam``/``name``, so it still matches ``name``, and
    ``classes`` yields ``class`` alongside ``classe``. The ``ed`` ending
    also gets an ``e``-restored variant, so ``hired`` matches ``hire``,
    and consonant + ``y`` plurals map back too (``salaries`` -> ``salary``).
    """
    candidates = {token}

    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= _MIN_TERM_LENGTH:
            candidates.add(token[: -len(suffix)])

    if token.endswith("ed") and len(token) - 2 >= _MIN_TERM_LENGTH:
        candidates.add(token[:-2] + "e")

    if token.endswith("ies") and len(token) - 3 >= _MIN_TERM_LENGTH:
        candidates.add(token[:-3] + "y")

    return frozenset(candidates)
