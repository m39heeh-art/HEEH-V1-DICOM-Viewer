from app import ClinicalApp


def test_latest_model_metrics_compares_normalized_timestamps_and_mtime_fallback():
    metrics = [
        {
            "model_id": "newest-offset",
            "finished_at": "2024-01-01T10:30:00-05:00",
        },
        {
            "model_id": "older-utc",
            "finished_at": "2024-01-01T15:00:00Z",
        },
        {
            "model_id": "newer-mtime",
            "metrics_mtime_utc": "2024-01-01T16:00:00+00:00",
        },
    ]

    assert ClinicalApp._latest_model_metrics(metrics[:2])["model_id"] == (
        "newest-offset"
    )
    assert ClinicalApp._latest_model_metrics(metrics)["model_id"] == "newer-mtime"


def test_invalid_explicit_model_timestamp_falls_back_to_file_mtime():
    metrics = [
        {
            "model_id": "invalid-explicit",
            "finished_at": "not-a-timestamp",
            "metrics_mtime_utc": "2024-01-01T15:00:00Z",
        },
        {
            "model_id": "newest",
            "finished_at": "2024-01-01T15:30:00+00:00",
        },
    ]

    assert ClinicalApp._latest_model_metrics(metrics)["model_id"] == "newest"
