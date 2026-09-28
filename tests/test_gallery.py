import io
import os
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image as PILImage

from content.images import AVIF_SUPPORTED, rendition_widths
from content.models import GalleryItem, Image

from .helpers import REVALIDATE_SETTINGS, DashboardTestCase, jpeg

M = '/api/v1/manage/gallery/'


@override_settings(**REVALIDATE_SETTINGS)
@mock.patch('common.revalidate._post', return_value=200)
class GalleryTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.m = self.client_for(self.admin)

    def upload(self, image=None, **data):
        body = {'image': image or jpeg(), 'category': 'farms', 'alt': 'Rows of maize at the Buea farm'}
        body.update(data)
        return self.m.post(M, body, format='multipart')

    def test_upload_creates_renditions(self, _post):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.upload(jpeg(1000, 600))
        self.assertEqual(res.status_code, 201, res.content)
        image = res.json()['image']
        self.assertEqual((image['width'], image['height']), (1000, 600))
        widths = sorted({r['w'] for r in image['renditions']})
        self.assertEqual(widths, [400, 800, 1000])
        fmts = {r['fmt'] for r in image['renditions']}
        self.assertEqual(fmts, {'avif', 'webp'} if AVIF_SUPPORTED else {'webp'})
        self.assertTrue(image['blur'].startswith('data:image/webp;base64,'))
        self.assertTrue(image['src'].startswith('http://testserver/media/uploads/gallery/'))
        for r in Image.objects.get().renditions:
            self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, r['path'])))
        self.assertEqual([c.args[0] for c in _post.call_args_list], [['/gallery', '/']])

    def test_rendition_widths_never_exceed_source(self, _post):
        self.assertEqual(rendition_widths(3000), [400, 800, 1200, 1600, 2400])
        self.assertEqual(rendition_widths(2400), [400, 800, 1200, 1600, 2400])
        self.assertEqual(rendition_widths(1650), [400, 800, 1200, 1600])
        self.assertEqual(rendition_widths(300), [300])

    def test_exif_is_not_kept(self, _post):
        exif = PILImage.Exif()
        exif[0x010F] = 'Camera maker'
        buf = io.BytesIO()
        PILImage.new('RGB', (500, 400), 'red').save(buf, 'JPEG', exif=exif)
        res = self.upload(SimpleUploadedFile('e.jpg', buf.getvalue()))
        path = Image.objects.get(pk=res.json()['image']['id']).file.path
        self.assertEqual(dict(PILImage.open(path).getexif()), {})

    def test_png_and_webp_accepted(self, _post):
        self.assertEqual(self.upload(jpeg(500, 500, name='a.png', fmt='PNG')).status_code, 201)
        self.assertEqual(self.upload(jpeg(500, 500, name='a.webp', fmt='WEBP')).status_code, 201)

    def test_alt_and_category_required(self, _post):
        self.assertEqual(self.upload(alt='').status_code, 400)
        self.assertEqual(self.upload(category='selfies').status_code, 400)
        self.assertFalse(Image.objects.exists())

    def test_rejects_non_images_and_wrong_types(self, _post):
        res = self.upload(SimpleUploadedFile('a.jpg', b'not an image at all'))
        self.assertEqual(res.status_code, 400)
        self.assertIn('image', res.json())
        self.assertEqual(self.upload(SimpleUploadedFile('a.gif', b'GIF89a')).status_code, 400)
        self.assertEqual(self.upload(SimpleUploadedFile('a.svg', b'<svg/>')).status_code, 400)

    @override_settings(IMAGE_UPLOAD_MAX_BYTES=1000)
    def test_size_limit(self, _post):
        res = self.upload(jpeg(800, 800))
        self.assertEqual(res.status_code, 400)
        self.assertIn('MB', res.json()['image'][0])

    def test_public_gallery_shape_and_filter(self, _post):
        self.upload(category='farms')
        self.upload(category='events')
        self.upload(category='events', status='draft')
        GalleryItem.objects.create(media_key='legacy', alt='x', category='farms', status='published')
        public = self.client_for(None).get('/api/v1/gallery/').json()
        self.assertEqual(public['count'], 2)
        row = public['results'][0]
        self.assertEqual(set(row), {'id', 'category', 'alt', 'caption', 'image'})
        self.assertEqual(set(row['image']), {'id', 'src', 'width', 'height', 'renditions', 'blur'})
        self.assertEqual(set(row['image']['renditions'][0]), {'w', 'fmt', 'url'})
        self.assertEqual(self.client_for(None).get('/api/v1/gallery/?category=events').json()['count'], 1)

    def test_patch_reorder_delete(self, _post):
        a = self.upload().json()['id']
        b = self.upload().json()['id']
        res = self.m.patch(f'{M}{a}/', {'caption': 'Harvest', 'category': 'products'}, format='json')
        self.assertEqual((res.json()['caption'], res.json()['category']), ('Harvest', 'products'))
        self.assertEqual(self.m.post(f'{M}reorder/', {'ids': [b, a]}, format='json').status_code, 200)
        self.assertEqual([i['id'] for i in self.m.get(M).json()['results']], [b, a])
        self.assertEqual(self.m.post(f'{M}reorder/', {'ids': [b, 999]}, format='json').status_code, 400)
        paths = Image.objects.get(gallery_items__pk=a).storage_paths()
        self.assertEqual(self.m.delete(f'{M}{a}/').status_code, 204)
        self.assertFalse(GalleryItem.objects.filter(pk=a).exists())
        for p in paths:
            self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, p)))

    def test_publishers_cannot_manage_gallery(self, _post):
        self.assertEqual(self.client_for(self.pub).get(M).status_code, 403)
        res = self.client_for(self.pub).post(M, {'image': jpeg(), 'category': 'farms', 'alt': 'x'}, format='multipart')
        self.assertEqual(res.status_code, 403)

    def test_inline_uploads(self, _post):
        for user, url in ((self.pub, '/api/v1/write/uploads/'), (self.admin, '/api/v1/manage/uploads/')):
            res = self.client_for(user).post(url, {'image': jpeg()}, format='multipart')
            self.assertEqual(res.status_code, 201, res.content)
            self.assertEqual(Image.objects.get(pk=res.json()['id']).kind, 'inline')
        self.assertEqual(self.client_for(self.pub).post('/api/v1/manage/uploads/', {'image': jpeg()},
                                                        format='multipart').status_code, 403)
        self.assertEqual(self.client_for(None).post('/api/v1/write/uploads/', {'image': jpeg()},
                                                    format='multipart').status_code, 401)
        self.assertEqual(self.client_for(self.pub).post('/api/v1/write/uploads/', {}, format='multipart').status_code, 400)
