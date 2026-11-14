import asyncio
import io
import tempfile
import warnings
from pathlib import Path

import imageio_ffmpeg
from PIL import Image


async def normalize(data: bytes, mime: str, kind: str) -> tuple[bytes, str]:
    """Decode actual media; never send a mismatched declared recording format."""
    if kind == 'image':
        def image_bytes():
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 20_000_000:
                        raise ValueError('Image exceeds the decoding pixel limit.')
                    image.load()
                    output = io.BytesIO()
                    image.convert('RGB').save(output, format='JPEG', quality=90)
                    return output.getvalue(), 'image/jpeg'
        try:
            return await asyncio.to_thread(image_bytes)
        except Exception as error:
            raise ValueError('Image cannot be decoded. Upload a valid JPEG, PNG, WebP or GIF.') from error
    with tempfile.TemporaryDirectory(prefix='autosage-') as directory:
        source = Path(directory) / 'input.media'
        target = Path(directory) / ('output.wav' if kind == 'audio' else 'output.mp4')
        source.write_bytes(data)
        args = ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source)]
        if kind == 'audio':
            args += ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le']
        else:
            args += ['-vf', 'scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26', '-c:a', 'aac', '-movflags', '+faststart']
        args += ['-threads', '2', str(target)]
        process = await asyncio.create_subprocess_exec(imageio_ffmpeg.get_ffmpeg_exe(), *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, _ = await asyncio.wait_for(process.communicate(), timeout=45)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode or not target.exists() or not target.stat().st_size:
            raise ValueError('Media cannot be decoded. Try a different audio/video recording or file.')
        if target.stat().st_size > 50_000_000:
            raise ValueError('Processed media exceeds 50 MB. Please send a shorter clip.')
        return target.read_bytes(), 'audio/wav' if kind == 'audio' else 'video/mp4'
