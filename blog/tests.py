from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Post, Comment
from .forms import CommentForm, EmailPostForm, SearchForm
from django.utils import timezone
from taggit.models import Tag

class BlogModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='john', password='12345')
        self.post = Post.objects.create(
            title='Test Post',
            slug='test-post',
            author=self.user,
            body='Body content',
            publish=timezone.now(),
            status=Post.Status.PUBLISHED,
        )

    def test_post_str(self):
        self.assertEqual(str(self.post), 'Test Post')

    def test_post_absolute_url(self):
        url = self.post.get_absolute_url()
        self.assertIn('/test-post', url)

    def test_comment_defaults(self):
        comment = Comment.objects.create(
            post=self.post,
            user=self.user,
            name='Alice',
            email='alice@example.com',
            body='Nice post!'
        )
        self.assertTrue(comment.active)
        self.assertEqual(str(comment), f'Comment by Alice on {self.post}')


class BlogFormTests(TestCase):
    def test_valid_email_post_form(self):
        form_data = {
            'name': 'John',
            'email': 'john@example.com',
            'to': 'jane@example.com',
            'comments': 'Check this out!',
        }
        form = EmailPostForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_invalid_email_post_form(self):
        form = EmailPostForm(data={})
        self.assertFalse(form.is_valid())

    def test_search_form(self):
        form = SearchForm(data={'query': 'django'})
        self.assertTrue(form.is_valid())

    def test_comment_form(self):
        form = CommentForm(data={'body': 'This is a comment'})
        self.assertTrue(form.is_valid())


class BlogViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='john', password='12345')
        self.post = Post.objects.create(
            title='Sample Post',
            slug='sample-post',
            author=self.user,
            body='Some content here',
            publish=timezone.now(),
            status=Post.Status.PUBLISHED
        )

    def test_post_list_view(self):
        resp = self.client.get(reverse('blog:post_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'blog/post/list.html')

    def test_post_detail_view(self):
        url = self.post.get_absolute_url()
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'blog/post/detail.html')

    def test_post_search_view(self):
        resp = self.client.get(reverse('blog:post_search'), {'query': 'Sample'})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'blog/post/search.html')

    def test_post_share_view_get(self):
        url = reverse('blog:post_share', args=[self.post.id])
        self.client.login(username='john', password='12345')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'blog/post/share.html')

    def test_post_like_ajax(self):
        self.client.login(username='john', password='12345')
        resp = self.client.post(reverse('blog:like_post'), {
            'id': self.post.id,
            'action': 'like'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertJSONEqual(str(resp.content, encoding='utf8'), {'status': 'ok'})


class FeedTests(TestCase):
    def test_latest_posts_feed(self):
        user = User.objects.create_user(username='john', password='12345')
        Post.objects.create(
            title='New post',
            slug='new-post',
            author=user,
            body='Body text',
            publish=timezone.now(),
            status=Post.Status.PUBLISHED
        )
        resp = self.client.get(reverse('blog:post_feed'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'New post', resp.content)


class BlogTemplateTagTests(TestCase):
    def test_fenced_code_block_renders_highlighted(self):
        from .templatetags.blog_tags import markdown_format
        html = markdown_format('```python\nprint("hi")\n```')
        self.assertIn('class="codehilite"', html)
        self.assertIn('<pre>', html)
        # The literal fences must not leak through as text.
        self.assertNotIn('```', html)

    def test_inline_code_renders(self):
        from .templatetags.blog_tags import markdown_format
        html = markdown_format('Use `pip install` to install.')
        self.assertIn('<code>pip install</code>', html)
