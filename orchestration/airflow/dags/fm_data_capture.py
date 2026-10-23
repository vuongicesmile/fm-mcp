"""DAG hữu hạn dùng chung cho mọi connection BMS/SPO, khởi chạy qua Control Plane."""

from datetime import UTC, datetime, timedelta

from airflow.sdk import dag
from fm_collector_definition import DAG_ID, RETRIES, STEPS
from fm_collector_tasks import execute_capture_step


@dag(dag_id=DAG_ID, schedule=None, start_date=datetime(2026, 1, 1, tzinfo=UTC), catchup=False,
     is_paused_upon_creation=False, max_active_runs=4, max_active_tasks=4,
     dagrun_timeout=timedelta(hours=2), tags=["titan", "collector", "bms", "spo"],
     default_args={"retries": 0, "execution_timeout": timedelta(minutes=30), "retry_delay": timedelta(seconds=30)})
def fm_data_capture():
    previous = None
    for name in STEPS:
        options = {"task_id": name, "retries": RETRIES.get(name, 0)}
        if name == "finalize":
            # Finalizer thất bại nếu có bước trước lỗi; không biến DAG lỗi thành thành công.
            options.update(trigger_rule="all_done", retries=3)
        current = execute_capture_step.override(**options)(name)
        if previous is not None:
            previous >> current
        previous = current


fm_data_capture()
