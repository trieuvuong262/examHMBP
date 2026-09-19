"""Them playlist Kdenlive vao khoa 5.

Chay tren VPS:
  docker compose exec -T web python manage.py shell < scripts/seed_kdenlive_course_5.py
"""
from django.db import transaction
from training.models import Course, Chapter, Lesson

COURSE_ID = 5
DURATION = 30
VIDEOS = [
  {
    "index": 1,
    "id": "zYD0b8LpiQA",
    "title": "Learn Kdenlive in 30 Minutes - Video Editing Basics"
  },
  {
    "index": 2,
    "id": "tKNQv2GBRoc",
    "title": "Beginner Editing Advice - Edit Like a Pro"
  },
  {
    "index": 3,
    "id": "44ufamHGIgQ",
    "title": "How to Create Smooth Subtitle Animation - Kdenlive Tutorial"
  },
  {
    "index": 4,
    "id": "FUduKr3KLdw",
    "title": "Kdenlive - Master the Basics : Video Editing"
  },
  {
    "index": 5,
    "id": "l5pWghw9mm8",
    "title": "Create Teleportation Effect - Kdenlive Tutorial"
  },
  {
    "index": 6,
    "id": "ex7GoLFOnio",
    "title": "Zoom Transition - Kdenlive Tutorial"
  },
  {
    "index": 7,
    "id": "Ey5yfLIj590",
    "title": "Create Glitch Transition - Kdenlive Tutorial"
  },
  {
    "index": 8,
    "id": "JTWRb8IEUl0",
    "title": "Color Correction & Grading - Kdenlive Effects Tutorial"
  },
  {
    "index": 9,
    "id": "2RyBH7fs5q8",
    "title": "Introduction to Scopes - Kdenlive Tutorial"
  },
  {
    "index": 10,
    "id": "zKisJAr5noQ",
    "title": "Color Correction | Kdenlive Tutorial"
  },
  {
    "index": 11,
    "id": "q06ZBT8IPSE",
    "title": "Color Grading Process - Kdenlive Tutorial"
  },
  {
    "index": 12,
    "id": "1ut_P2qp-xI",
    "title": "Kdenlive Curves - Learn how these Effects work. #shorts #kdenlive #colorcorrection"
  },
  {
    "index": 13,
    "id": "HYAfkPTI4XE",
    "title": "Restore Audio - Kdenlive #shorts #kdenlive #fnuxttux #tutorial"
  },
  {
    "index": 14,
    "id": "cGNC7TBk_SY",
    "title": "How to Remove Green Screen - Kdenlive Tutorial"
  },
  {
    "index": 15,
    "id": "-KgdKX4UVew",
    "title": "Secondary Color Selection - Kdenlive Tutorial"
  },
  {
    "index": 16,
    "id": "pMrJ7lJP2Vs",
    "title": "Kdenlive Secondary Color Selection #shorts #kdenlive"
  },
  {
    "index": 17,
    "id": "kE85bq-qFLI",
    "title": "Transform Your Videos With Overlays - Kdenlive Tutorial"
  },
  {
    "index": 18,
    "id": "mfF_DEGylqY",
    "title": "Composite Fire Into Your Scenes - Kdenlive Tutorial"
  },
  {
    "index": 19,
    "id": "N-6Ui3VyDTM",
    "title": "LUTs Made Easy - Kdenlive Tutorial"
  },
  {
    "index": 20,
    "id": "nQxKwG8rUhU",
    "title": "Duplicate Yourself - Kdenlive Tutorial"
  },
  {
    "index": 21,
    "id": "rDGv8WEF87c",
    "title": "Boost Your Sound Quality - Kdenlive Tutorial"
  },
  {
    "index": 22,
    "id": "oLdYnkcLUWI",
    "title": "How to Mix Your Voice with Music - Kdenlive Tutorial"
  },
  {
    "index": 23,
    "id": "6zBnTBQQE94",
    "title": "How to Add a Drop Shadow to Text and Images - Kdenlive Tutorial"
  },
  {
    "index": 24,
    "id": "vR_3M9pnUBQ",
    "title": "How to Avoid Audio Clipping - Kdenlive Tutorial"
  },
  {
    "index": 25,
    "id": "Pd3thBbDDTA",
    "title": "Edit Faster with Real Time Playback – Kdenlive Tutorial"
  },
  {
    "index": 26,
    "id": "V0_yp-ziqvI",
    "title": "Smooth Transitions, Camera Shake, Drop Shadow - Kdenlive Tutorial"
  },
  {
    "index": 27,
    "id": "d8gj-DjdWgM",
    "title": "How to Remove Objects From Video - Kdenlive Tutorial"
  },
  {
    "index": 28,
    "id": "bS7M1MHhFq4",
    "title": "Remove Peopel and Objects From Video - #Kdenlive #tutorials"
  },
  {
    "index": 29,
    "id": "dQNe1Dju3qs",
    "title": "Video Noise Reduction - Kdenlive Tutorial"
  },
  {
    "index": 30,
    "id": "nVseXbfIltc",
    "title": "Speech To Text Generate Subtitles - Kdenlive Tutorial"
  },
  {
    "index": 31,
    "id": "3Qg6TS_FfXw",
    "title": "How To Use Text-Based Editing In Kdenlive - Tutorial"
  },
  {
    "index": 32,
    "id": "9PTqvcRobUw",
    "title": "How to Add Text to Videos - Kdenlive Tutorial"
  },
  {
    "index": 33,
    "id": "Qdm7rppCjz8",
    "title": "Create Vertical Workspace Layout - Kdenlive Tutorial"
  },
  {
    "index": 34,
    "id": "ymJ3jaBmwDY",
    "title": "Convert Horizontal Videos To Vertical - Kdenlive Tutorial"
  },
  {
    "index": 35,
    "id": "dDt6-Ms_LwA",
    "title": "Rounded Corners - Kdenlive Tutorial"
  },
  {
    "index": 36,
    "id": "S8-GYX2AYnM",
    "title": "Compositing Challenge: Lucifer Eyes - Kdenlive Tutorial"
  },
  {
    "index": 37,
    "id": "6eKXQyYguQI",
    "title": "How to Use Track Mattes in Kdenlive - Tutorial"
  },
  {
    "index": 38,
    "id": "nHO5bT4FcSY",
    "title": "7 Kdenlive Tips to Improve Your Workflow - Kdenlive Tutorial"
  },
  {
    "index": 39,
    "id": "eP9cO1LL5cQ",
    "title": "6 Kdenlive Tips for a Better Workflow - Kdenlive Tutorial"
  },
  {
    "index": 40,
    "id": "ZH9NqZrf5T8",
    "title": "5 Kdenlive Tips Improve Your Workflow - Kdenlive Tutorial"
  },
  {
    "index": 41,
    "id": "6h9oTbojmEI",
    "title": "4 Tips to Improve Your Workflow - Kdenlive Tutorial"
  },
  {
    "index": 42,
    "id": "E4QJ1ACSBf4",
    "title": "3 Kdenlive Tips for a Smoother Workflow"
  },
  {
    "index": 43,
    "id": "AWpKdPs3j64",
    "title": "How To Make A TikTok Edit In Kdenlive Full Tutorial"
  },
  {
    "index": 44,
    "id": "2HSQuZbNvQo",
    "title": "How to Export Your Videos - Kdenlive Tutorial"
  },
  {
    "index": 45,
    "id": "sTPtIdAg-qQ",
    "title": "Drag and Drop Presets - Kdenlive Tutorial"
  },
  {
    "index": 46,
    "id": "Gi5AETqAY48",
    "title": "Color Grading & Correction Basics - Kdenlive Tutorial"
  },
  {
    "index": 47,
    "id": "j7hNpRb3fNc",
    "title": "Remove Background Noise in Audacity - Kdenlive Tutorial"
  },
  {
    "index": 48,
    "id": "38C4II-8X3A",
    "title": "TikTok Twitch Shake Transition - Kdenlive Tutorial"
  },
  {
    "index": 49,
    "id": "o69g-U1OAVI",
    "title": "Slow Motion in Kdenlive - Time Remapping Tutorial"
  },
  {
    "index": 50,
    "id": "mvmdiz84Hrc",
    "title": "TikTok Aggressive Shake Effect - Kdenlive Tutorial"
  },
  {
    "index": 51,
    "id": "F1h6Kg-WLDE",
    "title": "Keyframe Interpolation - Kdenlive Tutorial"
  },
  {
    "index": 52,
    "id": "IA5ANd7pnak",
    "title": "Kdenlive Tutorial 52"
  },
  {
    "index": 53,
    "id": "4Pw9b6xhO_k",
    "title": "Object Mask - Kdenlive Tutorial"
  },
  {
    "index": 54,
    "id": "C8kIBtMjOig",
    "title": "Kdenlive 25 - Video Editor"
  },
  {
    "index": 55,
    "id": "JfqZEF58BBw",
    "title": "Behind the Scenes - Kdenlive Pomotional Video"
  },
  {
    "index": 56,
    "id": "E4wAZUXFJnA",
    "title": "Picture in Picture with Crop - Kdenlive Tutorial"
  },
  {
    "index": 57,
    "id": "AZgbqzQB81k",
    "title": "How to Add Timer Countdown - Kdenlive Tutorial"
  },
  {
    "index": 58,
    "id": "NtJitJGMb-4",
    "title": "Text Glow Effect - Kdenlive Tutorial"
  },
  {
    "index": 59,
    "id": "R-9RU8SGWXM",
    "title": "How to Highlight Text - Kdenlive Tutorial"
  },
  {
    "index": 60,
    "id": "N_xxBEwthAA",
    "title": "Create Dreamy Look Effect - Kdenlive Tutorial"
  },
  {
    "index": 61,
    "id": "ohKRcOJd7ss",
    "title": "Film Halation Effect - Kdenlive Tutorial"
  },
  {
    "index": 62,
    "id": "j7YpiLPG3CA",
    "title": "How to Make CRT Effect - Kdenlive Tutorial"
  },
  {
    "index": 63,
    "id": "LME1tJEaaC8",
    "title": "Learn Motion Tracking - Kdenlive Tutorial"
  },
  {
    "index": 64,
    "id": "1byNRYP_HVg",
    "title": "Sharpen Blurry Video - Kdenlive Tutorial"
  },
  {
    "index": 65,
    "id": "Kvg034LVKwg",
    "title": "Glaxnimate vs Friction for Motion Graphics | Kdenlive Tutorial"
  },
  {
    "index": 66,
    "id": "6UePY9iSLCU",
    "title": "Blender, Friction & Kdenlive - Animation Pipeline"
  },
  {
    "index": 67,
    "id": "cJX8igxK91E",
    "title": "Learn Kdenlive in 30 Minutes | Multilingual | Video Editing Basics"
  },
  {
    "index": 68,
    "id": "v_aRN4ADfGs",
    "title": "Kdenlive Video Editing - Master the Basics"
  },
  {
    "index": 69,
    "id": "vf3OJvkQ2VQ",
    "title": "Filmstrip Transition Animation Effect - Kdenlive Tutorial"
  },
  {
    "index": 70,
    "id": "4uWfPllnOgU",
    "title": "Fire Text Effect - Kdenlive Tutorial"
  },
  {
    "index": 71,
    "id": "kBPN3rTUcx4",
    "title": "Burning Text Effect - Kdenlive Tutorial"
  },
  {
    "index": 72,
    "id": "ebN-gNgvQAc",
    "title": "Halftone Effect - Kdenlive Tutorial"
  },
  {
    "index": 73,
    "id": "tHzP9kJQJeg",
    "title": "Masking & Transition Effects Editing - Kdenlive Tutorial"
  },
  {
    "index": 74,
    "id": "1N1SrSQm-s8",
    "title": "Render Video with Transparent Background - Kdenlive Tutorial"
  },
  {
    "index": 75,
    "id": "apAWsvH_G4k",
    "title": "How to Add Effects to Videos - Kdenlive Tutorial"
  },
  {
    "index": 76,
    "id": "KopkebjSorw",
    "title": "Faster Edit with Video Proxy Clips - Kdenlive Tutorial"
  },
  {
    "index": 77,
    "id": "8S_Yopn73t0",
    "title": "Import Image Sequence into Kdenlive - Kdenlive Tutorial"
  },
  {
    "index": 78,
    "id": "53PjZd5veCA",
    "title": "Freeze Frame Clone Trail Effect - Kdenlive Tutorial"
  },
  {
    "index": 79,
    "id": "2eKSbU3mI74",
    "title": "How to Ripple Delete - Kdenlive Tutorial"
  }
]

