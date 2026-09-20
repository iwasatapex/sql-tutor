from dataclasses import dataclass

from sql_tutor.exercises.models import ExerciseDifficulty


@dataclass(frozen=True)
class CurriculumTopic:
    title: str
    description: str
    difficulty: ExerciseDifficulty
    order: int

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Topic title cannot be empty")

        if not self.description.strip():
            raise ValueError("Topic description cannot be empty")

        if self.order < 1:
            raise ValueError("Topic order must be at least 1")


class Curriculum:
    def __init__(self, topics: tuple[CurriculumTopic, ...]) -> None:
        if not topics:
            raise ValueError("Curriculum must contain at least one topic")

        orders = [topic.order for topic in topics]

        if len(set(orders)) != len(orders):
            raise ValueError("Topic orders must be unique")

        self.topics = tuple(
            sorted(topics, key=lambda topic: topic.order)
        )

    @classmethod
    def default(cls) -> "Curriculum":
        return cls(
            topics=(
                CurriculumTopic(
                    title="SELECT",
                    description="Retrieve data from one or more columns.",
                    difficulty=ExerciseDifficulty.BEGINNER,
                    order=1,
                ),
                CurriculumTopic(
                    title="WHERE",
                    description="Filter rows using conditions.",
                    difficulty=ExerciseDifficulty.BEGINNER,
                    order=2,
                ),
                CurriculumTopic(
                    title="ORDER BY",
                    description="Sort query results.",
                    difficulty=ExerciseDifficulty.BEGINNER,
                    order=3,
                ),
                CurriculumTopic(
                    title="GROUP BY",
                    description="Group rows for aggregate calculations.",
                    difficulty=ExerciseDifficulty.INTERMEDIATE,
                    order=4,
                ),
                CurriculumTopic(
                    title="JOIN",
                    description="Combine data from multiple tables.",
                    difficulty=ExerciseDifficulty.INTERMEDIATE,
                    order=5,
                ),
                CurriculumTopic(
                    title="SUBQUERY",
                    description="Use a query inside another query.",
                    difficulty=ExerciseDifficulty.ADVANCED,
                    order=6,
                ),
            )
        )

    def get_topic(self, concept: str) -> CurriculumTopic | None:
        normalized_concept = concept.strip().upper()

        for topic in self.topics:
            if topic.title.upper() == normalized_concept:
                return topic

        return None