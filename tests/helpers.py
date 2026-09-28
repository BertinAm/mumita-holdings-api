import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage
from rest_framework.test import APIClient

from accounts.auth import set_role
from accounts.models import Profile

PASSWORD = 'Correct-Horse-Battery-9'  # check_public: ignore (test fixture)
FRONTEND = 'https://frontend.example'
REVALIDATE_SETTINGS = {'FRONTEND_URL': FRONTEND, 'REVALIDATE_KEY': 'test-revalidate-key'}


def make_user(email, role, *, name='Test Person', password=PASSWORD, must_change=False, active=True):
    user = get_user_model().objects.create_user(username=email, email=email, password=password, is_active=active)
    Profile.objects.create(user=user, name=name, must_change_password=must_change)
    set_role(user, role)
    return user


def jpeg(width=1000, height=600, name='photo.jpg', fmt='JPEG', color=(40, 120, 60)):
    buf = io.BytesIO()
    PILImage.new('RGB', (width, height), color).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


class MediaTestCase(TestCase):
    """Uploads go to a throwaway MEDIA_ROOT."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='mumita-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)


class DashboardTestCase(MediaTestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user('test-admin@mumitaholdings.com', 'admin', name='Admin One')
        self.pub = make_user('test-pub@mumitaholdings.com', 'publisher', name='Pub One')
        self.pub2 = make_user('test-pub2@mumitaholdings.com', 'publisher', name='Pub Two')

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client
