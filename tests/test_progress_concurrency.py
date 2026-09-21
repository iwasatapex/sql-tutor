from concurrent.futures import ThreadPoolExecutor

from sql_tutor.storage.progress import ProgressStore


def test_file_backed_progress_store_supports_concurrent_writes(tmp_path):
    path = tmp_path / "progress.db"
    store = ProgressStore(str(path))

    def write(index: int) -> None:
        store.record_attempt(f"exercise-{index % 3}", f"SELECT {index};", index % 2 == 0)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))

    assert len(store.get_all_attempts()) == 40
    store.close()

    reopened = ProgressStore(str(path))
    assert len(reopened.get_all_attempts()) == 40
    reopened.close()