CHAPTERS = [
    ('Cơ bản', 1, 26),
    ('Nâng cao', 27, 50),
    ('Chuyên nghiệp', 51, 78),
]


def watch_url(video_id):
    return f'https://www.youtube.com/watch?v={video_id}'


course = Course.objects.filter(id=COURSE_ID).first()
if course is None:
    raise SystemExit('Khong tim thay khoa hoc id=5')

print('COURSE', course.pk, course.title)

by_index = {item['index']: item for item in VIDEOS}
created_chapters = 0
created_lessons = 0
skipped_lessons = 0

with transaction.atomic():
    existing_urls = set(
        Lesson.objects.filter(chapter__course=course)
        .exclude(video_url='')
        .exclude(video_url__isnull=True)
        .values_list('video_url', flat=True)
    )

    max_chapter_order = course.chapters.order_by('-order').values_list('order', flat=True).first() or 0

    for title, start, end in CHAPTERS:
        chapter = course.chapters.filter(title=title).first()
        if chapter is None:
            max_chapter_order += 1
            chapter = Chapter.objects.create(course=course, title=title, order=max_chapter_order)
            created_chapters += 1
            print('CHAPTER +', chapter.order, chapter.title)
        else:
            print('CHAPTER =', chapter.order, chapter.title)

        max_lesson_order = chapter.lessons.order_by('-order').values_list('order', flat=True).first() or 0
        for idx in range(start, end + 1):
            item = by_index.get(idx)
            if not item:
                print('MISSING index', idx)
                continue
            url = watch_url(item['id'])
            if url in existing_urls or chapter.lessons.filter(video_url=url).exists():
                skipped_lessons += 1
                continue
            max_lesson_order += 1
            lesson_title = item['title'] or f'Bai {idx}'
            Lesson.objects.create(
                chapter=chapter,
                title=lesson_title[:255],
                lesson_type='video',
                video_url=url,
                order=max_lesson_order,
                duration_estimate=DURATION,
            )
            existing_urls.add(url)
            created_lessons += 1

print('DONE chapters_new', created_chapters, 'lessons_new', created_lessons, 'skipped', skipped_lessons)
print('TOTAL lessons', Lesson.objects.filter(chapter__course=course).count())
