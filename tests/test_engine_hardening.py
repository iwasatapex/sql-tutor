import sqlite3

import pytest

from sql_tutor.sql.engine import SQLEngine


def test_runaway_query_is_interrupted() -> None:
    engine = SQLEngine(query_timeout_seconds=0.2)

    with pytest.raises(sqlite3.OperationalError):
        engine.execute_query(
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
            "SELECT COUNT(*) FROM c;"
        )

    engine.close()


def test_engine_still_works_after_a_timeout() -> None:
    engine = SQLEngine(query_timeout_seconds=0.2)

    with pytest.raises(sqlite3.OperationalError):
        engine.execute_query(
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
            "SELECT COUNT(*) FROM c;"
        )

    assert engine.execute_query("SELECT 1;").rows == ((1,),)
    engine.close()


def test_row_cap_is_enforced() -> None:
    engine = SQLEngine(max_rows=10)

    with pytest.raises(ValueError, match="more than 10 rows"):
        engine.execute_query(
            "WITH RECURSIVE c(x) AS "
            "(SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 100) "
            "SELECT x FROM c;"
        )

    engine.close()


def test_setup_still_works_after_queries_ran() -> None:
    engine = SQLEngine()
    engine.execute_setup(["CREATE TABLE a (x INTEGER)"])
    engine.execute_query("SELECT * FROM a;")
    engine.execute_setup(["INSERT INTO a VALUES (1)"])

    assert engine.execute_query("SELECT x FROM a;").rows == ((1,),)
    engine.close()
