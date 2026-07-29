# =====================================================================
# guardrails.py
#
# Guardrails & Safety module for the multi-agent blog-writing pipeline.
#
# Two classes:
#   TokenTracker     – tracks approximate token usage per agent call
#   GuardrailsEngine – input validation, PII detection, content safety,
#                      output format checks, and hallucination flagging
# =====================================================================

import re


# ── Token Tracker ────────────────────────────────────────────────────

class TokenTracker:
    """Track token usage per agent, using SDK metadata or char estimation."""

    def __init__(self):
        self._usage = {}

    def _ensure_agent(self, agent_name):
        if agent_name not in self._usage:
            self._usage[agent_name] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
            }

    def record(self, agent_name, response):
        self._ensure_agent(agent_name)
        entry = self._usage[agent_name]
        entry["calls"] += 1

        try:
            meta = response.usage_metadata
            entry["prompt_tokens"] += meta.prompt_token_count
            entry["completion_tokens"] += meta.candidates_token_count
            entry["total_tokens"] += meta.total_token_count
        except (AttributeError, TypeError):
            chars = len(response.text) if response.text else 0
            estimated = max(chars // 4, 1)
            entry["completion_tokens"] += estimated
            entry["total_tokens"] += estimated

    def record_fallback(self, agent_name, prompt_chars, response_chars):
        self._ensure_agent(agent_name)
        entry = self._usage[agent_name]
        entry["calls"] += 1
        prompt_est = max(prompt_chars // 4, 1)
        completion_est = max(response_chars // 4, 1)
        entry["prompt_tokens"] += prompt_est
        entry["completion_tokens"] += completion_est
        entry["total_tokens"] += prompt_est + completion_est

    def get_agent_usage(self, agent_name):
        return self._usage.get(agent_name, {})

    def get_summary(self):
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
        for stats in self._usage.values():
            for k in totals:
                totals[k] += stats[k]
        return {**self._usage, "totals": totals}

    @property
    def total_tokens(self):
        return sum(s["total_tokens"] for s in self._usage.values())

    def reset(self):
        self._usage.clear()


# ── Guardrails Engine ────────────────────────────────────────────────

class GuardrailsEngine:
    """Centralized safety validation for the blog-writing pipeline."""

    MAX_TOPIC_LENGTH = 500
    MAX_INSTRUCTIONS_LENGTH = 2000
    MIN_TOPIC_LENGTH = 3

    EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_RE = re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
    SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    CC_RE = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')

    INJECTION_PATTERNS = [
        re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions', re.I),
        re.compile(r'you\s+are\s+now\s+(?:a|an|the)', re.I),
        re.compile(r'system\s*prompt\s*:', re.I),
        re.compile(r'pretend\s+(?:to\s+be|you\s+are)', re.I),
        re.compile(r'disregard\s+(?:all\s+)?(?:prior|previous|above)', re.I),
        re.compile(r'override\s+(?:your\s+)?(?:instructions|programming)', re.I),
        re.compile(r'jailbreak', re.I),
    ]

    def __init__(self, gemini_caller=None):
        self._gemini_caller = gemini_caller
        self._flags = []

    def _add_flag(self, agent, check_type, severity, detail):
        self._flags.append({
            "agent": agent,
            "check_type": check_type,
            "severity": severity,
            "detail": detail,
        })

    # ── Input validation ─────────────────────────────────────────────

    def validate_input(self, topic, instructions):
        issues = []

        if not topic or not topic.strip():
            issues.append("Topic is empty")
            self._add_flag("input", "input_validation", "blocking", "Empty topic")
        elif len(topic.strip()) < self.MIN_TOPIC_LENGTH:
            issues.append(f"Topic too short (min {self.MIN_TOPIC_LENGTH} chars)")
            self._add_flag("input", "input_validation", "blocking", "Topic too short")
        elif len(topic) > self.MAX_TOPIC_LENGTH:
            issues.append(f"Topic too long (max {self.MAX_TOPIC_LENGTH} chars)")
            self._add_flag("input", "input_validation", "warning", "Topic exceeds max length")

        if instructions and len(instructions) > self.MAX_INSTRUCTIONS_LENGTH:
            issues.append(f"Instructions too long (max {self.MAX_INSTRUCTIONS_LENGTH} chars)")
            self._add_flag("input", "input_validation", "warning", "Instructions exceed max length")

        for pat in self.INJECTION_PATTERNS:
            if pat.search(topic):
                issues.append(f"Potential prompt injection in topic: '{pat.pattern}'")
                self._add_flag("input", "prompt_injection", "blocking",
                               f"Injection pattern in topic: {pat.pattern}")
            if instructions and pat.search(instructions):
                issues.append(f"Potential prompt injection in instructions: '{pat.pattern}'")
                self._add_flag("input", "prompt_injection", "blocking",
                               f"Injection pattern in instructions: {pat.pattern}")

        has_blocking = any(f["severity"] == "blocking" for f in self._flags
                          if f["check_type"] in ("input_validation", "prompt_injection"))
        return {"valid": not has_blocking, "issues": issues}

    # ── PII detection ────────────────────────────────────────────────

    def check_pii(self, content, agent_name):
        findings = []
        for label, regex in [("email", self.EMAIL_RE), ("phone", self.PHONE_RE),
                              ("ssn", self.SSN_RE), ("credit_card", self.CC_RE)]:
            for match in regex.finditer(content):
                findings.append({"type": label, "match": match.group(), "position": match.start()})

        if findings:
            self._add_flag(agent_name, "pii", "warning",
                           f"Found {len(findings)} PII pattern(s): "
                           + ", ".join(f["type"] for f in findings))

        return {"clean": len(findings) == 0, "findings": findings}

    # ── LLM-based content safety ─────────────────────────────────────

    def check_content_safety(self, content, agent_name):
        if not self._gemini_caller:
            return {"safe": True, "concerns": [], "skipped": True}

        system_prompt = """You are a content safety classifier. Analyze the text and respond EXACTLY in this format:

SAFETY_VERDICT: SAFE or UNSAFE
CONCERNS: <comma-separated list of concerns, or "none">

Check for: hate speech, violence, explicit content, dangerous misinformation, or harmful instructions.
Only flag genuinely problematic content -- technical/educational content about sensitive topics is fine."""

        try:
            result = self._gemini_caller(system_prompt, f"Analyze this content:\n\n{content[:3000]}")
            verdict_line = next((l for l in result.splitlines() if "SAFETY_VERDICT:" in l), "")
            is_safe = "SAFE" in verdict_line and "UNSAFE" not in verdict_line

            concerns = []
            concerns_line = next((l for l in result.splitlines() if "CONCERNS:" in l), "")
            if concerns_line and "none" not in concerns_line.lower():
                concerns = [c.strip() for c in concerns_line.split("CONCERNS:", 1)[1].split(",") if c.strip()]

            if not is_safe:
                self._add_flag(agent_name, "content_safety", "blocking",
                               f"Unsafe content: {', '.join(concerns)}")

            return {"safe": is_safe, "concerns": concerns}

        except Exception as e:
            return {"safe": True, "concerns": [], "error": str(e)}

    # ── Output format validation ─────────────────────────────────────

    def check_output_format(self, output, agent_name):
        issues = []
        if not output or not output.strip():
            issues.append(f"{agent_name} produced empty output")
            self._add_flag(agent_name, "format_validation", "blocking", "Empty output")
            return {"valid": False, "issues": issues}

        checks = {
            "planner": lambda t: len(t) >= 50 or issues.append("Plan too short (< 50 chars)"),
            "researcher": lambda t: len(t) >= 100 or issues.append("Research notes too short (< 100 chars)"),
            "writer": lambda t: (
                (len(t) >= 200 or issues.append("Draft too short (< 200 chars)")) and
                (("#" in t or "**" in t) or issues.append("Draft has no headings"))
            ),
            "reviewer": lambda t: (
                any(l.strip().startswith("VERDICT:") for l in t.splitlines())
                or issues.append("Reviewer output missing VERDICT: line")
            ),
        }

        check = checks.get(agent_name)
        if check:
            check(output)

        if issues:
            self._add_flag(agent_name, "format_validation", "warning",
                           "; ".join(issues))

        return {"valid": len(issues) == 0, "issues": issues}

    # ── Hallucination detection ──────────────────────────────────────

    def check_hallucinations(self, draft, research_notes):
        if not self._gemini_caller:
            return {"flagged_claims": [], "skipped": True}

        system_prompt = """You are a fact-checking assistant. Compare the blog draft against the research notes.
List any specific factual claims in the draft that are NOT supported by the research notes.
Respond in this format -- one per line:

CLAIM: <the unsupported claim>

If all claims are supported, respond with exactly: NO_UNSUPPORTED_CLAIMS"""

        try:
            result = self._gemini_caller(
                system_prompt,
                f"Research notes:\n{research_notes[:3000]}\n\nDraft:\n{draft[:3000]}"
            )

            if "NO_UNSUPPORTED_CLAIMS" in result:
                return {"flagged_claims": []}

            claims = [l.split("CLAIM:", 1)[1].strip()
                      for l in result.splitlines() if l.strip().startswith("CLAIM:")]

            for claim in claims:
                self._add_flag("writer", "hallucination", "warning", claim)

            return {"flagged_claims": claims}

        except Exception as e:
            return {"flagged_claims": [], "error": str(e)}

    # ── Convenience: run all output checks ───────────────────────────

    def run_all_checks(self, content, agent_name, research_notes=None):
        pii = self.check_pii(content, agent_name)
        safety = self.check_content_safety(content, agent_name)
        fmt = self.check_output_format(content, agent_name)

        hallucinations = {}
        if agent_name == "writer" and research_notes:
            hallucinations = self.check_hallucinations(content, research_notes)

        is_safe = pii["clean"] and safety.get("safe", True) and fmt["valid"]

        return {
            "safe": is_safe,
            "pii": pii,
            "content_safety": safety,
            "format": fmt,
            "hallucinations": hallucinations,
        }

    # ── Flag accessors ───────────────────────────────────────────────

    @property
    def all_flags(self):
        return list(self._flags)

    @property
    def blocking_flags(self):
        return [f for f in self._flags if f["severity"] == "blocking"]

    def reset(self):
        self._flags.clear()

    def get_summary(self):
        by_type = {}
        by_agent = {}
        for f in self._flags:
            by_type.setdefault(f["check_type"], []).append(f)
            by_agent.setdefault(f["agent"], []).append(f)

        return {
            "total_flags": len(self._flags),
            "blocking": len(self.blocking_flags),
            "warnings": len(self._flags) - len(self.blocking_flags),
            "by_check_type": {k: len(v) for k, v in by_type.items()},
            "by_agent": {k: len(v) for k, v in by_agent.items()},
        }
