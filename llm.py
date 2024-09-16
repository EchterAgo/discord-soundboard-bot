import asyncio
from dataclasses import dataclass
import json
import logging
from typing import List, Optional

import aiohttp
import discord
from discord.ext import commands, tasks
from discord.commands import option

from config import CONFIG_NANOGPT_API_KEY, CONFIG_NANOGPT_BASE_URL

headers = {"x-api-key": CONFIG_NANOGPT_API_KEY, "Content-Type": "application/json"}

_log = logging.getLogger(__name__)


@dataclass
class GptResponse:
    text: str
    info: dict[str, object]


async def talk_to_gpt(prompt: str, model: str = "gpt-4o", messages: List[str] = []) -> Optional[GptResponse]:
    data = {"prompt": prompt, "model": model, "messages": messages}

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CONFIG_NANOGPT_BASE_URL}/talk-to-gpt", headers=headers, json=data) as response:
            if response.status != 200:
                error_message = f"Error: Received {response.status} status code. Content: {await response.text()}"
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=error_message,
                    headers=response.headers,
                )

            response_text = await response.text()

            # Split and parse the response
            parts = response_text.split("<NanoGPT>")
            text_response = parts[0].strip()
            nano_info = json.loads(parts[1].split("</NanoGPT>")[0])

            return GptResponse(text=text_response, info=nano_info)


def autocomplete_models(ctx: discord.AutocompleteContext) -> list[str]:
    return [
        "chatgpt-4o-latest",
        "o1-preview",
        "o1-mini",
        "claude-3-5-sonnet-20240620",
        "google/gemini-pro-1.5",
        "google/gemini-pro-1.5-exp",
        "meta-llama/llama-3.1-405b-instruct",
        "mattshumer/reflection-70b",
        "accounts/fireworks/models/llama-v3p1-405b-instruct",
        "gpt-4o-2024-08-06",
        "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "llama-3.1-70b-instruct",
        "gpt-4o-mini",
        "claude-3-opus-20240229",
        "google/gemini-flash-1.5",
        "llama-3.1-sonar-huge-128k-online",
        "llama-3.1-sonar-large-128k-online",
        "nousresearch/hermes-3-llama-3.1-405b",
        "nousresearch/hermes-3-llama-3.1-405b:extended",
        "sao10k/l3-euryale-70b",
        "gryphe/mythomax-l2-13b",
        "microsoft/wizardlm-2-8x22b",
        "gpt-4-turbo-preview",
        "gpt-4o",
        "gpt-3.5-turbo",
        "gemini-1.5-flash-001",
        "gemini-1.5-pro-001",
    ]

class LLM(commands.Cog, name="Large language models"):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="gentext", description="Large language model text generation", guild_ids=[1033659963580633088]
    )
    @option("model", description="Pick a model!", autocomplete=autocomplete_models)
    async def gentext(
        self,
        ctx: discord.ApplicationContext,
        prompt: str,
        model: str = "llama-3.1-sonar-huge-128k-online",
    ):
        started_message = await ctx.respond("Generating text, please wait...")

        async def task_func():
            try:
                response = await talk_to_gpt(prompt=prompt, model=model)
                await started_message.edit_original_response(content=f"**PROMPT**: {prompt}\n**RESULT**: {response.text}")
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await started_message.edit_original_response(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())
