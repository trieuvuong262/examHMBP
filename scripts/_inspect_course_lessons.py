from training.models import Course, Chapter, Lesson

for cid in (4, 5, 6, 7):
    c = Course.objects.get(id=cid)
    print('===', c.id, c.title, 'users', list(c.assigned_users.values_list('username', flat=True)))
    for ch in c.chapters.order_by('order'):
        print(' CH', ch.order, ch.title, 'n=', ch.lessons.count())
        for ls in ch.lessons.order_by('order')[:8]:
            print('   ', ls.order, ls.title[:80])
        if ch.lessons.count() > 8:
            print('    ...')
