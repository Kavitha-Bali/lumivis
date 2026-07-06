from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class CustomRegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label='Email Address',
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
    )
    phone = forms.CharField(
        max_length=15,
        required=False,
        label='Phone Number',
        widget=forms.TextInput(attrs={'placeholder': '+91 9876543210'}),
    )

    class Meta:
        model  = User
        fields = ['username', 'email', 'phone', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user
