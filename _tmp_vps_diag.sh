cd /opt/portaljustplay
docker compose logs --since=6h web 2>&1 | grep -iE 'UPLOAD_SCAN|clamd|Quét virus' | tail -15
echo '--- test scan'
docker compose exec -T web python manage.py shell -c "
import io
from nas_storage.av_scan import scan_stream
r = scan_stream(io.BytesIO(b'<html><head></head><body>hi</body></html>'))
print('SMALL', r.status, r.detail)
" 2>&1 | grep SMALL
echo '--- git'
git log -1 --oneline
ls xay_dung 2>&1 | head -3
