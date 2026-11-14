"""Opt-in paid live checks: python -m backend.tests.live_smoke. Never prints keys."""
import asyncio
import io
import json
import math
import struct
import tempfile
import wave
from pathlib import Path

from PIL import Image
import imageio_ffmpeg

from backend.app import main
from backend.app.config import settings
from backend.app.schemas import Attachment, Incident, Message, Vehicle


async def turn(incident, text, attachment=None):
    user = Message(role='user', text=text)
    if attachment:
        data, mime, kind = attachment
        file = Attachment(id='smoke-' + kind, filename='synthetic-test.' + mime.split('/')[-1], kind=kind, mime_type=mime, size=len(data), url='/unused')
        user.attachments.append(file)
        main.media[file.id] = (data, mime)
    answer = Message(role='assistant', state='processing', provider='gemini', model=settings()[1])
    incident.messages.extend([user, answer])
    await main.run(incident, user, answer)
    summary = {'state': answer.state, 'model': answer.model, 'tools': [e.tool for e in answer.activity], 'citations': len(answer.citations), 'suggestions': len(answer.search_suggestions), 'error': answer.error}
    print(json.dumps(summary), flush=True)
    if answer.state != 'complete':
        raise RuntimeError('Live check failed; see sanitized error above.')
    return answer


async def run():
    if not settings()[0]:
        raise RuntimeError('Configure GEMINI_API_KEY before live checks.')
    incident = Incident(vehicle=Vehicle(make='Toyota', model='Corolla', year=2020))
    answer = await turn(incident, 'I am safely parked. My car has a yellow tire-pressure warning. Use get_vehicle_profile and Google Search to find official manufacturer guidance. Explain what is known and unknown, and create a mechanic report. Do not invent sensor readings.')
    assert 'google_search' in [e.tool for e in answer.activity] and answer.citations
    assert 'get_vehicle_profile' in [e.tool for e in answer.activity]
    await turn(incident, 'Which vehicle and warning did I tell you about? Keep this answer short.')
    output = io.BytesIO()
    Image.new('RGB', (320, 240), color=(30, 110, 160)).save(output, 'PNG')
    await turn(Incident(), 'This is a synthetic solid-color test image. Describe the visible color and explain why it cannot establish a car fault.', (output.getvalue(), 'image/png', 'image'))
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000)
        file.writeframes(b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    await turn(Incident(), 'This is a synthetic audio test, not a car recording. Describe what is audible and its diagnostic limitations.', (audio.getvalue(), 'audio/wav', 'audio'))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'test.mp4'
        process = await asyncio.create_subprocess_exec(imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path))
        assert await process.wait() == 0
        await turn(Incident(), 'This is a synthetic video test. Describe the visible scene and its limitations for car diagnosis.', (path.read_bytes(), 'video/mp4', 'video'))
    print('Live text, follow-up, search, image, audio and video checks passed.', flush=True)


if __name__ == '__main__':
    asyncio.run(run())
