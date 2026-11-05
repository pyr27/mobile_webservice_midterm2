from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Post, Profile
from .forms import PostForm, SignupForm
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import ValidationError
from .serializers import PostSerializer


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
