from django.db import models
from django.utils import timezone

class Post(models.Model):
    author = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    text = models.TextField()
    created_date = models.DateTimeField(default=timezone.now)
    published_date = models.DateTimeField(blank=True, null=True)
    image = models.ImageField(upload_to='images/%Y/%m/%d/', default='images/default_error.png')

    class Meta:
        ordering = ['-published_date']  # 최신 게시글이 먼저 오도록

    def publish(self):
        self.published_date = timezone.now()
        self.save()

    def __str__(self):
        return self.title


class Profile(models.Model):
    # 회원가입 신청 시 입력한 전화번호 (관리자 승인 참고용)
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.user.username} ({self.phone})"

class StudySession(models.Model):
    """Edge Client(YOLO + 얼굴 식별)가 측정한 1회 공부 세션. 소유자 본인만 생성/조회/수정 가능."""
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='study_sessions')
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_sec = models.PositiveIntegerField()
    note = models.CharField(max_length=200, blank=True)  # 세션 메모(기말: 공부 내용 기록으로 확장)

    class Meta:
        ordering = ['-started_at']

    def save(self, *args, **kwargs):
        if not self.duration_sec and self.started_at and self.ended_at:
            self.duration_sec = max(0, int((self.ended_at - self.started_at).total_seconds()))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} {self.started_at:%Y-%m-%d %H:%M} ({self.duration_sec}s)"
