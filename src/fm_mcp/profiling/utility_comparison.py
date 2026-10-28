"""Read monthly utility comparisons from the configured tenant's cleaned marts."""

import unicodedata
from urllib.parse import urlencode

from fm_mcp.profiling.clickhouse import ClickHouseClient
from fm_mcp.profiling.energy_demo import periods
from fm_mcp.profiling.service import _database_name


def _normalized(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold().replace("đ", "d")) if unicodedata.category(c) != "Mn")


def _match(value: str, *candidates: str) -> bool:
    if not value:
        return True
    if ":" in value:
        return value in candidates
    return any(_normalized(value) in _normalized(candidate or "") for candidate in candidates)


def energy_comparison(building: str = "", equipment: str = "", metric: str = "electricity", object_type: str = "", group_by: str = "building") -> dict:
    """Compare equal completed-day windows without manufacturing missing readings."""
    if metric not in {"electricity", "water"} or group_by not in {"building", "equipment", "object_type"}:
        raise ValueError("Unsupported comparison metric or grouping")
    if object_type not in {"", "Energy", "Consumption", "WaterConsumption"}:
        raise ValueError("Unsupported comparison object type")
    if len(building) > 200 or len(equipment) > 200:
        raise ValueError("Utility comparison filter is too long")
    schema = _database_name("marts")
    table = f"`{schema}`.agg_meter_daily"
    kind, canonical_unit, unit = ("Energy", "kWh", "kWh") if metric == "electricity" else ("WaterConsumption", "m3", "m³")
    previous, current, days = periods()
    client = ClickHouseClient()
    parameters = {"metric": metric, "unit": canonical_unit, "previous": str(previous), "current": str(current), "days": str(days)}
    limits = "SETTINGS max_execution_time=20, max_result_rows=20000, result_overflow_mode='throw', readonly=2, join_use_nulls=1"

    buildings = client.query_json(f"SELECT building_id,name FROM `{schema}`.rpt_building ORDER BY building_id {limits}")
    meter_table = "dim_electric_meter" if metric == "electricity" else "dim_water_meter"
    equipment_type = "ElectricityMeter" if metric == "electricity" else "WaterMeter"
    catalog = client.query_json(f"""SELECT meter_id AS id,building_id,meter_id AS name,data_origin
        FROM `{schema}`.{meter_table}
        UNION DISTINCT SELECT equipment_id AS id,building_id,coalesce(name,equipment_id) AS name,data_origin
        FROM `{schema}`.rpt_equipment WHERE equipment_type={{equipment_type:String}} {limits}""",
        parameters={"equipment_type": equipment_type})

    # Dùng consumption đã chuẩn hóa bởi Marts; không cộng chỉ số tích lũy hoặc công suất.
    valid = "consumption IS NOT NULL AND consumption>=0 AND valid_reading_count>0"
    clean = f"({valid}) AND expected_hours=24 AND hours_with_data=24 AND missing_hours=0 AND source_missing_count=0 AND reset_count=0 AND gap_count=0 AND spike_count=0 AND out_of_range_count=0 AND critical_count=0"
    windows = {
        "previous": "period_date>={previous:Date} AND period_date<addDays({previous:Date},{days:UInt32})",
        "current": "period_date>={current:Date} AND period_date<addDays({current:Date},{days:UInt32})",
    }
    fields = []
    for prefix, window in windows.items():
        fields.extend([
            f"toFloat64(sumIf(consumption,({window}) AND ({valid}))) AS {prefix}_sum",
            f"uniqExactIf(period_date,({window}) AND ({valid})) AS {prefix}_days",
            f"uniqExactIf(period_date,({window}) AND ({clean})) AS {prefix}_complete_days",
        ])
    series = client.query_json(f"""SELECT building_id,building_name,meter_id,equipment_id,object_id,
        source_system,connection_id,object_type,meter_level,
        minIf(period_date,{valid}) AS first_date,maxIf(period_date,{valid}) AS last_date,
        countIf({valid}) AS available_days,{','.join(fields)}
        FROM {table} WHERE utility={{metric:String}} AND canonical_unit={{unit:String}}
        AND value_kind IN ('interval','register')
        GROUP BY building_id,building_name,meter_id,equipment_id,object_id,source_system,connection_id,object_type,meter_level
        ORDER BY building_id,meter_id,object_id {limits}""", parameters=parameters)

    names = {row["building_id"]: row["name"] for row in buildings}
    selected_catalog = [row for row in catalog if _match(building, row["building_id"], names.get(row["building_id"], ""))]
    equipment_names = {row["id"]: row["name"] for row in catalog}
    source_series = [row for row in series if _match(building, row["building_id"], row["building_name"])]
    equipment_options = {row["id"]: row["name"] for row in selected_catalog}
    for row in source_series:
        key = row["equipment_id"] or row["meter_id"] or row["object_id"]
        equipment_options[key] = equipment_names.get(key, key)

    rows = []
    accepted_types = {kind, "Consumption"} if metric == "water" else {kind}
    for row in source_series:
        equipment_id = row["equipment_id"] or row["meter_id"] or row["object_id"]
        if not _match(equipment, equipment_id, row["meter_id"], row["object_id"], equipment_names.get(equipment_id, "")):
            continue
        if object_type and object_type not in accepted_types:
            continue
        # Khi không chọn thiết bị, loại công tơ nhánh để không cộng Main + HVAC.
        if metric == "electricity" and not equipment and (row["meter_level"] or "").casefold() not in {"", "main"}:
            continue
        item = dict(row, building=row["building_name"], meter=row["meter_id"] or equipment_id,
                    equipment_name=equipment_names.get(equipment_id, equipment_id))
        for prefix in windows:
            item[f"{prefix}_value"] = row[f"{prefix}_sum"] if row[f"{prefix}_days"] else None
            # Tách ngày chưa có tiêu thụ khỏi ngày có số nhưng chưa đạt chất lượng.
            item[f"{prefix}_missing_days"] = max(0, days - row[f"{prefix}_days"])
            item[f"{prefix}_rejected_days"] = max(0, row[f"{prefix}_days"] - row[f"{prefix}_complete_days"])
        item["complete"] = days > 0 and all(row[f"{p}_complete_days"] == days for p in windows)
        item["change_pct"] = round(100 * (item["current_value"] - item["previous_value"]) / item["previous_value"], 2) if item["complete"] and item["previous_value"] else None
        rows.append(item)

    # Giữ khóa nguồn, không hợp nhất các tòa nhà trùng tên từ hai connection.
    groups = {}
    for row in rows:
        if not row["complete"]:
            continue
        key = row["building_id"] if group_by == "building" else row["object_id"] if group_by == "equipment" else row["object_type"]
        label = f"{row['building']} · {row['building_id']}" if group_by == "building" else f"{row['equipment_name']} · {row['object_id']}" if group_by == "equipment" else row["object_type"]
        group = groups.setdefault(key, {"label": label, "previous_value": 0, "current_value": 0})
        for prefix in windows:
            group[f"{prefix}_value"] += row[f"{prefix}_value"]

    complete = bool(rows) and all(row["complete"] for row in rows)
    totals = {p: sum(row[f"{p}_value"] or 0 for row in rows) if any(row[f"{p}_value"] is not None for row in rows) else None for p in windows}
    change = round(100 * (totals["current"] - totals["previous"]) / totals["previous"], 2) if complete and totals["previous"] else None
    daily = []
    if complete:
        ids = {f"object_{i}": row["object_id"] for i, row in enumerate(rows)}
        selected = ",".join(f"{{{key}:String}}" for key in ids)
        daily = client.query_json(f"""SELECT toDayOfMonth(period_date) AS day,
            toFloat64(sumIf(consumption,{windows['previous']})) AS previous_value,
            toFloat64(sumIf(consumption,{windows['current']})) AS current_value
            FROM {table} WHERE utility={{metric:String}} AND canonical_unit={{unit:String}}
            AND object_id IN ({selected}) AND ({valid})
            AND (({windows['previous']}) OR ({windows['current']}))
            GROUP BY day ORDER BY day {limits}""", parameters={**parameters, **ids})

    available = [row for row in rows if row["available_days"]]
    coverage = {"first_date": min((row["first_date"] for row in available), default=None),
                "last_date": max((row["last_date"] for row in available), default=None),
                "meters": len(rows), "complete_meters": sum(row["complete"] for row in rows)}
    coverage["periods"] = {
        prefix: {"start": str(start), "expected_meter_days": len(rows) * days,
                 "valid_meter_days": sum(row[f"{prefix}_days"] for row in rows),
                 "complete_meter_days": sum(row[f"{prefix}_complete_days"] for row in rows),
                 "missing_meter_days": sum(row[f"{prefix}_missing_days"] for row in rows),
                 "rejected_meter_days": sum(row[f"{prefix}_rejected_days"] for row in rows)}
        for prefix, start in (("previous", previous), ("current", current))
    }
    coverage["reason"] = ("no_matching_history" if not rows else "no_completed_days" if not days
                          else "missing_history" if any(row[f"{p}_missing_days"] for row in rows for p in windows)
                          else "incomplete_quality" if not complete else "complete")
    origins = sorted({row["data_origin"] for row in selected_catalog if row["data_origin"]})
    warnings = ["Các mã có tiền tố nguồn được giữ riêng; chưa hợp nhất cùng một tòa nhà giữa các nguồn."]
    if metric == "electricity" and not equipment:
        warnings.append("Mặc định lấy công tơ Main và điểm đo chưa phân cấp; không cộng nhánh HVAC với công tơ chính. Chọn thiết bị để xem riêng công tơ nhánh.")
    if metric == "water":
        warnings.append("Danh mục nước chưa phân cấp công tơ chính/nhánh; tổng là tổng các điểm đo, chưa bảo đảm là tổng tiêu thụ toàn tòa nhà.")
    if any("synthetic" in origin.casefold() or "demo" in origin.casefold() for origin in origins):
        warnings.append("Nguồn đã nhập có dữ liệu mô phỏng; đây không phải xác nhận số đo vận hành thực.")
    if change is not None:
        message = f"{'Điện năng' if metric == 'electricity' else 'Nước tiêu thụ'} trong {days} ngày hoàn tất đầu tháng {current:%m/%Y}: {totals['current']:,.2f} {unit}; cùng kỳ tháng {previous:%m/%Y}: {totals['previous']:,.2f} {unit}; thay đổi {change:+.2f}%."
    elif complete:
        message = "Kỳ trước ghi nhận tiêu thụ bằng 0; không tính phần trăm thay đổi vì không có mẫu số hợp lệ."
    else:
        message = "Chưa đủ dữ liệu hợp lệ hai kỳ để so sánh; không tính tỷ lệ thay đổi và không điền số 0 cho dữ liệu thiếu." if rows else "Không tìm thấy lịch sử tiêu thụ phù hợp với bộ lọc. Danh mục tòa nhà không đồng nghĩa đã có lịch sử đo."
        if rows and not days:
            message = "Hôm nay là ngày đầu tháng; chưa có ngày hoàn tất để so sánh cùng kỳ. Không bao gồm ngày đang diễn ra."
        if rows and days:
            for prefix, start in (("previous", previous), ("current", current)):
                period = coverage["periods"][prefix]
                message += (f" Tháng {start:%m/%Y}: {period['complete_meter_days']}/{period['expected_meter_days']} ngày-công tơ đạt điều kiện;"
                            f" {period['missing_meter_days']} ngày chưa có tiêu thụ hợp lệ,"
                            f" {period['rejected_meter_days']} ngày chưa đạt độ phủ/chất lượng.")
        if coverage["last_date"]:
            message += f" Lịch sử tiêu thụ hiện có từ {coverage['first_date']} đến {coverage['last_date']}."
        if rows and days:
            message += " Cần đồng bộ lịch sử của hai kỳ và chạy chuyển đổi Marts; đổi bộ lọc hoặc tải lại không tự bổ sung dữ liệu nguồn."
    filters = {"building": building, "equipment": equipment, "metric": metric, "object_type": object_type, "group_by": group_by}
    return {"demo": False, "dataset": table, "source": f"{schema}: agg_meter_daily, rpt_building, {meter_table}, rpt_equipment",
            "data_origins": origins, "warnings": warnings, "coverage": coverage,
            "metric": metric, "unit": unit, "previous_value": totals["previous"], "current_value": totals["current"],
            "groups": list(groups.values()), "daily": daily, "previous_month": str(previous), "current_month": str(current),
            "days": days, "complete": complete, "change_pct": change, "rows": rows, "filters": filters,
            "options": {"building": [row["building_id"] for row in buildings], "equipment": sorted(equipment_options), "object_type": [kind]},
            "option_labels": {"building": {key: f"{name} · {key}" for key, name in names.items()},
                              "equipment": {key: f"{name} · {key}" if name != key else key for key, name in equipment_options.items()}},
            "dashboard_url": "/dashboards/energy-comparison?" + urlencode({k: v for k, v in filters.items() if v}),
            "message": message}
