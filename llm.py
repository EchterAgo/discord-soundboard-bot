import asyncio
from dataclasses import dataclass
import json
import logging
from typing import List, Optional, Dict

import aiohttp
import nextcord
from nextcord.ext import commands

from config import CONFIG_NANOGPT_API_KEY, CONFIG_NANOGPT_BASE_URL

headers = {"Authorization": f"Bearer {CONFIG_NANOGPT_API_KEY}", "Content-Type": "application/json"}

_log = logging.getLogger(__name__)


@dataclass
class GptResponse:
    text: str
    info: dict[str, object]


async def talk_to_gpt(prompt: str, model: str = "gpt-4o", messages: List[Dict[str, str]] = []) -> Optional[GptResponse]:
    data = {"model": model}
    if messages:
        data["messages"] = messages
    else:
        data["messages"] = [{"role": "user", "content": prompt}]

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CONFIG_NANOGPT_BASE_URL}/chat/completions", headers=headers, json=data) as response:
            if response.status != 200:
                error_message = f"Error: Received {response.status} status code. Content: {await response.text()}"
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=error_message,
                    headers=response.headers,
                )

            response = await response.json()
            return GptResponse(text=response["choices"][0]["message"]["content"], info=response["nanoGPT"])


class LLM(commands.Cog, name="Large language models"):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(
        name="gentext", description="Large language model text generation", guild_ids=[1033659963580633088]
    )
    async def gentext(
        self,
        interaction: nextcord.Interaction,
        prompt: str,
        model: str = nextcord.SlashOption(
            required=True, description="Pick a model!", autocomplete=True, default="llama-3.1-sonar-huge-128k-online"
        ),
    ):
        started_message = await interaction.response.send_message("Generating text, please wait...")

        async def task_func():
            try:
                response = await talk_to_gpt(prompt=prompt, model=model)
                await started_message.edit(content=f"**PROMPT**: {prompt}\n**RESULT**: {response.text}")
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await started_message.edit(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())

    @gentext.on_autocomplete("model")
    async def autocomplete_models(self, interaction: nextcord.Interaction, item: str):
        await interaction.response.send_autocomplete(
            [
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
            ][:25]
        )

    @nextcord.slash_command(
        name="genlocal", description="Large language model text generation", guild_ids=[1033659963580633088]
    )
    async def genlocal(
        self,
        interaction: nextcord.Interaction,
        prompt: str,
        model: str = nextcord.SlashOption(
            required=True,
            description="Pick a model!",
            autocomplete=True,
            default="Qwen2.5-Coder-32B-Instruct-Q4_K_L.gguf",
        ),
    ):
        started_message = await interaction.response.send_message("Generating text, please wait...")

        async def task_func():
            try:
                response = await talk_to_gpt(prompt=prompt, model=model)
                await started_message.edit(content=f"**PROMPT**: {prompt}\n**RESULT**: {response.text}")
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await started_message.edit(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())

    @genlocal.on_autocomplete("model")
    async def autocomplete_models_local(self, interaction: nextcord.Interaction, item: str):
        await interaction.response.send_autocomplete(
            [
                "Qwen2.5-Coder-32B-Instruct-Q4_K_L.gguf",
            ][:25]
        )
