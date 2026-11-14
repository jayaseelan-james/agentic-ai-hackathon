import asyncio
import io

from google import genai

from .config import settings


class GeminiProvider:
    def __init__(self):
        key, self.model = settings()
        if not key:
            raise ValueError('Gemini is not configured. Set GEMINI_API_KEY in the root .env and restart the backend.')
        self.client = genai.Client(api_key=key, http_options={'timeout': 120000, 'retry_options': {'attempts': 1}})

    async def create(self, **body):
        result = await self.client.aio.interactions.create(model=self.model, timeout=120, automatic_continuation=False, **body)
        return result.model_dump(mode='json', exclude_none=True)

    async def upload(self, data: bytes, mime: str):
        file = await self.client.aio.files.upload(file=io.BytesIO(data), config={'mime_type': mime})
        return file.model_dump(mode='json', exclude_none=True)

    async def file(self, name: str):
        result = await self.client.aio.files.get(name=name)
        return result.model_dump(mode='json', exclude_none=True)

    async def delete(self, name: str):
        await self.client.aio.files.delete(name=name)

    async def close(self):
        await self.client.aio.aclose()
        self.client.close()


def public_error(error: Exception) -> str:
    # Provider exception strings may include request details. Never expose them.
    if isinstance(error, ValueError):
        return str(error) if str(error).startswith(('Gemini is not configured', 'Media cannot', 'Image cannot', 'Processed media', 'Gemini returned', 'Investigation', 'Provider file')) else 'Invalid provider response. Please retry.'
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return 'Investigation timed out. Retry or send a shorter recording.'
    code = getattr(error, 'code', None) or getattr(error, 'status_code', None)
    if code in (401, 403):
        return 'Gemini rejected the credentials or model access. Check the backend key and account permissions.'
    if code == 429:
        return 'Gemini quota or rate limit reached. Check account billing/quota and retry later.'
    if code == 404:
        return 'Configured Gemini model or interaction is unavailable. Check GEMINI_MODEL and account access.'
    return 'Gemini request failed. Check the backend connection and provider availability, then retry.'
