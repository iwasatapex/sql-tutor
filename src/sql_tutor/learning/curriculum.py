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
    """The complete SQLite-focused SQL learning path.

    Topics are intentionally explicit so the adaptive selector and LLM
    generator can target a concrete SQL skill instead of producing generic
    beginner exercises.
    """

    def __init__(self, topics: tuple[CurriculumTopic, ...]) -> None:
        if not topics:
            raise ValueError("Curriculum must contain at least one topic")

        orders = [topic.order for topic in topics]

        if len(set(orders)) != len(orders):
            raise ValueError("Topic orders must be unique")

        self.topics = tuple(sorted(topics, key=lambda topic: topic.order))

    @classmethod
    def default(cls) -> "Curriculum":
        specs: tuple[tuple[str, str, ExerciseDifficulty], ...] = (
            ("SELECT", "Retrieve columns and rows from tables.", ExerciseDifficulty.BEGINNER),
            ("WHERE", "Filter rows with comparisons, boolean logic, and predicates.", ExerciseDifficulty.BEGINNER),
            ("DISTINCT", "Remove duplicate result rows.", ExerciseDifficulty.BEGINNER),
            ("NULL", "Work safely with NULL, IS NULL, COALESCE, and NULL semantics.", ExerciseDifficulty.BEGINNER),
            ("OPERATORS", "Use arithmetic, comparison, boolean, LIKE, GLOB, IN, and BETWEEN operators.", ExerciseDifficulty.BEGINNER),
            ("CASE", "Create conditional values with CASE expressions.", ExerciseDifficulty.BEGINNER),
            ("BUILT-IN FUNCTIONS", "Use SQLite scalar, string, numeric, and conditional functions.", ExerciseDifficulty.INTERMEDIATE),
            ("DATE AND TIME", "Use SQLite date, time, datetime, and julianday functions.", ExerciseDifficulty.INTERMEDIATE),
            ("ORDER BY", "Sort results with multiple keys, expressions, and NULL handling.", ExerciseDifficulty.BEGINNER),
            ("LIMIT AND OFFSET", "Paginate and restrict result sets.", ExerciseDifficulty.BEGINNER),
            ("GROUP BY", "Group rows for aggregate calculations.", ExerciseDifficulty.INTERMEDIATE),
            ("AGGREGATES", "Use COUNT, SUM, AVG, MIN, MAX, and aggregate expressions.", ExerciseDifficulty.INTERMEDIATE),
            ("HAVING", "Filter grouped results after aggregation.", ExerciseDifficulty.INTERMEDIATE),
            ("JOIN", "Combine matching rows from multiple tables with INNER JOIN semantics.", ExerciseDifficulty.INTERMEDIATE),
            ("LEFT JOIN", "Preserve rows from the left table while joining optional data.", ExerciseDifficulty.INTERMEDIATE),
            ("CROSS JOIN", "Build Cartesian products and understand join cardinality.", ExerciseDifficulty.INTERMEDIATE),
            ("SELF JOIN", "Join a table to itself for hierarchical and relationship queries.", ExerciseDifficulty.INTERMEDIATE),
            ("UNION", "Combine compatible result sets while removing duplicates.", ExerciseDifficulty.INTERMEDIATE),
            ("UNION ALL", "Combine result sets while preserving duplicates.", ExerciseDifficulty.INTERMEDIATE),
            ("INTERSECT AND EXCEPT", "Compare and subtract compatible result sets.", ExerciseDifficulty.ADVANCED),
            ("SUBQUERY", "Use scalar, list, and correlated subqueries.", ExerciseDifficulty.ADVANCED),
            ("EXISTS", "Use EXISTS and NOT EXISTS for relationship-based filtering.", ExerciseDifficulty.ADVANCED),
            ("COMMON TABLE EXPRESSIONS", "Use WITH clauses to structure multi-step queries.", ExerciseDifficulty.ADVANCED),
            ("RECURSIVE CTE", "Traverse trees, graphs, and generated sequences recursively.", ExerciseDifficulty.ADVANCED),
            ("WINDOW FUNCTIONS", "Calculate values across related rows without collapsing them.", ExerciseDifficulty.ADVANCED),
            ("WINDOW PARTITIONING", "Use PARTITION BY for per-group window calculations.", ExerciseDifficulty.ADVANCED),
            ("WINDOW FRAMES", "Use ROWS and RANGE frames for running and moving calculations.", ExerciseDifficulty.ADVANCED),
            ("RANKING FUNCTIONS", "Use ROW_NUMBER, RANK, and DENSE_RANK.", ExerciseDifficulty.ADVANCED),
            ("LAG AND LEAD", "Compare each row with previous and following rows.", ExerciseDifficulty.ADVANCED),
            ("RUNNING AND MOVING AGGREGATES", "Use aggregate window functions for cumulative and moving metrics.", ExerciseDifficulty.ADVANCED),
            ("CREATE TABLE", "Define tables, columns, and SQLite data types.", ExerciseDifficulty.INTERMEDIATE),
            ("CONSTRAINTS", "Use PRIMARY KEY, NOT NULL, UNIQUE, CHECK, and FOREIGN KEY constraints.", ExerciseDifficulty.INTERMEDIATE),
            ("INSERT", "Insert single and multiple rows safely.", ExerciseDifficulty.INTERMEDIATE),
            ("UPDATE", "Modify rows with precise, safe predicates.", ExerciseDifficulty.INTERMEDIATE),
            ("DELETE", "Delete selected rows while avoiding unintended data loss.", ExerciseDifficulty.INTERMEDIATE),
            ("UPSERT", "Use INSERT ... ON CONFLICT for insert-or-update workflows.", ExerciseDifficulty.ADVANCED),
            ("TRANSACTIONS", "Use BEGIN, COMMIT, ROLLBACK, and savepoints.", ExerciseDifficulty.ADVANCED),
            ("VIEWS", "Create and query reusable views.", ExerciseDifficulty.ADVANCED),
            ("INDEXES", "Create indexes and reason about lookup performance.", ExerciseDifficulty.ADVANCED),
            ("EXPLAIN QUERY PLAN", "Inspect SQLite query plans and identify index usage.", ExerciseDifficulty.ADVANCED),
            ("PRAGMAS", "Use relevant SQLite PRAGMA statements safely.", ExerciseDifficulty.ADVANCED),
            ("JSON FUNCTIONS", "Query and transform JSON using SQLite JSON functions when available.", ExerciseDifficulty.ADVANCED),
            ("QUERY COMPOSITION", "Combine joins, CTEs, aggregates, windows, and subqueries in realistic problems.", ExerciseDifficulty.ADVANCED),
            ("SQL DEBUGGING", "Diagnose syntax, schema, NULL, cardinality, and logic errors.", ExerciseDifficulty.ADVANCED),
        )

        topics = tuple(
            CurriculumTopic(
                title=title,
                description=description,
                difficulty=difficulty,
                order=index,
            )
            for index, (title, description, difficulty) in enumerate(specs, start=1)
        )
        return cls(topics=topics)

    def get_topic(self, concept: str) -> CurriculumTopic | None:
        normalized_concept = concept.strip().upper()

        for topic in self.topics:
            if topic.title.upper() == normalized_concept:
                return topic

        return None
