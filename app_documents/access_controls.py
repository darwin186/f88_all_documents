# access_cpntrols.py
import unicodedata

from django.contrib.auth.models import User, Group, Permission
from app_documents.models import UserProfile, Shop , Region

class AccessControls:
    @staticmethod
    def _normalize_scope(value):
        normalized = unicodedata.normalize('NFKD', str(value or ''))
        return ''.join(char for char in normalized if char.isalnum()).casefold()

    @staticmethod
    def _is_nationwide_region(region):
        if region is None:
            return False
        region_name = AccessControls._normalize_scope(region.region_name)
        region_code = AccessControls._normalize_scope(region.region_code)
        return region_name in {'toanquoc', 'nationwide', 'all'} or region_code in {
            'toanquoc',
            'nationwide',
            'all',
        }

    @staticmethod
    def get_filters_for_user(user):
        ''' Returns the appropriate filter based on the user's group. '''
        if user.groups.filter(name='checker').exists():
            # Return a filter based on the user's region
            return AccessControls.get_region_filter_for_user(user)
        elif user.groups.filter(name='shop').exists():
            # If you are a shop user, return a filter based on the shop
            return AccessControls.get_shop_filter_for_user(user)
        elif user.groups.filter(name='admin').exists():
            # Return an empty filter for superuser; admin; can see everything
            return {}
        elif user.groups.filter(name='supervisor').exists():
            # If you are a supervisor, return a filter based on the region,
            return AccessControls.get_shop_filter_for_user(user)
        elif user.groups.filter(name='manager').exists():
            return AccessControls.get_shop_filter_for_user(user)
        # More conditions can be added here if there are more roles
        return {}  # Default to no filters if user role is not defined or doesn't need filters

    @staticmethod
    def get_region_filter_for_user(user):
        ''' Filter documents dựa trên region của các user.'''
        if user.groups.filter(name='checker').exists() :
            region = user.userprofile.region
            if AccessControls._is_nationwide_region(region):
                return {}
            return {'region_id': region.region_id if region else None}
        return {}

    @staticmethod
    def get_shop_filter_for_user(user):
        ''' Filter documents dựa trên shop của các user.'''
        if user.groups.filter(name='shop').exists() :
            shop_id = user.userprofile.shop_id
            return {'shop_id': shop_id}
        return {}

    @staticmethod
    def get_users_based_on_role(user):
        ''' Returns a QuerySet of users based on the role of the logged-in user '''
        # If the user is an admin, return all checkers and other admins
        if user.is_superuser:
            return User.objects.filter(groups__name__in=['checker', 'admin'])
        # If the user is a checker, return checkers only in the same region
        elif user.groups.filter(name='checker').exists():
            current_region = user.userprofile.region
            if AccessControls._is_nationwide_region(current_region):
                return User.objects.filter(groups__name__in=['checker', 'admin']).distinct()
            return User.objects.filter(
                groups__name__in=['checker','admin'],
                userprofile__region_id=current_region.region_id if current_region else None
            ).distinct()
        # Otherwise, return an empty queryset
        return User.objects.none()

    def get_regions_based_on_role(user):
        ''' Returns a QuerySet of regions based on the role of the logged-in user '''
        if user.is_superuser or user.groups.filter(name='admin'):
            return Region.objects.all()
        elif user.groups.filter(name='checker').exists():
            current_region = user.userprofile.region
            if AccessControls._is_nationwide_region(current_region):
                return Region.objects.all()
            return Region.objects.filter(region_id=current_region.region_id if current_region else None)
        return Region.objects.none()

    @staticmethod
    def filter_shop_region_based_on_role(user):
        ''' Trả về Filter là region_id của shop dựa trên role của user là checker
        '''
        if user.groups.filter(name='checker').exists():
            region = user.userprofile.region
            if AccessControls._is_nationwide_region(region):
                return {}
            return {'shop_id__region_id': region.region_id if region else None}
        return {}
