import os

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel

MODEL: str = "gpt-4o"
client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    http_client=httpx.AsyncClient(verify=False),
)


async def structured_call(
    prompt: str, input_data: str, return_type: type[BaseModel]
) -> BaseModel:
    response = await client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": input_data},
        ],
        text_format=return_type,
    )
    return response.output_parsed


async def text_call(system_prompt: str, user_input: str) -> str:
    """Plain-text LLM call, returns the model's output as a string."""
    response = await client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
    )
    return response.output_text
