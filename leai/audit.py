from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ToolExecutionAudit(BaseModel):
    """Structured audit record of a single tool execution performed by the AI agent."""

    step: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_output: str = ""
    summary: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    duration_seconds: float = 0.0


class TurnAuditRecord(BaseModel):
    """Complete audit record for a single conversation turn."""

    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    user_prompt: str
    ai_response: str
    provider: str = ""
    model: str = ""
    latency_seconds: float = 0.0
    tokens_used: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    rag_entities: list[str] = Field(default_factory=list)
    tools_executed: list[ToolExecutionAudit] = Field(default_factory=list)


class SessionAuditReport(BaseModel):
    """Aggregate audit report for an entire interactive LEAI session."""

    session_id: str
    start_time: str
    last_updated: str
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    turns: list[TurnAuditRecord] = Field(default_factory=list)


class SessionAuditLogger:
    """Manages persistent session logging and auditing for LEAI AI interactions."""

    def __init__(self, session_id: str | None = None, log_dir: Path | None = None) -> None:
        self.session_id = session_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:6]
        self.start_time = datetime.datetime.now().isoformat()
        self.turns: list[TurnAuditRecord] = []

        # Setup persistent directory in project folder (.leai/sessions)
        if log_dir is not None:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path("./.leai/sessions")

        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = self.log_dir / f"session_{self.session_id}.json"
        except Exception:
            self.log_dir = Path("./.leai_sessions")
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = self.log_dir / f"session_{self.session_id}.json"

    def record_turn(
        self,
        user_prompt: str,
        ai_response: str,
        provider: str = "",
        model: str = "",
        latency_seconds: float = 0.0,
        tokens_used: int = 0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        rag_entities: list[str] | None = None,
        tools_executed: list[ToolExecutionAudit] | None = None,
    ) -> TurnAuditRecord:
        """Records a new conversation turn and automatically flushes the session audit file."""
        record = TurnAuditRecord(
            turn_id=str(len(self.turns) + 1),
            user_prompt=user_prompt,
            ai_response=ai_response,
            provider=provider,
            model=model,
            latency_seconds=round(latency_seconds, 3),
            tokens_used=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            rag_entities=rag_entities or [],
            tools_executed=tools_executed or [],
        )
        self.turns.append(record)
        self._flush_to_disk()
        return record

    def get_last_turn(self) -> TurnAuditRecord | None:
        """Returns the most recent conversation turn audit record."""
        return self.turns[-1] if self.turns else None

    def get_session_summary(self) -> dict[str, Any]:
        """Calculates aggregate statistics for the active session."""
        total_tools = sum(len(t.tools_executed) for t in self.turns)
        total_tokens = sum(t.tokens_used for t in self.turns)
        total_latency = sum(t.latency_seconds for t in self.turns)
        tool_counts: dict[str, int] = {}
        for t in self.turns:
            for te in t.tools_executed:
                tool_counts[te.tool_name] = tool_counts.get(te.tool_name, 0) + 1

        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "total_turns": len(self.turns),
            "total_tool_calls": total_tools,
            "total_tokens": total_tokens,
            "total_latency_seconds": round(total_latency, 2),
            "tool_usage_breakdown": tool_counts,
            "log_file": str(self.log_file.resolve()),
        }

    def export_json(self, output_path: Path | None = None) -> Path:
        """Exports the complete audit log to a standalone JSON file."""
        target = output_path or self.log_file
        target.parent.mkdir(parents=True, exist_ok=True)
        report = SessionAuditReport(
            session_id=self.session_id,
            start_time=self.start_time,
            last_updated=datetime.datetime.now().isoformat(),
            total_turns=len(self.turns),
            total_tool_calls=sum(len(t.tools_executed) for t in self.turns),
            total_tokens=sum(t.tokens_used for t in self.turns),
            turns=self.turns,
        )
        target.write_text(json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def export_markdown(self, output_path: Path | None = None) -> Path:
        """Exports a formal human-readable technical audit report in Markdown."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target = output_path or (self.log_dir / f"audit_report_{self.session_id}.md")
        target.parent.mkdir(parents=True, exist_ok=True)

        summary = self.get_session_summary()
        lines = [
            "# LEAI Session Audit Report",
            "",
            f"- **Session ID:** `{self.session_id}`",
            f"- **Generated At:** `{now}`",
            f"- **Started At:** `{self.start_time}`",
            f"- **Total Questions:** `{summary['total_turns']}`",
            f"- **Total Tool Executions:** `{summary['total_tool_calls']}`",
            f"- **Total Tokens Consumed:** `{summary['total_tokens']:,}`",
            f"- **Total Latency:** `{summary['total_latency_seconds']}s`",
            f"- **Session Audit Log:** `{summary['log_file']}`",
            "",
            "---",
            "",
            "## Tool Usage Breakdown",
            "",
        ]

        if summary["tool_usage_breakdown"]:
            lines.append("| Tool Name | Calls Count |")
            lines.append("| :--- | :--- |")
            for t_name, count in sorted(summary["tool_usage_breakdown"].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| `{t_name}` | **{count}** |")
            lines.append("")
        else:
            lines.append("*No tools were executed during this session.*")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## Interaction Trace Log")
        lines.append("")

        for idx, turn in enumerate(self.turns, 1):
            lines.append(f"### Turn {idx}: `{turn.timestamp}`")
            lines.append(f"- **User Prompt:** *\"{turn.user_prompt}\"*")
            lines.append(f"- **AI Model:** `{turn.provider}:{turn.model}`")
            lines.append(f"- **Turn Latency:** `{turn.latency_seconds}s` • **Tokens:** `{turn.tokens_used:,}`")
            if turn.rag_entities:
                lines.append(f"- **RAG Injected Entities:** {', '.join(f'`{e}`' for e in turn.rag_entities)}")
            lines.append("")

            if turn.tools_executed:
                lines.append("#### 🛠️ Tool Calls Executed:")
                for te in turn.tools_executed:
                    lines.append(f"##### Step {te.step}: `{te.tool_name}` ({te.duration_seconds:.3f}s)")
                    lines.append(f"- **Summary:** {te.summary or 'Completed'}")
                    lines.append("- **Input Arguments:**")
                    lines.append("```json")
                    lines.append(json.dumps(te.arguments, indent=2, ensure_ascii=False))
                    lines.append("```")
                    lines.append("- **Raw Tool Output:**")
                    lines.append("```json")
                    try:
                        parsed = json.loads(te.raw_output)
                        lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except Exception:
                        lines.append(te.raw_output)
                    lines.append("```")
                    lines.append("")

            lines.append("#### 🤖 Final AI Response:")
            lines.append(turn.ai_response)
            lines.append("")
            lines.append("---")
            lines.append("")

        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def _flush_to_disk(self) -> None:
        """Silently updates the active session JSON log file."""
        try:
            self.export_json(self.log_file)
        except Exception:
            pass
