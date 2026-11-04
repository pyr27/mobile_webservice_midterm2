from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Post

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ('title', 'text', 'image',)


class SignupForm(UserCreationForm):
    phone = forms.RegexField(
        label="전화번호",
        regex=r'^[0-9\-]{9,13}$',
        error_messages={'invalid': "숫자와 '-'만 입력해주세요. (예: 010-1234-5678)"},
    )

    class Meta(UserCreationForm.Meta):
        fields = ('username',)
