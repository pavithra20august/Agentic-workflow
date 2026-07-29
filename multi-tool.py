# =====================================================================
# Enhanced AI Agent using Gemini
# Tools: calculator, web_search (mocked), unit_converter
# Covers: multi-tool selection, error handling, ReAct-style prompting,
#         few-shot examples, asking for clarification
# =====================================================================

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------------
# STEP 1: Load our API key privately from a .env file
# ---------------------------------------------------------------
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ---------------------------------------------------------------
# STEP 2: Define our tools
# Each one is a normal Python function.
# The docstring IS the tool description Gemini reads to decide
# when to use it — so we write these clearly and specifically.
# ---------------------------------------------------------------

def calculator(expression: str) -> str:
    """Evaluates a math expression and returns the numeric result.
    Use this ONLY for arithmetic calculations, e.g. "23 * 47" or "100 / 4".
    Do not use this for unit conversions.

    Args:
        expression: A math expression like '23 * 47'
    """
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        # If something goes wrong (bad expression, etc.), tell the model
        # what happened instead of crashing. The model can then decide
        # what to do next — retry, fix it, or tell the user.
        return f"ERROR: could not calculate '{expression}'. Reason: {e}"


def web_search(query: str) -> str:
    """Searches the web for current information, like news, facts, or events.
    Use this when the user asks about something that could be recent,
    or something you don't already know for certain.

    Args:
        query: What to search for, e.g. "current weather in Chennai"
    """
    # NOTE: This is a MOCK (fake) search, just for learning purposes.
    # In a real project, you'd call an actual search API here
    # (e.g. Tavily, SerpAPI, Bing Search API) and return real results.
    fake_search_results = {
        "capital of australia": "Canberra is the capital of Australia.",
        "tallest mountain": "Mount Everest is the tallest mountain above sea level.",
    }

    query_lower = query.lower()
    for key in fake_search_results:
        if key in query_lower:
            return fake_search_results[key]

    return f"No mock results found for '{query}'. (This is a fake search tool for practice.)"


def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Converts a numeric value between units (length, weight, or temperature).
    Supported units: km, miles, kg, lbs, celsius, fahrenheit.
    Use this ONLY for converting between units — not for plain math.

    Args:
        value: The number to convert, e.g. 10
        from_unit: The unit you're converting FROM, e.g. 'km'
        to_unit: The unit you're converting TO, e.g. 'miles'
    """
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
            return f"ERROR: I don't know how to convert {from_unit} to {to_unit}."

        result = conversions[key](value)
        return f"{value} {from_unit} = {round(result, 2)} {to_unit}"

    except Exception as e:
        return f"ERROR: conversion failed. Reason: {e}"


# ---------------------------------------------------------------
# STEP 3: Write a system prompt (the agent's "job description")
# This is where we cover: role, boundaries, ReAct-style thinking,
# a few-shot example, and asking for clarification.
# ---------------------------------------------------------------

SYSTEM_PROMPT = """
You are a helpful assistant with access to 3 tools: calculator, web_search, and unit_converter.

RULES:
1. Before using a tool, briefly think about which tool (if any) fits the question.
2. Only use a tool if you actually need it. If you already know the answer
   (e.g. "What is the capital of France?"), answer directly without a tool.
3. If a tool returns an error, do not just give up — explain briefly what
   went wrong, or try a corrected approach if reasonable.
4. If the user's question is ambiguous or missing information (e.g. "convert
   10" without saying which units), ask a clarifying question instead of guessing.

EXAMPLE:
User: "How many km is 50 miles, and what's that number times 3?"
Thinking: This needs two steps — first a unit conversion, then a calculation.
Action: call unit_converter(50, "miles", "km") -> get result
Action: call calculator using that result * 3
Final answer: explain both results clearly in plain sentences.
"""

# ---------------------------------------------------------------
# STEP 4: The agent loop
# We turn OFF automatic tool calling so we can see (and control)
# every step: observe -> think -> act -> observe result -> repeat
# ---------------------------------------------------------------

def run_agent(user_question, max_steps=5):
    print(f"\nUser: {user_question}")

    # This list holds the whole conversation so far
    conversation = [
        types.Content(role="user", parts=[types.Part(text=user_question)])
    ]

    # Map tool names to the real Python functions, so we can call them
    available_tools = {
        "calculator": calculator,
        "web_search": web_search,
        "unit_converter": unit_converter,
    }

    for step in range(max_steps):
        # ---- THINK: ask Gemini what to do next ----
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=conversation,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[calculator, web_search, unit_converter],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
        )

        # Add Gemini's reply to the conversation history
        conversation.append(response.candidates[0].content)

        # ---- ACT: check if Gemini wants to use tool(s) ----
        if response.function_calls:
            print(f"Step {step}: Gemini wants to use {len(response.function_calls)} tool(s)")

            tool_response_parts = []

            # NOTE: Gemini can ask for MULTIPLE tools at once (parallel calls).
            # We loop through all of them, not just the first one.
            for call in response.function_calls:
                tool_name = call.name
                tool_args = dict(call.args)
                print(f"   -> Calling {tool_name}({tool_args})")

                tool_function = available_tools.get(tool_name)

                if tool_function is None:
                    result = f"ERROR: unknown tool '{tool_name}'"
                else:
                    result = tool_function(**tool_args)

                print(f"   -> Result: {result}")

                # Package this tool's result to send back to Gemini
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result}
                    )
                )

            # ---- OBSERVE: send all tool results back at once ----
            conversation.append(types.Content(role="user", parts=tool_response_parts))
            # loop continues -> Gemini sees the results and reasons again

        else:
            # No more tools needed — this is the final answer
            print(f"Step {step}: Final answer ready")
            return response.text

    return "Agent stopped: too many steps (possible loop)."


# ---------------------------------------------------------------
# STEP 5: Try it out
# ---------------------------------------------------------------

print(run_agent("What is 23 times 47?"))
print(run_agent("Convert 10 km to miles"))
print(run_agent("What's the capital of Australia?"))
print(run_agent("Convert 50 miles to km, then multiply that number by 2"))
print(run_agent("Convert 10"))   # deliberately vague -> should ask for clarification