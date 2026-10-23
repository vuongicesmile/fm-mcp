"""Contract DAG thu dữ liệu; chỉ dùng thư viện chuẩn để Airflow import độc lập."""

STEPS = ("prepare", "validate_source", "capture", "verify_bronze", "load_raw", "canonical", "compile", "transform", "publish", "finalize")
DAG_ID = "fm_data_capture"
RETRIES = {"validate_source": 2, "verify_bronze": 2, "load_raw": 2, "canonical": 2, "publish": 2, "finalize": 3}
