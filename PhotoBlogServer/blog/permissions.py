from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """객체의 user가 요청 사용자 본인(또는 staff)일 때만 접근 허용."""

    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.user_id == request.user.id
