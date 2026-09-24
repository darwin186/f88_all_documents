def has_admin_docs_access(user) -> bool:
    """Return whether a user may access the administrative-document module."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user.groups.filter(name="checker").exists():
        return False
    return user.groups.filter(
        name__in=["administrative staff", "adminpaper"]
    ).exists()
