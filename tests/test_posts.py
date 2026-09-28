from datetime import datetime
from datetime import timezone as dt_timezone
from unittest import mock

from django.core import mail
from django.test import override_settings

from content.models import Image, Post, PostRevision

from .helpers import REVALIDATE_SETTINGS, DashboardTestCase, jpeg

W = '/api/v1/write/posts/'
M = '/api/v1/manage/posts/'
BODY = '<p>Farmers in Buea grow more when the soil is tested first.</p>'


@override_settings(**REVALIDATE_SETTINGS)
@mock.patch('common.revalidate._post', return_value=200)
class PostWorkflowTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.w = self.client_for(self.pub)
        self.m = self.client_for(self.admin)

    def draft(self, client=None, **data):
        body = {'title': 'Soil first', 'body_html': BODY}
        body.update(data)
        res = (client or self.w).post(W, body, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def paths(self, post_mock):
        return [c.args[0] for c in post_mock.call_args_list]

    def test_create_draft(self, _post):
        post = self.draft()
        self.assertEqual(post['status'], 'draft')
        self.assertEqual(post['slug'], 'soil-first')
        self.assertEqual(post['author'], 'Pub One')
        self.assertFalse(post['has_live_version'])
        self.assertEqual(Post.objects.get().created_by, self.pub)

    def test_slugs_are_unique(self, _post):
        self.draft()
        self.assertEqual(self.draft()['slug'], 'soil-first-2')
        res = self.w.post(W, {'title': 'X', 'slug': 'soil-first'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_status_is_not_writable_by_publishers(self, _post):
        res = self.w.post(W, {'title': 'X', 'status': 'published'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('status', res.json())

    def test_publisher_sees_only_own_posts(self, _post):
        mine = self.draft()
        theirs = self.draft(client=self.client_for(self.pub2), title='Theirs')
        listed = [p['id'] for p in self.w.get(W).json()['results']]
        self.assertEqual(listed, [mine['id']])
        url = f"{W}{theirs['id']}/"
        self.assertEqual(self.w.get(url).status_code, 404)
        self.assertEqual(self.w.patch(url, {'title': 'Mine now'}, format='json').status_code, 404)
        self.assertEqual(self.w.delete(url).status_code, 404)
        self.assertEqual(self.w.post(url + 'submit/').status_code, 404)
        self.assertEqual(Post.objects.get(pk=theirs['id']).title, 'Theirs')

    def test_publisher_cannot_use_manage_or_approve(self, _post):
        post = self.draft()
        self.assertEqual(self.w.get(M).status_code, 403)
        self.assertEqual(self.w.post(f"{M}{post['id']}/approve/").status_code, 403)
        self.assertEqual(self.w.get('/api/v1/manage/stats/').status_code, 403)
        self.assertEqual(Post.objects.get().status, 'draft')

    def test_anonymous_gets_401(self, _post):
        self.assertEqual(self.client_for(None).get(W).status_code, 401)
        self.assertEqual(self.client_for(None).get(M).status_code, 401)

    def test_submit_emails_admins_then_approve_publishes(self, _post):
        post = self.draft()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.w.post(f"{W}{post['id']}/submit/")
        self.assertEqual(res.json()['status'], 'pending_review')
        self.assertEqual([m.to for m in mail.outbox], [[self.admin.email]])
        self.assertIn('Soil first', mail.outbox[0].subject)
        self.assertEqual(self.client_for(None).get('/api/v1/posts/').json()['count'], 0)

        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.post(f"{M}{post['id']}/approve/")
        self.assertEqual(res.json()['status'], 'published')
        self.assertIsNotNone(res.json()['published_at'])
        self.assertEqual(self.paths(_post), [['/blog', '/blog/soil-first', '/']])
        public = self.client_for(None).get('/api/v1/posts/soil-first/').json()
        self.assertEqual(public['body_html'], BODY)
        self.assertEqual(public['author'], 'Pub One')
        self.assertEqual(public['reading_minutes'], 1)
        self.assertTrue(public['excerpt'].startswith('Farmers in Buea'))

    def test_submit_needs_text(self, _post):
        post = self.draft(body_html='')
        self.assertEqual(self.w.post(f"{W}{post['id']}/submit/").status_code, 400)

    def test_reject_requires_note_and_emails_author(self, _post):
        post = self.draft()
        self.w.post(f"{W}{post['id']}/submit/")
        mail.outbox.clear()
        self.assertEqual(self.m.post(f"{M}{post['id']}/reject/", {}, format='json').status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.post(f"{M}{post['id']}/reject/", {'note': 'Add a source for the yield figure.'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'changes_requested')
        self.assertEqual(mail.outbox[0].to, [self.pub.email])
        self.assertIn('Add a source', mail.outbox[0].body)
        mine = self.w.get(f"{W}{post['id']}/").json()
        self.assertEqual(mine['review_note'], 'Add a source for the yield figure.')
        # Edit keeps changes_requested; submit moves it back to pending_review.
        self.assertEqual(self.w.patch(f"{W}{post['id']}/", {'dek': 'Now sourced.'}, format='json').json()['status'],
                         'changes_requested')
        self.assertEqual(self.w.post(f"{W}{post['id']}/submit/").json()['status'], 'pending_review')

    def test_reject_only_pending(self, _post):
        post = self.draft()
        self.assertEqual(self.m.post(f"{M}{post['id']}/reject/", {'note': 'x'}, format='json').status_code, 400)

    def test_editing_a_published_post_creates_a_revision(self, _post):
        post = self.draft()
        self.w.post(f"{W}{post['id']}/submit/")
        self.m.post(f"{M}{post['id']}/approve/")
        published_at = Post.objects.get().published_at
        _post.reset_mock()

        res = self.w.patch(f"{W}{post['id']}/", {'title': 'Soil first, revised', 'body_html': '<p>New text.</p>'},
                           format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'pending_review')
        self.assertTrue(res.json()['has_live_version'])
        self.assertTrue(res.json()['has_pending_revision'])
        self.assertEqual(res.json()['title'], 'Soil first, revised')
        # The live version is untouched.
        live = self.client_for(None).get('/api/v1/posts/soil-first/').json()
        self.assertEqual((live['title'], live['body_html']), ('Soil first', BODY))
        self.assertEqual(PostRevision.objects.count(), 1)
        self.assertEqual(_post.call_count, 0)

        with self.captureOnCommitCallbacks(execute=True):
            self.m.post(f"{M}{post['id']}/approve/")
        live = self.client_for(None).get('/api/v1/posts/soil-first/').json()
        self.assertEqual((live['title'], live['body_html']), ('Soil first, revised', '<p>New text.</p>'))
        self.assertEqual(Post.objects.get().published_at, published_at)
        self.assertFalse(PostRevision.objects.exists())
        self.assertEqual(_post.call_count, 1)

    def test_rejected_revision_keeps_live_version(self, _post):
        post = Post.objects.create(slug='live', title='Live', body=BODY, status='published', created_by=self.pub,
                                   published_at=datetime(2020, 1, 9, tzinfo=dt_timezone.utc))
        self.w.patch(f'{W}{post.pk}/', {'title': 'Changed'}, format='json')
        self.m.post(f'{M}{post.pk}/reject/', {'note': 'No.'}, format='json')
        self.assertEqual(self.w.get(f'{W}{post.pk}/').json()['status'], 'changes_requested')
        self.assertEqual(self.client_for(None).get('/api/v1/posts/live/').json()['title'], 'Live')

    def test_submit_on_published_without_changes_is_refused(self, _post):
        post = Post.objects.create(slug='live', title='Live', body=BODY, status='published', created_by=self.pub,
                                   published_at=datetime(2020, 1, 9, tzinfo=dt_timezone.utc))
        self.assertEqual(self.w.post(f'{W}{post.pk}/submit/').status_code, 400)

    def test_delete_own_published_post_revalidates(self, _post):
        post = Post.objects.create(slug='live', title='Live', body=BODY, status='published', created_by=self.pub,
                                   published_at=datetime(2020, 1, 9, tzinfo=dt_timezone.utc))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.w.delete(f'{W}{post.pk}/').status_code, 204)
        self.assertFalse(Post.objects.exists())
        self.assertEqual(self.paths(_post), [['/blog', '/blog/live', '/']])

    def test_delete_draft_does_not_revalidate(self, _post):
        post = self.draft()
        with self.captureOnCommitCallbacks(execute=True):
            self.w.delete(f"{W}{post['id']}/")
        self.assertEqual(_post.call_count, 0)

    def test_admin_publishes_directly_and_unpublishes(self, _post):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.post(M, {'title': 'Admin note', 'body_html': BODY, 'status': 'published'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()['status'], 'published')
        self.assertEqual(self.client_for(None).get('/api/v1/posts/').json()['count'], 1)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.patch(f"{M}{res.json()['id']}/", {'status': 'draft'}, format='json')
        self.assertEqual(res.json()['status'], 'draft')
        self.assertEqual(self.client_for(None).get('/api/v1/posts/admin-note/').status_code, 404)
        self.assertEqual(_post.call_count, 2)

    def test_admin_sees_all_posts_and_filters(self, _post):
        self.draft()
        self.draft(client=self.client_for(self.pub2), title='Other')
        self.assertEqual(self.m.get(M).json()['count'], 2)
        self.assertEqual(self.m.get(M + '?status=draft').json()['count'], 2)
        self.assertEqual(self.m.get(M + '?status=published').json()['count'], 0)
        self.assertEqual(self.m.get(M + '?q=other').json()['count'], 1)
        self.assertEqual(self.m.get(f'{M}?owner={self.pub2.pk}').json()['count'], 1)

    def test_admin_direct_edit_of_live_post_revalidates_old_and_new_slug(self, _post):
        post = Post.objects.create(slug='live', title='Live', body=BODY, status='published',
                                   published_at=datetime(2020, 1, 9, tzinfo=dt_timezone.utc))
        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.patch(f'{M}{post.pk}/', {'slug': 'renamed'}, format='json')
        self.assertEqual(res.json()['slug'], 'renamed')
        self.assertEqual(self.paths(_post), [['/blog', '/blog/live', '/blog/renamed', '/']])

    def test_cover_must_be_own_upload_for_publishers(self, _post):
        img = self.client_for(self.pub2).post('/api/v1/write/uploads/', {'image': jpeg()}, format='multipart').json()
        res = self.w.post(W, {'title': 'X', 'cover_id': img['id']}, format='json')
        self.assertEqual(res.status_code, 400)
        mine = self.w.post('/api/v1/write/uploads/', {'image': jpeg()}, format='multipart').json()
        res = self.w.post(W, {'title': 'Y', 'cover_id': mine['id']}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['cover']['id'], mine['id'])
        self.assertEqual(Image.objects.count(), 2)


@override_settings(ALLOWED_HOSTS=['api.example.com', 'testserver'], MEDIA_BASE_URL='https://api.example.com',
                   SITE_HOSTS=['mumitaholdings.com'])
class SanitizationTests(DashboardTestCase):
    def body_of(self, html):
        res = self.client_for(self.pub).post(W, {'title': 'T', 'body_html': html}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()['body_html']

    def test_scripts_and_event_handlers_are_stripped(self):
        out = self.body_of('<p onclick="steal()" style="color:red">Hi<script>alert(1)</script></p>'
                           '<img src="/media/uploads/inline/a.webp" onerror="x()" alt="a">'
                           '<iframe src="https://evil.example"></iframe><style>p{}</style>')
        self.assertNotIn('script', out)
        self.assertNotIn('onclick', out)
        self.assertNotIn('onerror', out)
        self.assertNotIn('style', out)
        self.assertNotIn('iframe', out)
        self.assertIn('<p>Hi</p>', out)

    def test_javascript_urls_removed(self):
        out = self.body_of('<p><a href="javascript:alert(1)">x</a><a href="data:text/html,hi">y</a></p>')
        self.assertNotIn('javascript', out)
        self.assertNotIn('data:', out)

    def test_external_links_get_rel(self):
        out = self.body_of('<p><a href="https://evil.example/x">e</a> <a href="https://www.mumitaholdings.com/blog">i</a>'
                           ' <a href="/contact" target="_top">r</a></p>')
        self.assertIn('<a href="https://evil.example/x" rel="noopener noreferrer">e</a>', out)
        self.assertIn('<a href="https://www.mumitaholdings.com/blog">i</a>', out)
        self.assertIn('<a href="/contact">r</a>', out)

    def test_images_only_from_our_media(self):
        out = self.body_of('<figure><img src="https://evil.example/a.png" alt="bad">'
                           '<img src="https://api.example.com/media/uploads/inline/2026/09/a-800.webp" alt="ok" width="800">'
                           '<img src="/media/partners/logo.svg"><img src="/media/uploads/../../etc/passwd">'
                           '<figcaption>Cap</figcaption></figure>')
        self.assertNotIn('evil', out)
        self.assertNotIn('partners', out)
        self.assertNotIn('passwd', out)
        self.assertIn('src="https://api.example.com/media/uploads/inline/2026/09/a-800.webp"', out)
        self.assertIn('<figcaption>Cap</figcaption>', out)

    def test_allow_list_keeps_editor_markup(self):
        html = ('<h2>A</h2><h3>B</h3><h4>C</h4><p><strong>s</strong> <em>e</em> <u>u</u> <s>x</s> <code>c</code><br></p>'
                '<ul><li>1</li></ul><ol><li>2</li></ol><blockquote>q</blockquote><pre>p</pre><hr>'
                '<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>d</td></tr></tbody></table>')
        self.assertEqual(self.body_of(html), html)

    def test_disallowed_tags_are_unwrapped(self):
        self.assertEqual(self.body_of('<h1>Big</h1><div><span>t</span></div>'), 'Bigt')
