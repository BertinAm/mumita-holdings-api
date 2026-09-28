"""Image uploads: validation, renditions and the image JSON object.

    image = {id, src, width, height, renditions: [{w, fmt, url}], blur}

Accepted: jpg, png, webp, heic/heif (HEIC needs pillow-heif), up to
IMAGE_UPLOAD_MAX_BYTES (15 MB). The pixels are re-encoded, EXIF is not
carried over (after applying its orientation), and the upload itself is
discarded.
"""

import base64
import io
import logging
import secrets
import warnings

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from PIL import Image as PILImage
from PIL import ImageOps, features

from .models import Image

logger = logging.getLogger('content')

try:  # HEIC/HEIF (iPhone photos). Optional: without it HEIC is refused.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIF_SUPPORTED = False

WIDTHS = (400, 800, 1200, 1600, 2400)
AVIF_SUPPORTED = features.check('avif')
FORMATS = ('avif', 'webp') if AVIF_SUPPORTED else ('webp',)
EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'} | ({'heic', 'heif'} if HEIF_SUPPORTED else set())
PIL_FORMATS = {'JPEG', 'MPO', 'PNG', 'WEBP'} | ({'HEIF'} if HEIF_SUPPORTED else set())
MAX_PIXELS = 80_000_000  # 80 MP: larger than any phone camera, far below a decompression bomb
QUALITY = {'avif': 55, 'webp': 80}


class ImageError(ValueError):
    pass


def rendition_widths(source_width):
    widths = [w for w in WIDTHS if w <= source_width]
    if source_width < WIDTHS[-1] and (not widths or source_width - widths[-1] >= 100):
        widths.append(source_width)
    return widths


def _encode(im, fmt, quality=None):
    buf = io.BytesIO()
    if fmt == 'avif':
        im.save(buf, 'AVIF', quality=quality or QUALITY['avif'], speed=8)
    else:
        im.save(buf, 'WEBP', quality=quality or QUALITY['webp'], method=4)
    return buf.getvalue()


def open_upload(upload):
    name = (getattr(upload, 'name', '') or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext not in EXTENSIONS:
        allowed = ', '.join(sorted(EXTENSIONS))
        raise ImageError(f'Upload a {allowed} image.')
    if upload.size > settings.IMAGE_UPLOAD_MAX_BYTES:
        raise ImageError(f'The image is larger than {settings.IMAGE_UPLOAD_MAX_BYTES // (1024 * 1024)} MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', PILImage.DecompressionBombWarning)
            upload.seek(0)
            im = PILImage.open(upload)
            if im.format not in PIL_FORMATS:
                raise ImageError('The file is not a supported image.')
            if im.width * im.height > MAX_PIXELS:
                raise ImageError('The image has too many pixels.')
            im.load()
    except ImageError:
        raise
    except (PILImage.DecompressionBombError, PILImage.DecompressionBombWarning):
        raise ImageError('The image has too many pixels.')
    except Exception:
        raise ImageError('The file could not be read as an image.')
    im = ImageOps.exif_transpose(im)
    has_alpha = im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info)
    im = im.convert('RGBA' if has_alpha else 'RGB')
    return im


def create_image(upload, *, kind, user=None):
    im = open_upload(upload)
    token = secrets.token_hex(8)
    now = timezone.now()
    folder = f'uploads/{kind}/{now:%Y/%m}'
    renditions = []
    saved = []
    try:
        current = im
        for w in sorted(rendition_widths(im.width), reverse=True):
            h = max(1, round(im.height * w / im.width))
            current = current.resize((w, h), PILImage.Resampling.LANCZOS) if current.width != w else current
            for fmt in FORMATS:
                path = default_storage.save(f'{folder}/{token}-{w}.{fmt}', ContentFile(_encode(current, fmt)))
                saved.append(path)
                renditions.append({'w': w, 'h': h, 'fmt': fmt, 'path': path})
        tiny = im.copy()
        tiny.thumbnail((24, 24))
        blur = 'data:image/webp;base64,' + base64.b64encode(_encode(tiny, 'webp', quality=40)).decode()
        largest = max((r for r in renditions if r['fmt'] == 'webp'), key=lambda r: r['w'])
        renditions.sort(key=lambda r: (r['w'], r['fmt']))
        image = Image(
            kind=kind, width=largest['w'], height=largest['h'], renditions=renditions, blur=blur,
            uploaded_by=user if user and user.is_authenticated else None,
        )
        image.file.name = largest['path']
        image.save()
    except Exception:
        for path in saved:
            default_storage.delete(path)
        raise
    logger.info('Image %s (%s) stored with %d renditions', image.pk, kind, len(renditions))
    return image


def media_url(path, request=None):
    if not path:
        return None
    base = settings.MEDIA_BASE_URL
    if not base and request is not None:
        base = request.build_absolute_uri('/').rstrip('/')
    return f'{base}{settings.MEDIA_URL}{path}'


def image_payload(image, request=None):
    if image is None:
        return None
    return {
        'id': image.pk,
        'src': media_url(image.file.name, request),
        'width': image.width,
        'height': image.height,
        'renditions': [
            {'w': r['w'], 'fmt': r['fmt'], 'url': media_url(r['path'], request)} for r in image.renditions
        ],
        'blur': image.blur,
    }


@receiver(post_delete, sender=Image)
def _delete_files(sender, instance, **kwargs):
    for path in instance.storage_paths():
        try:
            default_storage.delete(path)
        except Exception:  # pragma: no cover
            logger.warning('Could not delete media file for image %s', instance.pk)
