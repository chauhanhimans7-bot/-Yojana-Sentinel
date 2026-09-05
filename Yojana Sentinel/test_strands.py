import os
from dotenv import load_dotenv

from strands import Agent
from strands.models.litellm import LiteLLMModel

# Load .env
load_dotenv()

# Create Groq model
model = LiteLLMModel(
    model_id="groq/llama-3.1-8b-instant",
    params={
        "temperature": 0.7,
    },
)

# Create Strands agent using Groq
agent = Agent(model=model)

# Ask the agent
response = agent("Say hello in one sentence.")

print(response)