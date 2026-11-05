# 랭킹/공부세션 기능 제거 (편의 기능 범위 조정)
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0006_studysession'),
    ]

    operations = [
        migrations.DeleteModel(name='StudySession'),
    ]
