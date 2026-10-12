import pytest
from desktop import navigation_kind, safe_filename, LocalServer


def test_navigation_is_limited_to_local_app_and_trusted_https_links():
    assert navigation_kind('http://127.0.0.1:2345/api/config', 2345) == 'local'
    assert navigation_kind('https://ollama.com/download/windows', 2345) == 'external'
    for url in ['http://127.0.0.1:9999', 'file:///C:/secret.txt', 'javascript:alert(1)',
                'https://ollama.com.evil.test', 'https://user@github.com', 'https://github.com:8080',
                'https://[bad', 'https://unknown.invalid']:
        assert navigation_kind(url, 2345) == 'blocked'


def test_report_filename_cannot_escape_directory_or_use_devices():
    assert safe_filename(r'C:\secret\file.json') == 'file.json'
    assert safe_filename('../../sample.pdf') == 'sample.pdf'
    assert safe_filename('CON.json') == 'report-CON.json'
    for name in ['run.exe', 'a.json.exe', '', '.', 'x.html']:
        with pytest.raises(ValueError):
            safe_filename(name)


def test_local_server_uses_os_assigned_loopback_port_and_closes():
    import socket
    import urllib.request
    server = LocalServer()
    port = server.port
    assert server.httpd.server_address[0] == '127.0.0.1'
    server.start()
    try:
        with urllib.request.urlopen(server.url + '/api/config') as response:
            assert response.status == 200
    finally:
        server.stop()
    with socket.socket() as sock:
        sock.settimeout(.2)
        assert sock.connect_ex(('127.0.0.1', port)) != 0
