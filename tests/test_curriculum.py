from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.learning.curriculum import Curriculum


def test_curriculum_contains_ordered_topics() -> None:
    curriculum = Curriculum.default()

    topics = curriculum.topics

    assert len(topics) > 0
    assert topics[0].title == "SELECT"
    assert topics[0].difficulty == ExerciseDifficulty.BEGINNER

    orders = [topic.order for topic in topics]
    assert orders == sorted(orders)


def test_curriculum_returns_topic_by_concept() -> None:
    curriculum = Curriculum.default()

    topic = curriculum.get_topic("WHERE")

    assert topic is not None
    assert topic.title == "WHERE"


def test_curriculum_returns_none_for_unknown_concept() -> None:
    curriculum = Curriculum.default()

    assert curriculum.get_topic("UNKNOWN") is None

def test_curriculum_covers_core_and_advanced_sql_topics() -> None:
    curriculum = Curriculum.default()
    titles = {topic.title for topic in curriculum.topics}

    required = {
        "SELECT",
        "WHERE",
        "GROUP BY",
        "JOIN",
        "COMMON TABLE EXPRESSIONS",
        "RECURSIVE CTE",
        "WINDOW FUNCTIONS",
        "WINDOW FRAMES",
        "RANKING FUNCTIONS",
        "LAG AND LEAD",
        "TRANSACTIONS",
        "INDEXES",
    }

    assert required <= titles
    assert len(curriculum.topics) >= 40


def test_curriculum_orders_are_contiguous() -> None:
    curriculum = Curriculum.default()
    assert [topic.order for topic in curriculum.topics] == list(
        range(1, len(curriculum.topics) + 1)
    )
