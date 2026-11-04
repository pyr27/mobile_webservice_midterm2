from blog.models import Post, StudySession
from django.contrib.auth.models import User
from rest_framework import serializers

class PostSerializer(serializers.ModelSerializer):
    # 토큰 인증된 요청(YOLO Edge Client)은 author를 생략해도 서버가 요청 사용자로 채움
    author = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = Post
        fields = ('id', 'author', 'author_name', 'title', 'text', 'created_date', 'published_date', 'image')

class StudySessionSerializer(serializers.ModelSerializer):
    # user는 토큰 사용자로 서버가 지정 (클라이언트가 타인 user를 지정할 수 없음)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    duration_sec = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = StudySession
        fields = ('id', 'user', 'username', 'started_at', 'ended_at', 'duration_sec', 'note')

    def validate(self, attrs):
        started, ended = attrs.get('started_at'), attrs.get('ended_at')
        if started and ended and ended < started:
            raise serializers.ValidationError('ended_at must be after started_at')
        return attrs
