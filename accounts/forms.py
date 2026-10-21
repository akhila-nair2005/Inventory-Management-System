from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import User


class _BootstrapMixin:
    def _style_fields(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs['class'] = 'form-select'
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            else:
                widget.attrs['class'] = 'form-control'


class StaffCreateForm(_BootstrapMixin, forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'department', 'role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self._style_fields()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2:
            if p1 != p2:
                self.add_error('password2', "The two passwords don't match.")
            else:
                try:
                    validate_password(p1, User(
                        username=cleaned.get('username', ''), email=cleaned.get('email', '')
                    ))
                except forms.ValidationError as exc:
                    self.add_error('password1', exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.is_staff = (user.role == User.Role.ADMIN)  # only Admins open Django admin
        if commit:
            user.save()
        return user


class StaffUpdateForm(_BootstrapMixin, forms.ModelForm):
    new_password = forms.CharField(
        label='New password', required=False, widget=forms.PasswordInput,
        help_text='Leave blank to keep the current password.',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'role', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].label = 'Account active'
        self._style_fields()

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('new_password'):
            user.set_password(self.cleaned_data['new_password'])
        user.is_staff = user.is_superuser or user.role == User.Role.ADMIN
        if commit:
            user.save()
        return user
