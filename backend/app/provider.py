import asyncio
import io
import json
from uuid import uuid4

from google import genai

from .config import RESTRICTED_MODEL, WEB_TOOLS, settings


class GeminiProvider:
    name = 'gemini'

    def __init__(self, model: str | None = None):
        key, configured_model = settings()
        self.model = model or configured_model
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


class GemmaProvider(GeminiProvider):
    """Hosted Gemma through the same Gemini API; local application tools only."""
    name = 'gemma'

    def __init__(self):
        super().__init__(model=RESTRICTED_MODEL)
        self._contents = []
        self._previous = None
        self._calls = {}

    async def create(self, **body):
        declarations = []
        for tool in body.get('tools', []):
            if tool.get('type') != 'function' or tool.get('name') in WEB_TOOLS:
                raise ValueError('Web access is blocked in remote breakdown mode. External tools cannot be sent to Gemma.')
            declarations.append({
                'name': tool['name'], 'description': tool.get('description', ''),
                'parameters_json_schema': tool.get('parameters', {'type': 'object'}),
            })
        previous = body.get('previous_interaction_id')
        if previous and previous != self._previous:
            raise ValueError('Gemma returned an invalid conversation continuation. Please retry.')
        if not previous:
            self._contents = []
            self._calls = {}
        for item in body['input']:
            if item['type'] == 'function_result':
                result = json.loads(item['result'][0]['text'])
                call = self._calls.pop(item['call_id'], None)
                if not call or call['name'] != item['name']:
                    raise ValueError('Gemma returned an invalid tool continuation. Please retry.')
                response = {'name': item['name'], 'response': result}
                if call.get('id'):
                    response['id'] = call['id']
                content = {'role': 'user', 'parts': [{'function_response': response}]}
            else:
                blocks = item.get('content', [item])
                parts = []
                for block in blocks:
                    if block['type'] == 'text':
                        parts.append({'text': block['text']})
                    elif block['type'] in ('image', 'audio', 'video'):
                        parts.append({'file_data': {'file_uri': block['uri'], 'mime_type': block['mime_type']}})
                    else:
                        raise ValueError('Gemma returned unsupported conversation content. Please retry.')
                content = {'role': 'model' if item['type'] == 'model_output' else 'user', 'parts': parts}
            # Consecutive user inputs (including automatic sensor context and tool results)
            # form one turn. Model response parts, including signatures, stay intact.
            if self._contents and content['role'] == 'user' and self._contents[-1]['role'] == 'user':
                self._contents[-1]['parts'].extend(content['parts'])
            else:
                self._contents.append(content)
        config = {
            'system_instruction': body['system_instruction'],
            'max_output_tokens': body.get('generation_config', {}).get('max_output_tokens', 6000),
            'automatic_function_calling': {'disable': True},
        }
        if declarations:
            config['tools'] = [{'function_declarations': declarations}]
        result = await self.client.aio.models.generate_content(model=RESTRICTED_MODEL, contents=self._contents, config=config)
        raw = result.model_dump(mode='json', exclude_none=True)
        if raw.get('model_version') not in (None, RESTRICTED_MODEL, 'models/' + RESTRICTED_MODEL):
            raise ValueError('Gemma returned a different model. Remote breakdown mode requires Gemma 4 26B strictly.')
        candidates = raw.get('candidates') or []
        if not candidates or candidates[0].get('finish_reason') != 'STOP':
            raise ValueError('Gemma returned a blocked, incomplete or empty response. Rephrase the question or retry.')
        content = candidates[0].get('content') or {}
        if not content.get('parts'):
            raise ValueError('Gemma returned a blocked, incomplete or empty response. Rephrase the question or retry.')
        self._contents.append(content)
        self._previous = uuid4().hex
        steps = []
        for part in content['parts']:
            if part.get('function_call'):
                call = part['function_call']
                call_id = call.get('id') or uuid4().hex
                self._calls[call_id] = call
                steps.append({'type': 'function_call', 'id': call_id, 'name': call['name'], 'arguments': call.get('args') or {}})
            elif part.get('text') and not part.get('thought'):
                steps.append({'type': 'model_output', 'content': [{'type': 'text', 'text': part['text']}]})
        return {'id': self._previous, 'status': 'completed', 'steps': steps}


def public_error(error: Exception) -> str:
    # Provider exception strings may include request details. Never expose them.
    if isinstance(error, ValueError):
        return str(error) if str(error).startswith(('Gemini is not configured', 'Media cannot', 'Image cannot', 'Processed media', 'Gemini returned', 'Gemma returned', 'Gemma 4 26B returned', 'Web access is blocked', 'Investigation', 'Provider file')) else 'Invalid provider response. Please retry.'
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
