import asyncio
import base64
import hashlib
from io import BytesIO
import logging
from typing import Optional

import aiohttp
import nextcord
from nextcord.ext import commands, tasks

from config import CONFIG_NANOGPT_API_KEY, CONFIG_NANOGPT_BASE_URL

headers = {"x-api-key": CONFIG_NANOGPT_API_KEY, "Content-Type": "application/json"}

_log = logging.getLogger(__name__)


async def generate_image(
    prompt: str, model: str, width=1024, height=1024, negative_prompt: str = None
) -> Optional[bytes]:
    data = {
        "prompt": prompt,
        "model": model,
        "width": width,
        "height": height,
        "nImages": 1,
        "num_steps": 25,
        "resolution": f"{width}x{height}",
        "sampler_name": "DPM++ 2S a Karras",
        "scale": 7.5,
    }

    # {
    #     "prompt": "tree",
    #     "nImages": 1,
    #     "model": "flux-pro",
    #     "size": "1024x1024",
    #     "quality": "standard",
    #     "conversationUUID": "cb4212ea-9dcd-4807-9b5c-88f3e1dca7dc",
    #     "showExplicitContent": True,
    # }

    # {
    #     "prompt": "test",
    #     "nImages": 1,
    #     "height": 1024,
    #     "width": 1024,
    #     "num_steps": 28,
    #     "scale": 4,
    #     "model": "sd3_base_medium.safetensors",
    #     "resolution": "1024x1024",
    #     "negative_prompt": "",
    #     "sampler_name": "FlowMatchEuler",
    #     "conversationUUID": "f4e97938-3bf0-4fb9-b2a9-99b501adde93",
    # }

    # {
    #     "prompt": "test",
    #     "nImages": 1,
    #     "height": 1024,
    #     "width": 1024,
    #     "num_steps": 25,
    #     "scale": 7.5,
    #     "model": "dreamshaper_8_93211.safetensors",
    #     "resolution": "1024x1024",
    #     "negative_prompt": "ugly, deformed, malformed, lowres, mutant, mutated, disfigured, compressed, noise, artifacts, dithering, simple, watermark, text, font, signage, collage, pixel",
    #     "sampler_name": "DPM++ 2S a Karras",
    #     "conversationUUID": "f4e97938-3bf0-4fb9-b2a9-99b501adde93",
    # }

    if negative_prompt:
        data["negative_prompt"] = negative_prompt

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CONFIG_NANOGPT_BASE_URL}/generate-image", headers=headers, json=data) as response:
            if response.status != 200:
                error_message = f"Error: Received {response.status} status code. Content: {await response.text()}"
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=error_message,
                    headers=response.headers,
                )

            # {"created":1723451521474,"data":[{"b64_json":"/base64 data=="}],"nanoCost":0.00681,"remainingBalance":5.683467420705782}

            response = await response.json()
            img = base64.b64decode(response["data"][0]["b64_json"])
            return img


class TextToImage(commands.Cog, name="Generates images from text prompts"):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="genimg", description="Generates images from text prompts", guild_ids=[1033659963580633088])
    async def genimg(
        self,
        interaction: nextcord.Interaction,
        prompt: str,
        model: str = nextcord.SlashOption(
            required=True,
            description="Pick a model!",
            autocomplete=True,
            default="sd3_base_medium.safetensors",  # before was epicrealism_naturalSinRC1VAE_106430.safetensors
        ),
        negative_prompt: str = "(deformed iris, deformed pupils, semi-realistic, cgi, 3d, render, sketch, cartoon, drawing, anime:1.4), text, close up, cropped, out of frame, worst quality, low quality, jpeg artifacts, duplicate, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, mutation, deformed, blurry, dehydrated, bad anatomy, bad proportions, extra limbs, cloned face, disfigured, gross proportions, malformed limbs, missing arms, missing legs, extra arms, extra legs, fused fingers, too many fingers, long neck",
    ):
        started_message = await interaction.response.send_message("Generating image, please wait...")

        async def task_func():
            try:
                image = await generate_image(prompt=prompt, model=model, negative_prompt=negative_prompt)
                image_hash = hashlib.sha256(image).hexdigest()
                image_file = nextcord.File(BytesIO(image), filename=f"{image_hash}.jpg")
                await started_message.edit(content=f"Prompt: {prompt}", file=image_file)
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await started_message.edit(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())

    @genimg.on_autocomplete("model")
    async def autocomplete_models(self, interaction: nextcord.Interaction, item: str):
        await interaction.response.send_autocomplete(
            [
                "flux-pro",
                "flux-realism",
                "flux/schnell",
                "playground-v2.5",
                "proteus-v0.2",
                "realisticVisionV51_v51VAE_94301.safetensors",
                "uberRealisticPornMerge_urpmv12_4979.safetensors",
                "sd3_base_medium.safetensors",
                "dreamshaper_8_93211.safetensors",
                "revAnimated_v122.safetensors",
            ][:25]
        )
