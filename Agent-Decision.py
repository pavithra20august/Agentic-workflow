# =====================================================================
# Multi-Agent Example: Router -> Math Agent / Search Agent
# =====================================================================

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ---------------------------------------------------------------
# TOOLS (same as before — plain functions, no intelligence)
# ---------------------------------------------------------------

def calculator(expression: str) -> str:
    """Evaluates a math expression and returns the numeric result."""
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"ERROR: {e}"


def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Converts a value between km/miles, kg/lbs, or celsius/fahrenheit."""
    try:
        conversions = {
            ("km", "miles"): lambda v: v * 0.621371,
            ("miles", "km"): lambda v: v / 0.621371,
            ("kg", "lbs"): lambda v: v * 2.20462,
            ("lbs", "kg"): lambda v: v / 2.20462,
            ("celsius", "fahrenheit"): lambda v: (v * 9/5) + 32,
            ("fahrenheit", "celsius"): lambda v: (v - 32) * 5/9,
        }
        key = (from_unit.lower(), to_unit.lower())
        if key not in conversions:
            return f"ERROR: can't convert {from_unit} to {to_unit}"
        return f"{value} {from_unit} = {round(conversions[key](value), 2)} {to_unit}"
    except Exception as e:
        return f"ERROR: {e}"


def web_search(query: str) -> str:
    """Searches the web for facts or current info (mocked for practice)."""
    fake_results = {
        "capital of australia": "Canberra is the capital of Australia.",
        "tallest mountain": "Mount Everest is the tallest mountain above sea level.",
    }
    for key, value in fake_results.items():
        if key in query.lower():
            return value
    return f"No mock results found for '{query}'."


# =====================================================================
# AGENT 1: Math Agent
# Its own LLM reasoning + its own tools (calculator, unit_converter)
# =====================================================================

def math_agent(question):
    print("   [Math Agent] thinking...")

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction="You are a math specialist. Use your tools to solve math and unit-conversion questions.",
            tools=[calculator, unit_converter],
        )
    )
    return response.text


# =====================================================================
# AGENT 2: Search Agent
# Its own LLM reasoning + its own tool (web_search)
# =====================================================================

def search_agent(question):
    print("   [Search Agent] thinking...")

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction="You are a research specialist. Use web_search to answer factual questions.",
            tools=[web_search],
        )
    )
    return response.text


# =====================================================================
# AGENT 3: Router Agent
# This agent does NOT solve the question itself.
# Its only job: decide which specialist agent should handle it.
# =====================================================================

def router_agent(question):
    print(f"\nUser: {question}")
    print("   [Router Agent] deciding who should handle this...")

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=f"""
Decide which agent should handle this question. Reply with ONLY one word:
"MATH" or "SEARCH".

MATH = arithmetic, calculations, unit conversions
SEARCH = facts, current events, general knowledge lookups

Question: {question}
"""
    )

    decision = response.text.strip().upper()
    print(f"   [Router Agent] decision: {decision}")

    # Router hands off the question to the chosen specialist agent
    if "MATH" in decision:
        return math_agent(question)
    elif "SEARCH" in decision:
        return search_agent(question)
    else:
        return "Router couldn't decide which agent to use."


# ---------------------------------------------------------------
# Try it
# ---------------------------------------------------------------

print(router_agent("What is 23 times 47?"))
print(router_agent("What's the capital of Australia?"))
print(router_agent("Convert 10 km to miles"))