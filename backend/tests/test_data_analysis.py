import json
from pathlib import Path
import pandas as pd
import pytest

from agents.data_analysis.analyser import DataAnalysisAgent, data_analysis_adapter, Dataset
from agents.data_analysis.calculator import (
    statistics,
    detect_trends,
    detect_anomalies,
    compute_correlations,
)
from agents.orchestrator.planner import TaskPlanner
from agents.orchestrator.state import AgentContext, AgentTask


def test_data_analysis_adapter_csv(tmp_path):
    csv_file = tmp_path / "sensor_data.csv"
    csv_file.write_text(
        "timestamp,temperature,pressure\n"
        "2025-01-01 00:00,45.0,2.5\n"
        "2025-01-01 01:00,46.2,2.6\n"
        "2025-01-01 02:00,48.1,2.8\n",
        encoding="utf-8"
    )
    
    task = AgentTask(agent_name="data_analysis", instruction="Analyze trends and highest temperature")
    context = AgentContext(task=task, files=[str(csv_file)], user_request="What is the average and highest temperature?")
    
    result = data_analysis_adapter(context)
    assert result.status == "completed"
    assert len(result.data["datasets"]) >= 1
    dataset = result.data["datasets"][0]
    assert dataset["row_count"] == 3
    assert "temperature" in dataset["statistics"]
    assert dataset["statistics"]["temperature"]["max"] == 48.1
    assert dataset["statistics"]["temperature"]["min"] == 45.0
    assert len(result.artifacts) >= 1


def test_data_analysis_json_loading(tmp_path):
    json_file = tmp_path / "telemetry.json"
    data = [
        {"equipment": "Pump-A", "vibration": 1.2, "temperature": 55.0},
        {"equipment": "Pump-A", "vibration": 1.4, "temperature": 56.5},
        {"equipment": "Pump-A", "vibration": 1.8, "temperature": 58.0},
        {"equipment": "Pump-A", "vibration": 2.1, "temperature": 60.2},
    ]
    json_file.write_text(json.dumps(data), encoding="utf-8")

    agent = DataAnalysisAgent(output_directory=str(tmp_path / "out"))
    datasets = agent.load_file(str(json_file))
    assert len(datasets) == 1
    res = agent.analyze(datasets[0])
    assert res["row_count"] == 4
    assert "vibration" in res["statistics"]
    assert res["statistics"]["vibration"]["mean"] == 1.625


def test_data_analysis_tsv_txt_loading(tmp_path):
    txt_file = tmp_path / "readings.txt"
    txt_file.write_text(
        "machine\tspeed\ttorque\n"
        "M1\t1500\t120.5\n"
        "M1\t1520\t122.0\n"
        "M1\t1510\t121.2\n",
        encoding="utf-8"
    )

    agent = DataAnalysisAgent(output_directory=str(tmp_path / "out"))
    datasets = agent.load_file(str(txt_file))
    assert len(datasets) == 1
    res = agent.analyze(datasets[0])
    assert res["row_count"] == 3
    assert "speed" in res["numeric_columns"]


def test_statistics_comprehensive():
    df = pd.DataFrame({
        "a": [10.0, 20.0, 30.0, 40.0, 50.0],
        "b": ["x", "y", "z", "w", "v"],
    })
    stats = statistics(df)
    assert "a" in stats
    assert "b" not in stats
    assert stats["a"]["count"] == 5
    assert stats["a"]["mean"] == 30.0
    assert stats["a"]["median"] == 30.0
    assert stats["a"]["min"] == 10.0
    assert stats["a"]["max"] == 50.0


def test_trend_detection():
    df = pd.DataFrame({
        "temp_rising": [20.0, 25.0, 30.0, 35.0, 40.0],
        "temp_falling": [50.0, 45.0, 40.0, 35.0, 30.0],
        "temp_stable": [25.0, 25.0, 25.0, 25.0, 25.0],
    })
    trends = detect_trends(df, ["temp_rising", "temp_falling", "temp_stable"])
    assert trends["temp_rising"]["direction"] == "increasing"
    assert trends["temp_falling"]["direction"] == "decreasing"
    assert trends["temp_stable"]["direction"] == "stable"


def test_anomaly_detection_iqr():
    # Regular values around 10-12, one extreme outlier at 100.0
    df = pd.DataFrame({
        "temp": [10.0, 10.2, 10.1, 10.5, 10.3, 10.4, 10.2, 100.0],
    })
    anomalies = detect_anomalies(df, ["temp"])
    assert len(anomalies) >= 1
    assert anomalies[0]["column"] == "temp"
    assert anomalies[0]["value"] == 100.0
    assert anomalies[0]["bound_exceeded"] == "high"


def test_correlation_calculation():
    df = pd.DataFrame({
        "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y": [2.0, 4.0, 6.0, 8.0, 10.0],
        "z": [5.0, 4.0, 3.0, 2.0, 1.0],
    })
    corrs = compute_correlations(df, ["x", "y", "z"])
    assert corrs["x"]["y"] == 1.0
    assert corrs["x"]["z"] == -1.0


def test_empty_or_invalid_file_handling(tmp_path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    agent = DataAnalysisAgent(output_directory=str(tmp_path / "out"))

    with pytest.raises(ValueError):
        agent.load_file(str(empty_csv))


def test_planner_routing_to_data_analysis():
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Analyze the sensor vibration trends and detect statistical anomalies in the dataset",
        files=["readings.csv"],
    )
    assert plan.intent == "DATA_ANALYSIS"
    assert "data_analysis" in plan.planned_agents
