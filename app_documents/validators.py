from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, ngettext_lazy

class CustomPasswordValidator:
    def __init__(self, min_length=8):
        self.min_length = min_length
    # This method is called when you run the validate() method of the validator
    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                ngettext_lazy(
                    'Mật khẩu của bạn phải chứa ít nhất %(min_length)d ký tự.', # singular
                    'Mật khẩu của bạn phải chứa ít nhất %(min_length)d ký tự.', # plural
                    self.min_length
                ) % {'min_length': self.min_length},
                code='password_too_short',
            )

        if not any(char.isdigit() for char in password):
            raise ValidationError(_('Mật khẩu phải chứa ít nhất một chữ số (0-9).'), code='password_no_number')
        
        if not any(char.isalpha() for char in password):
            raise ValidationError(_('Mật khẩu phải chứa ít nhất một ký tự chữ cái.'), code='password_no_letter')
        
        if not any(char.isupper() for char in password):
            raise ValidationError(_('Mật khẩu phải chứa ít nhất một chữ cái in hoa (A-Z).'), code='password_no_upper')
        
        if not any(char.islower() for char in password):
            raise ValidationError(_('Mật khẩu phải chứa ít nhất một chữ cái in thường (a-z).'), code='password_no_lower')

    def get_help_text(self):
        return ngettext_lazy(
            'Mật khẩu của bạn phải chứa ít nhất %(min_length)d ký tự, bao gồm cả chữ số, chữ cái in hoa, và chữ cái in thường.', # singular
            'Mật khẩu của bạn phải chứa ít nhất %(min_length)d ký tự, bao gồm cả chữ số, chữ cái in hoa, và chữ cái in thường.', # plural
            self.min_length
        ) % {'min_length': self.min_length}
        
    #
    