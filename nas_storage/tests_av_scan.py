"""Test quét virus: giao thức INSTREAM, xử lý lỗi, và tích hợp vào upload guard."""

from __future__ import annotations

import io
import socket
import struct
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from nas_storage import av_scan
from nas_storage.av_scan import (
    RESULT_CLEAN,
    RESULT_ERROR,
    RESULT_INFECTED,
    RESULT_SKIPPED,
    ping,
    scan_stream,
    version,
)
from nas_storage.upload_guard import UploadRejected, validate_upload, validate_uploads

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64
PDF = b'%PDF-1.7\n' + b'0' * 64

AV_ON = dict(AV_SCAN_ENABLED=True, AV_CLAMD_HOST='clamav', AV_CLAMD_PORT=3310)


class FakeSocket:
    """Giả clamd — ghi lại byte nhận được, trả phản hồi cho trước."""

    def __init__(self, response: bytes, *, raise_on=None):
        self.response = response
        self.sent = bytearray()
        self._raise_on = raise_on
        self.closed = False
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        if self._raise_on == 'sendall':
            raise OSError('broken pipe')
        self.sent.extend(data)

    def recv(self, _n):
        if self._raise_on == 'recv':
            raise socket.timeout()
        data, self.response = self.response, b''
        return data

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True
        return False


def fake_conn(response: bytes, *, raise_on=None, capture=None):
    sock = FakeSocket(response, raise_on=raise_on)
    if capture is not None:
        capture.append(sock)

    def _create_connection(_addr, timeout=None):
        return sock

    return _create_connection


@override_settings(**AV_ON)
class InstreamProtocolTests(SimpleTestCase):
    def test_clean_response(self):
        with patch.object(socket, 'create_connection', fake_conn(b'stream: OK\0')):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_CLEAN)
        self.assertTrue(result.is_clean)

    def test_infected_response_extracts_signature(self):
        resp = b'stream: Eicar-Test-Signature FOUND\0'
        with patch.object(socket, 'create_connection', fake_conn(resp)):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_INFECTED)
        self.assertEqual(result.signature, 'Eicar-Test-Signature')

    def test_sends_correct_instream_framing(self):
        """zINSTREAM + (độ dài 4 byte big-endian + dữ liệu) + độ dài 0."""
        captured: list[FakeSocket] = []
        payload = b'A' * 100
        with patch.object(
            socket, 'create_connection',
            fake_conn(b'stream: OK\0', capture=captured),
        ):
            scan_stream(io.BytesIO(payload), size=len(payload))

        sent = bytes(captured[0].sent)
        self.assertTrue(sent.startswith(b'zINSTREAM\0'))
        body = sent[len(b'zINSTREAM\0'):]
        self.assertEqual(body[:4], struct.pack('!I', len(payload)))
        self.assertEqual(body[4:4 + len(payload)], payload)
        self.assertEqual(body[4 + len(payload):], struct.pack('!I', 0))

    def test_error_response(self):
        resp = b'INSTREAM size limit exceeded. ERROR\0'
        with patch.object(socket, 'create_connection', fake_conn(resp)):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_ERROR)
        self.assertIn('size limit', result.detail)

    def test_connection_refused_is_error_not_crash(self):
        def refuse(*_a, **_k):
            raise ConnectionRefusedError('nope')

        with patch.object(socket, 'create_connection', refuse):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_ERROR)

    def test_timeout_is_error_not_crash(self):
        with patch.object(
            socket, 'create_connection', fake_conn(b'', raise_on='recv'),
        ):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_ERROR)

    def test_seek_restored_after_scan(self):
        f = io.BytesIO(PNG)
        with patch.object(socket, 'create_connection', fake_conn(b'stream: OK\0')):
            scan_stream(f, size=len(PNG))
        self.assertEqual(f.tell(), 0)
        self.assertEqual(f.read(4), b'\x89PNG')

    @override_settings(AV_SCAN_MAX_BYTES=10)
    def test_oversize_skipped_without_connecting(self):
        def boom(*_a, **_k):
            raise AssertionError('không được kết nối clamd cho file quá lớn')

        with patch.object(socket, 'create_connection', boom):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_SKIPPED)

    def test_ping_and_version(self):
        with patch.object(socket, 'create_connection', fake_conn(b'PONG\0')):
            self.assertTrue(ping())
        with patch.object(socket, 'create_connection', fake_conn(b'ClamAV 1.4.1\0')):
            self.assertIn('ClamAV', version())

    def test_ping_false_when_unreachable(self):
        def refuse(*_a, **_k):
            raise OSError('down')

        with patch.object(socket, 'create_connection', refuse):
            self.assertFalse(ping())


