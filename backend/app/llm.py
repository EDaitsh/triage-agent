import os

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel

MODEL: str = "gpt-4o"
client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    http_client=httpx.AsyncClient(verify=False),
)


async def structured_call(prompt: str, input_data: str, return_type: type[BaseModel]) -> BaseModel:
    response = await client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": input_data},
        ],
        text_format=return_type,
    )
    return response.output_parsed
