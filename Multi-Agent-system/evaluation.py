# =====================================================================
# evaluation.py
#
# Evaluation & Debugging module for the multi-agent blog-writing pipeline.
#
# EvaluationEngine – per-agent timing, structured tracing, LLM-based
#                    quality scoring, debug logging, and summary reports
# =====================================================================

import time
import json
import dataclasses
from datetime import datetime, timezone


@dataclasses.dataclass
class TraceEntry:
    step_name: str
    timestamp: str
    duration_seconds: float
    input_keys: list
    output_keys: list
    details: str = ""


class EvaluationEngine:
    """Pipeline-wide performance tracking and quality evaluation."""

    def __init__(self, debug=False, gemini_caller=None):
        self.debug = debug
        self._gemini_caller = gemini_caller
        self._timings = {}
        self._traces = []
        self._pipeline_start = None
        self._pipeline_end = None
        self._active_timers = {}

    # ── Pipeline timing ──────────────────────────────────────────────

    def start_pipeline(self):
        self._pipeline_start = time.time()
        if self.debug:
            print(f"[DEBUG] Pipeline started at {datetime.now(timezone.utc).isoformat()}")

    def end_pipeline(self):
        self._pipeline_end = time.time()
        if self.debug:
            elapsed = self._pipeline_end - self._pipeline_start
            print(f"[DEBUG] Pipeline finished. Total: {elapsed:.1f}s")

    # ── Agent timing ─────────────────────────────────────────────────

    def start_agent(self, agent_name):
        self._active_timers[agent_name] = time.time()
        if self.debug:
            print(f"[DEBUG] Starting {agent_name} at {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

    def end_agent(self, agent_name, input_keys=None, output_keys=None, details=""):
        start = self._active_timers.pop(agent_name, None)
        if start is None:
            return

        duration = time.time() - start
        self._timings.setdefault(agent_name, []).append(duration)

        entry = TraceEntry(
            step_name=agent_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=round(duration, 2),
            input_keys=input_keys or [],
            output_keys=output_keys or [],
            details=details,
        )
        self._traces.append(entry)

        if self.debug:
            print(f"[DEBUG] {agent_name} completed in {duration:.1f}s "
                  f"| output: {output_keys or '(none)'}")

    # ── Quality scoring ──────────────────────────────────────────────

    def score_quality(self, draft, plan, research_notes=""):
        if not self._gemini_caller:
            return {"clarity": -1, "accuracy": -1, "completeness": -1,
                    "engagement": -1, "overall": -1, "feedback": "No LLM caller configured"}

        system_prompt = """You are a blog quality evaluator. Score the draft against the plan on these dimensions (1-10 each).
Respond in EXACTLY this format:

CLARITY: <score>
ACCURACY: <score>
COMPLETENESS: <score>
ENGAGEMENT: <score>
FEEDBACK: <one paragraph of constructive feedback>"""

        user_prompt = f"Plan:\n{plan[:2000]}\n\nResearch notes:\n{research_notes[:2000]}\n\nDraft:\n{draft[:3000]}"

        try:
            result = self._gemini_caller(system_prompt, user_prompt)

            scores = {}
            for dim in ("CLARITY", "ACCURACY", "COMPLETENESS", "ENGAGEMENT"):
                line = next((l for l in result.splitlines() if l.strip().startswith(f"{dim}:")), "")
                try:
                    val = int("".join(c for c in line.split(":", 1)[1] if c.isdigit())[:2])
                    scores[dim.lower()] = min(max(val, 1), 10)
                except (ValueError, IndexError):
                    scores[dim.lower()] = -1

            feedback = ""
            if "FEEDBACK:" in result:
                feedback = result.split("FEEDBACK:", 1)[1].strip()

            dims = [v for v in scores.values() if v > 0]
            overall = round(sum(dims) / len(dims), 1) if dims else -1

            return {**scores, "overall": overall, "feedback": feedback}

        except Exception as e:
            return {"clarity": -1, "accuracy": -1, "completeness": -1,
                    "engagement": -1, "overall": -1, "feedback": f"Scoring failed: {e}"}

    # ── Debug logging ────────────────────────────────────────────────

    def debug_log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")

    # ── Timing accessors ─────────────────────────────────────────────

    def get_agent_timing(self, agent_name):
        durations = self._timings.get(agent_name, [])
        if not durations:
            return {"calls": 0, "total_seconds": 0, "avg_seconds": 0}
        return {
            "calls": len(durations),
            "total_seconds": round(sum(durations), 2),
            "avg_seconds": round(sum(durations) / len(durations), 2),
        }

    def get_summary(self):
        total_dur = 0
        if self._pipeline_start and self._pipeline_end:
            total_dur = round(self._pipeline_end - self._pipeline_start, 2)

        return {
            "total_duration_seconds": total_dur,
            "agent_timings": {name: self.get_agent_timing(name) for name in self._timings},
            "total_agent_calls": sum(len(d) for d in self._timings.values()),
            "trace_count": len(self._traces),
        }

    # ── Summary report ───────────────────────────────────────────────

    def print_summary(self, quality_scores=None, token_summary=None, safety_summary=None):
        print("\n" + "=" * 70)
        print("PIPELINE SUMMARY REPORT")
        print("=" * 70)

        summary = self.get_summary()
        print(f"Total duration: {summary['total_duration_seconds']}s")
        print(f"Total agent calls: {summary['total_agent_calls']}")

        print("\nAgent Performance:")
        for name, timing in summary["agent_timings"].items():
            extra = " (revision loop)" if timing["calls"] > 1 else ""
            print(f"  {name:15s} {timing['calls']} call(s), "
                  f"{timing['avg_seconds']}s avg{extra}")

        if token_summary:
            print("\nToken Usage:")
            totals = token_summary.get("totals", {})
            for name, stats in token_summary.items():
                if name == "totals":
                    continue
                print(f"  {name:15s} ~{stats.get('total_tokens', 0):,} tokens "
                      f"({stats.get('calls', 0)} call(s))")
            print(f"  {'TOTAL':15s} ~{totals.get('total_tokens', 0):,} tokens")

        if safety_summary:
            print("\nSafety:")
            print(f"  Flags: {safety_summary.get('warnings', 0)} warning(s), "
                  f"{safety_summary.get('blocking', 0)} blocking")
            by_type = safety_summary.get("by_check_type", {})
            for check_type, count in by_type.items():
                print(f"  {check_type}: {count}")

        if quality_scores and quality_scores.get("overall", -1) > 0:
            print("\nQuality Scores:")
            for dim in ("clarity", "accuracy", "completeness", "engagement"):
                score = quality_scores.get(dim, -1)
                bar = "#" * score + "." * (10 - score) if score > 0 else "N/A"
                print(f"  {dim.capitalize():15s} {score:>2}/10  [{bar}]")
            print(f"  {'Overall':15s} {quality_scores['overall']}/10")
            if quality_scores.get("feedback"):
                print(f"\n  Feedback: {quality_scores['feedback'][:300]}")

        print("=" * 70)

    # ── Trace export ─────────────────────────────────────────────────

    def get_traces(self):
        return [dataclasses.asdict(t) for t in self._traces]

    def export_trace_json(self):
        return json.dumps(self.get_traces(), indent=2)
