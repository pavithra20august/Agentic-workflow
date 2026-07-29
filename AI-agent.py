# =========================================
# A very simple AI Agent using Gemini
# It can use a "calculator tool" if it needs to
# =========================================

import google.generativeai as genai
import os

# Step 1: Set up our API key so we can talk to Gemini
my_api_key = os.getenv("GEMINI_API_KEY")

genai.configure(api_key = my_api_key)


# Step 2: Create our tool (just a normal function)
# The comment inside (docstring) tells Gemini what this function does.
# Gemini reads this to decide WHEN to use it.
def calculator(expression):
    """
    This tool does math.
    Give it something like "23 * 47" and it will return the answer.
    """
    answer = eval(expression)
    return str(answer)


# Step 3: Tell Gemini it is allowed to use our calculator tool
my_model = genai.GenerativeModel(
    model_name="gemini-2.5-pro",
    tools=[calculator]
)


# Step 4: Start a chat with the model
chat = my_model.start_chat()


# Step 5: Ask our question
question = "What is 123 divide by 47?"
print("Me:", question)

response = chat.send_message(question)


# Step 6: Check if Gemini wants to use the calculator
first_part = response.candidates[0].content.parts[0]

if first_part.function_call.name == "calculator":

    print("Gemini wants to use the calculator tool!")

    # Get the math expression Gemini wants to calculate
    math_expression = first_part.function_call.args["expression"]
    print("Expression Gemini gave us:", math_expression)

    # Step 7: We run the calculator ourselves
    result = calculator(math_expression)
    print("Calculator result:", result)

    # Step 8: Send the result back to Gemini so it can finish answering
    response = chat.send_message(
        genai.protos.Content(
            parts=[
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name="calculator",
                        response={"result": result}
                    )
                )
            ]
        )
    )

# Step 9: Print Gemini's final answer
print("Gemini's final answer:", response.text)