class DisabledScannerTests(SimpleTestCase):
    @override_settings(AV_SCAN_ENABLED=False)
    def test_skipped_when_disabled(self):
        def boom(*_a, **_k):
            raise AssertionError('không được kết nối khi AV tắt')

        with patch.object(socket, 'create_connection', boom):
            result = scan_stream(io.BytesIO(PNG), size=len(PNG))
        self.assertEqual(result.status, RESULT_SKIPPED)

    @override_settings(AV_SCAN_ENABLED=False)
    def test_upload_guard_skips_scan_when_disabled(self):
        with patch.object(av_scan, 'scan_upload') as scan:
            validate_upload(SimpleUploadedFile('a.png', PNG))
        scan.assert_not_called()


@override_settings(**AV_ON)
class UploadGuardIntegrationTests(SimpleTestCase):
    def test_rejects_infected_upload(self):
        resp = b'stream: Win.Test.EICAR_HDB-1 FOUND\0'
        with patch.object(socket, 'create_connection', fake_conn(resp)):
            with self.assertRaises(UploadRejected) as ctx:
                validate_upload(SimpleUploadedFile('bao-cao.pdf', PDF))
        msg = ' '.join(ctx.exception.messages)
        self.assertIn('mã độc', msg)
        self.assertIn('Win.Test.EICAR_HDB-1', msg)

    def test_accepts_clean_upload(self):
        with patch.object(socket, 'create_connection', fake_conn(b'stream: OK\0')):
            self.assertEqual(
                validate_upload(SimpleUploadedFile('bao-cao.pdf', PDF)), 'bao-cao.pdf',
            )

    @override_settings(AV_FAIL_CLOSED=False)
    def test_fail_open_lets_file_through_when_scanner_down(self):
        def refuse(*_a, **_k):
            raise ConnectionRefusedError('down')

        with patch.object(socket, 'create_connection', refuse):
            self.assertEqual(
                validate_upload(SimpleUploadedFile('a.png', PNG)), 'a.png',
            )

    @override_settings(AV_FAIL_CLOSED=True)
    def test_fail_closed_rejects_when_scanner_down(self):
        def refuse(*_a, **_k):
            raise ConnectionRefusedError('down')

        with patch.object(socket, 'create_connection', refuse):
            with self.assertRaises(UploadRejected) as ctx:
                validate_upload(SimpleUploadedFile('a.png', PNG))
        self.assertIn('Chưa quét được virus', ' '.join(ctx.exception.messages))

    def test_cheap_checks_run_before_scanner(self):
        """File sai định dạng phải bị chặn mà không cần gọi scanner."""
        def boom(*_a, **_k):
            raise AssertionError('không được quét file đã bị từ chối')

        with patch.object(socket, 'create_connection', boom):
            with self.assertRaises(UploadRejected):
                validate_upload(SimpleUploadedFile('virus.exe', b'MZ\x90\x00'))

    def test_batch_validates_all_before_scanning_any(self):
        """Lô có 1 file sai định dạng thì không quét file nào."""
        def boom(*_a, **_k):
            raise AssertionError('không được quét khi lô đã có file sai')

        with patch.object(socket, 'create_connection', boom):
            with self.assertRaises(UploadRejected):
                validate_uploads([
                    SimpleUploadedFile('ok.png', PNG),
                    SimpleUploadedFile('bad.exe', b'MZ\x90\x00'),
                ])

    def test_batch_scans_every_file(self):
        captured: list[FakeSocket] = []

        def _create_connection(_addr, timeout=None):
            sock = FakeSocket(b'stream: OK\0')
            captured.append(sock)
            return sock

        with patch.object(socket, 'create_connection', _create_connection):
            validate_uploads([
                SimpleUploadedFile('a.png', PNG),
                SimpleUploadedFile('b.pdf', PDF),
            ])
        self.assertEqual(len(captured), 2)


@override_settings(**AV_ON)
class EicarEndToEndTests(SimpleTestCase):
    """Chuỗi EICAR phải đi qua đúng đường ống tới scanner."""

    def test_eicar_payload_reaches_scanner(self):
        from nas_storage.management.commands.av_status import EICAR

        captured: list[FakeSocket] = []
        resp = b'stream: Eicar-Test-Signature FOUND\0'
        with patch.object(
            socket, 'create_connection', fake_conn(resp, capture=captured),
        ):
            result = scan_stream(io.BytesIO(EICAR), size=len(EICAR))

        self.assertTrue(result.is_infected)
        self.assertIn(b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE', bytes(captured[0].sent))
