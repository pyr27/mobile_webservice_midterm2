from django import template

register = template.Library()


@register.filter
def hms(seconds):
    """초 -> 'H시간 M분 S초'."""
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return seconds
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}시간 {m}분 {s}초" if h else f"{m}분 {s}초"
