from blog.models import Post
from django.contrib.auth.models import User
from rest_framework import serializers

class PostSerializer(serializers.ModelSerializer):
    # 토큰 인증된 요청(YOLO Edge Client)은 author를 생략해도 서버가 요청 사용자로 채움
    author = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = Post
        fields = ('id', 'author', 'author_name', 'title', 'text', 'created_date', 'published_date', 'image')