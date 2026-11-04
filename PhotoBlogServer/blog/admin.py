from django.contrib import admin
from .models import Post, Profile

admin.site.register(Post)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    # 가입 승인: 관리자 > Users 에서 해당 사용자의 Active 체크
    list_display = ('user', 'phone', 'is_approved')

    @admin.display(boolean=True, description='승인됨')
    def is_approved(self, obj):
        return obj.user.is_active
