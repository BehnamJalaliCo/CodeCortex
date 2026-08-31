import pytest

from codecortex.tracing import TaskTraceRecorder


def test_task_trace_records_redacts_and_summarizes(tmp_path) -> None:
    recorder = TaskTraceRecorder(tmp_path / "traces.jsonl")
    trace_id = recorder.new_trace_id()
    with recorder.span(
        "tool.search",
        trace_id=trace_id,
        attributes={"context_tokens": 120, "api_key": "secret"},
    ):
        pass
    summary = recorder.summarize(trace_id)
    records = recorder.read(trace_id)
    assert summary.tool_calls == 1
    assert summary.context_tokens == 120
    assert records[0].attributes["api_key"] == "[REDACTED]"


def test_task_trace_records_errors(tmp_path) -> None:
    recorder = TaskTraceRecorder(tmp_path / "traces.jsonl")
    trace_id = recorder.new_trace_id()
    with pytest.raises(RuntimeError):
        with recorder.span("engine.execute", trace_id=trace_id):
            raise RuntimeError("boom")
    assert recorder.summarize(trace_id).errors == 1
