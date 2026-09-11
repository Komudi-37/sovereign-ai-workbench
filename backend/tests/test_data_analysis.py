from pathlib import Path
from agents.data_analysis.analyser import data_analysis_adapter
from agents.orchestrator.state import AgentContext, AgentTask

def test_data_analysis_adapter_csv(tmp_path):
    csv_file = tmp_path / "sensor_data.csv"
    csv_file.write_text("timestamp,temperature,pressure\n2025-01-01 00:00,45.0,2.5\n2025-01-01 01:00,46.2,2.6\n2025-01-01 02:00,48.1,2.8\n", encoding="utf-8")
    
    task = AgentTask(agent_name="data_analysis", instruction="Analyze trends")
    context = AgentContext(task=task, files=[str(csv_file)])
    
    result = data_analysis_adapter(context)
    assert result.status == "completed"
    assert len(result.data["datasets"]) >= 1
    assert len(result.artifacts) >= 1  # Charts or analyzed data CSV
