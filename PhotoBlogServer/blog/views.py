from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Q, Sum, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Post, Profile, StudySession
from .forms import PostForm, SignupForm
from rest_framework import viewsets, permissions, throttling
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .permissions import IsOwner
from .serializers import PostSerializer, StudySessionSerializer


def can_manage(user, post):
    # 게시자 본인 또는 관리자만 수정/삭제 가능
    return user.is_authenticated and (user == post.author or user.is_staff)


def post_list(request):
    posts = Post.objects.filter(
        published_date__lte=timezone.now()
    ).select_related('author').order_by('-published_date')

    q = request.GET.get('q', '').strip()
    if q:
        posts = posts.filter(
            Q(title__icontains=q) | Q(text__icontains=q) | Q(author__username__icontains=q)
        )
    return render(request, 'blog/post_list.html', {'posts': posts, 'q': q})

def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    return render(request, 'blog/post_detail.html', {
        'post': post,
        'can_manage': can_manage(request.user, post),
    })

@login_required
def post_new(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.published_date = timezone.now()
            post.save()
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm()
    return render(request, 'blog/post_edit.html', {'form': form})

@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_manage(request.user, post):
        raise PermissionDenied
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()  # 관리자가 수정해도 원래 게시자는 유지
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/post_edit.html', {'form': form, 'post': post})

@login_required
def post_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_manage(request.user, post):
        raise PermissionDenied
    if request.method == "POST":
        post.delete()
        return redirect('post_list')
    return render(request, 'blog/post_confirm_delete.html', {'post': post})

def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            # 관리자 승인 전까지는 로그인할 수 없도록 비활성 상태로 생성
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            Profile.objects.create(user=user, phone=form.cleaned_data['phone'])
            messages.success(request, "가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.")
            return redirect('post_list')
    else:
        form = SignupForm()
    return render(request, 'registration/signup.html', {'form': form})

def js_test(request):
    return render(request, 'blog/js_test.html', {})

class IntruderImage(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    # YOLO Edge Client는 /api-token-auth/ 로 받은 토큰(Authorization: Token ...)으로 인증
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def perform_create(self, serializer):
        if self.request.user.is_authenticated:
            serializer.save(author=self.request.user)  # 토큰/세션 사용자를 게시자로 지정
        elif 'author' in serializer.validated_data:
            serializer.save()  # 기존 Android 클라이언트처럼 author id를 직접 보낸 경우
        else:
            raise ValidationError({'author': '인증 토큰 또는 author 값이 필요합니다.'})


# ---------------------------------------------------------------------------
# 편의 기능 ②: 공부 세션(StudySession) - 소유자 권한 / 일·주 집계 / 랭킹(캐시+스로틀링)
# ---------------------------------------------------------------------------
RANKING_CACHE_SEC = 60


def period_start(period):
    """'day' -> 오늘 0시, 'week' -> 이번 주 월요일 0시 (서버 TIME_ZONE 기준)."""
    now = timezone.localtime()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'week':
        start -= timedelta(days=start.weekday())
    return start


def ranking_rows(period):
    """기간별 사용자 순공부시간 랭킹. 60초 캐시로 반복 집계 쿼리를 막는다."""
    key = f"ranking:{period}:{period_start(period):%Y%m%d}"
    rows = cache.get(key)
    if rows is None:
        qs = (StudySession.objects.filter(started_at__gte=period_start(period))
              .values('user_id', 'user__username')
              .annotate(total_sec=Sum('duration_sec'), sessions=Count('id'))
              .order_by('-total_sec'))
        rows = [{'rank': i + 1, 'user': r['user_id'], 'username': r['user__username'],
                 'total_sec': r['total_sec'], 'sessions': r['sessions']} for i, r in enumerate(qs)]
        cache.set(key, rows, RANKING_CACHE_SEC)
        cached = False
    else:
        cached = True
    return rows, cached


class StudySessionViewSet(viewsets.ModelViewSet):
    """토큰 인증 필수. 본인 세션만 목록/조회/수정/삭제 가능 (staff는 전체)."""
    serializer_class = StudySessionSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        qs = StudySession.objects.select_related('user')
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        cache.clear()  # 새 세션이 들어오면 랭킹 캐시 무효화


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([permissions.IsAuthenticated])
def study_stats(request):
    """본인의 오늘/이번 주 순공부시간 집계."""
    result = {'username': request.user.username}
    for period in ('day', 'week'):
        agg = (StudySession.objects.filter(user=request.user, started_at__gte=period_start(period))
               .aggregate(total=Sum('duration_sec'), sessions=Count('id')))
        result[period] = {'total_sec': agg['total'] or 0, 'sessions': agg['sessions']}
    return Response(result)


class RankingThrottle(throttling.AnonRateThrottle):
    scope = 'ranking'


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([RankingThrottle])
def study_ranking(request):
    """GET /api_root/ranking/?period=day|week  - 전체 사용자 순공부시간 랭킹 (60초 캐시, 분당 30회 제한)."""
    period = request.GET.get('period', 'day')
    if period not in ('day', 'week'):
        raise ValidationError({'period': "'day' or 'week'"})
    rows, cached = ranking_rows(period)
    resp = Response({'period': period, 'since': period_start(period), 'cached': cached, 'results': rows})
    resp['X-Cache'] = 'HIT' if cached else 'MISS'
    return resp


def ranking_page(request):
    period = request.GET.get('period', 'day')
    if period not in ('day', 'week'):
        period = 'day'
    rows, cached = ranking_rows(period)
    return render(request, 'blog/ranking.html', {'rows': rows, 'period': period, 'cached': cached,
                                                 'since': period_start(period)})
