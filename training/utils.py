import re


def get_video_embed_url(url):
    """Chuyển link YouTube/Vimeo sang URL embed iframe."""
    if not url:
        return None

    url = str(url).strip()

    youtube_match = re.search(
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})',
        url,
    )
    if youtube_match:
        return f'https://www.youtube.com/embed/{youtube_match.group(1)}'

    vimeo_match = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
    if vimeo_match:
        return f'https://player.vimeo.com/video/{vimeo_match.group(1)}'

    return None
