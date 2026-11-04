from django.urls import path, include
from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register('Post', views.IntruderImage)
router.register('StudySession', views.StudySessionViewSet, basename='studysession')

urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/new/', views.post_new, name='post_new'),
    path('post/<int:pk>/edit/', views.post_edit, name='post_edit'),
    path('post/<int:pk>/delete/', views.post_delete, name='post_delete'),
    path('signup/', views.signup, name='signup'),
    path('js_test/', views.js_test, name='js_test'),
    path('ranking/', views.ranking_page, name='ranking'),
    path('api_root/stats/', views.study_stats, name='study_stats'),
    path('api_root/ranking/', views.study_ranking, name='study_ranking'),
    path('api_root/', include(router.urls)),
]