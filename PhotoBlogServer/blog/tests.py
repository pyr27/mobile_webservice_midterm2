from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Post


class PostAPITestCase(APITestCase):

    def setUp(self):
        # 실제 User를 먼저 만들고, 그 User를 author로 사용
        self.user = User.objects.create_user(username="testuser", password="testpass123")

        self.post = Post.objects.create(
            author=self.user,
            title="테스트 게시글",
            text="자동 테스트로 생성된 게시글입니다.",
            created_date=timezone.now(),
            published_date=timezone.now(),
        )

    def test_get_post_list(self):
        """GET /api_root/Post/ 요청 시 200 OK와 게시글 목록을 반환하는지 확인"""
        response = self.client.get('/api_root/Post/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_post_list_contains_title(self):
        """목록에 방금 만든 게시글의 title이 포함되어 있는지 확인"""
        response = self.client.get('/api_root/Post/')
        titles = [item['title'] for item in response.data]
        self.assertIn("테스트 게시글", titles)

    def test_create_post(self):
        """POST /api_root/Post/ 로 새 게시글 작성이 되는지 확인"""
        data = {
            "author": self.user.id,
            "title": "새 글",
            "text": "POST 테스트",
            "created_date": timezone.now().isoformat(),
            "published_date": timezone.now().isoformat(),
        }
        response = self.client.post('/api_root/Post/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Post.objects.count(), 2)

    def test_api_root_allowed_methods(self):
        """OPTIONS 요청으로 GET, POST, HEAD, OPTIONS가 허용되는지 확인"""
        response = self.client.options('/api_root/Post/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('GET', response['Allow'])
        self.assertIn('POST', response['Allow'])


class BlogWebTestCase(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw12345!")
        self.other = User.objects.create_user(username="other", password="pw12345!")
        self.admin = User.objects.create_user(username="boss", password="pw12345!", is_staff=True)
        now = timezone.now()
        self.old = Post.objects.create(author=self.owner, title="옛날 글", text="사과",
                                       published_date=now - timezone.timedelta(days=1))
        self.new = Post.objects.create(author=self.other, title="최신 글", text="바나나",
                                       published_date=now)

    def test_home_lists_titles_newest_first_without_body(self):
        res = self.client.get('/')
        html = res.content.decode()
        self.assertLess(html.index("최신 글"), html.index("옛날 글"))
        self.assertNotIn("사과", html)

    def test_home_shows_login_and_signup_when_logged_out(self):
        res = self.client.get('/')
        self.assertContains(res, '/accounts/login/')
        self.assertContains(res, '/signup/')
        self.assertNotContains(res, '/post/new/')

    def test_home_shows_new_and_logout_when_logged_in(self):
        self.client.login(username="owner", password="pw12345!")
        res = self.client.get('/')
        self.assertContains(res, '/post/new/')
        self.assertContains(res, 'action="/accounts/logout/"')

    def test_logout_via_post(self):
        self.client.login(username="owner", password="pw12345!")
        res = self.client.post('/accounts/logout/')
        self.assertEqual(res.status_code, 302)

    def test_login_page_renders(self):
        res = self.client.get('/accounts/login/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "로그인")

    def test_search(self):
        res = self.client.get('/', {'q': '바나나'})
        self.assertContains(res, "최신 글")
        self.assertNotContains(res, "옛날 글")
        res = self.client.get('/', {'q': 'owner'})
        self.assertContains(res, "옛날 글")
        self.assertNotContains(res, "최신 글")

    def test_detail_buttons_only_for_owner_or_admin(self):
        url = f'/post/{self.old.pk}/'
        edit_url = f'/post/{self.old.pk}/edit/'
        self.assertNotContains(self.client.get(url), edit_url)
        self.client.login(username="other", password="pw12345!")
        self.assertNotContains(self.client.get(url), edit_url)
        self.client.login(username="owner", password="pw12345!")
        self.assertContains(self.client.get(url), edit_url)
        self.client.login(username="boss", password="pw12345!")
        self.assertContains(self.client.get(url), edit_url)
        self.assertContains(self.client.get(url), "링크 복사")

    def test_non_owner_cannot_edit_or_delete(self):
        self.client.login(username="other", password="pw12345!")
        self.assertEqual(self.client.get(f'/post/{self.old.pk}/edit/').status_code, 403)
        self.assertEqual(self.client.post(f'/post/{self.old.pk}/delete/').status_code, 403)
        self.assertTrue(Post.objects.filter(pk=self.old.pk).exists())

    def test_anonymous_redirected_to_login(self):
        res = self.client.get('/post/new/')
        self.assertRedirects(res, '/accounts/login/?next=/post/new/')

    def test_admin_edit_keeps_original_author(self):
        self.client.login(username="boss", password="pw12345!")
        self.client.post(f'/post/{self.old.pk}/edit/', {'title': '수정됨', 'text': '본문'})
        self.old.refresh_from_db()
        self.assertEqual(self.old.title, '수정됨')
        self.assertEqual(self.old.author, self.owner)

    def test_signup_creates_inactive_user_pending_approval(self):
        res = self.client.post('/signup/', {
            'username': 'newbie', 'password1': 'Str0ng!pass', 'password2': 'Str0ng!pass',
            'phone': '010-1234-5678',
        }, follow=True)
        self.assertContains(res, "관리자 승인")
        user = User.objects.get(username='newbie')
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.phone, '010-1234-5678')
        self.assertFalse(self.client.login(username='newbie', password='Str0ng!pass'))