"""Desktop backend regression tests. Only synthetic data and mocked model I/O."""
import io
import json
import threading
from http.client import HTTPConnection
from unittest.mock import Mock

import pytest
from pypdf import PdfReader

import model_setup
import report_export
import server


@pytest.fixture
def workstation():
    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def request(httpd, method, path, data=None, **headers):
    conn = HTTPConnection('127.0.0.1', httpd.server_port, timeout=3)
    body = json.dumps(data).encode('utf-8') if data is not None else None
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_dynamic_port_config_and_security_headers(workstation):
    status, headers, body = request(workstation, 'GET', '/api/config')
    assert status == 200
    config = json.loads(body)
    assert config['token'] == server.TOKEN
    assert config['version'] == server.VERSION
    assert headers['Cache-Control'] == 'no-store'
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']


@pytest.mark.parametrize('headers', [
    {'Host': 'attacker.example'},
    {'Host': '127.0.0.1:1'},
    {'Origin': 'https://attacker.example'},
    {'Origin': 'null'},
    {'Sec-Fetch-Site': 'cross-site'},
    {'Sec-Fetch-Site': 'same-site'},
])
def test_config_rejects_rebinding_or_cross_origin(workstation, headers):
    status, _, body = request(workstation, 'GET', '/api/config', **headers)
    assert status == 403
    assert server.TOKEN.encode() not in body


def test_protected_get_and_post_require_token(workstation, monkeypatch):
    list_models = Mock(return_value={'models': ['test'], 'ollama_available': True})
    monkeypatch.setattr(server, 'list_models', list_models)
    for token in (None, 'incorrect'):
        headers = {} if token is None else {'X-Local-Token': token}
        assert request(workstation, 'GET', '/api/models', **headers)[0] == 403
        assert request(workstation, 'POST', '/api/export/pdf', {}, **headers)[0] == 403
    list_models.assert_not_called()
    allowed = {'X-Local-Token': server.TOKEN,
               'Origin': f'http://127.0.0.1:{workstation.server_port}',
               'Sec-Fetch-Site': 'same-origin'}
    assert request(workstation, 'GET', '/api/models', **allowed)[0] == 200
    list_models.assert_called_once()


def test_pdf_api_download_and_malformed_body(workstation):
    token = {'X-Local-Token': server.TOKEN}
    status, headers, body = request(workstation, 'POST', '/api/export/pdf',
        {'description': 'Тестовый протокол', 'conclusion': 'Данных недостаточно'}, **token)
    assert status == 200
    assert headers['Content-Type'] == 'application/pdf'
    assert body.startswith(b'%PDF-')
    assert request(workstation, 'POST', '/api/export/pdf', ['invalid'], **token)[0] == 400
    assert request(workstation, 'POST', '/api/export/pdf', {},
                   **(token | {'Content-Length': str(server.MAX_BODY + 1)}))[0] == 413


def test_analysis_is_serialized_and_lock_released_after_error(workstation, monkeypatch):
    token = {'X-Local-Token': server.TOKEN}
    analysis = Mock(side_effect=RuntimeError('SENSITIVE internal model message'))
    monkeypatch.setattr(server, 'analyze', analysis)
    with server.ANALYSIS_LOCK:
        assert request(workstation, 'POST', '/api/analyze', {}, **token)[0] == 409
    analysis.assert_not_called()
    status, _, body = request(workstation, 'POST', '/api/analyze', {}, **token)
    assert status == 400
    assert b'SENSITIVE' not in body
    assert not server.ANALYSIS_LOCK.locked()


@pytest.mark.parametrize('name,details', [
    ('model:cloud', {'capabilities': ['vision']}),
    ('model:4b-cloud', {'capabilities': ['vision']}),
    ('model:latest', {'capabilities': ['vision'], 'remote_host': 'cloud.example'}),
    ('model:latest', {'capabilities': ['vision'], 'remote_model': 'remote'}),
    ('text:latest', {'capabilities': ['completion']}),
])
def test_cloud_or_text_model_rejected_before_image_decode(monkeypatch, name, details):
    backend = Mock(side_effect=[{'models': [{'name': name}]}, details])
    convert = Mock()
    monkeypatch.setattr(server, 'ollama', backend)
    monkeypatch.setattr(server, 'convert_image', convert)
    with pytest.raises(ValueError):
        server.analyze({'model': name, 'images': ['synthetic placeholder'],
                        'privacy_confirmed': True})
    convert.assert_not_called()
    assert backend.call_count == 2


def test_model_listing_filters_cloud_text_and_failed_details(monkeypatch):
    names = ['vision:latest', 'text:latest', 'vision:cloud', 'broken:latest']
    responses = [{'models': [{'name': name} for name in names]},
                 {'capabilities': ['vision']}, {'capabilities': ['completion']},
                 {'capabilities': ['vision']}, OSError('test failure')]
    monkeypatch.setattr(server, 'ollama', Mock(side_effect=responses))
    assert server.list_models() == {'models': ['vision:latest'], 'ollama_available': True}


def extract_pdf(data):
    reader = PdfReader(io.BytesIO(report_export.make_pdf(data)))
    return reader, '\n'.join(page.extract_text() for page in reader.pages)


def test_pdf_russian_text_and_markup_stay_literal():
    markup = '<img src="file:///private"> & <b>не команда</b>'
    reader, text = extract_pdf({'organ': 'Щитовидная железа', 'description': markup,
        'conclusion': 'Тестовый черновик', 'status': 'Черновик',
        'provenance': {'provider': 'manual'}})
    assert 'Щитовидная железа' in text
    assert markup in text
    assert 'ЧЕРНОВИК' in text
    assert 'без ИИ-анализа' in text
    assert not reader.trailer['/Root'].get('/OpenAction')
    assert not reader.trailer['/Root'].get('/AcroForm')


def test_pdf_approval_requires_complete_doctor_record():
    fields = {'status': 'Проверено врачом', 'doctor': 'Тестовый врач',
              'description': 'Описание', 'conclusion': 'Заключение'}
    assert 'Проверено врачом' in extract_pdf(fields)[1]
    for missing in ('doctor', 'description', 'conclusion'):
        assert 'ЧЕРНОВИК' in extract_pdf(fields | {missing: ''})[1]


def test_pdf_long_protocol_spans_pages_and_preserves_end():
    description = ('Тестовое наблюдение.\n' * 650) + 'КОНЕЦПРОТОКОЛА'
    reader, text = extract_pdf({'description': description, 'conclusion': 'Без заключения'})
    assert len(reader.pages) >= 3
    assert 'КОНЕЦПРОТОКОЛА' in text
    assert all('SonoCopilot' in page.extract_text() for page in reader.pages)


@pytest.mark.parametrize('value', [None, 12, ['test'], 'x' * 16001],
                         ids=['null', 'number', 'list', 'oversized'])
def test_pdf_rejects_invalid_or_oversized_field(value):
    with pytest.raises(ValueError):
        report_export.make_pdf({'description': value})


def mock_download_stream(monkeypatch, stream):
    response = io.BytesIO(stream)
    opener = Mock()
    opener.open.return_value = response
    build = Mock(return_value=opener)
    monkeypatch.setattr(model_setup.urllib.request, 'build_opener', build)
    return opener, build


def test_download_success_tracks_progress_without_clinical_data(monkeypatch):
    stream = b'{"status":"pulling","total":100,"completed":40}\n{"status":"success"}\n'
    opener, build = mock_download_stream(monkeypatch, stream)
    download = model_setup.ModelDownload()
    download._run()
    result = download.snapshot()
    assert result['state'] == 'complete'
    assert result['total'] == 100
    assert result['completed'] == 40
    request_obj = opener.open.call_args.args[0]
    assert request_obj.full_url == 'http://127.0.0.1:11434/api/pull'
    assert json.loads(request_obj.data) == {'model': 'gemma3:4b', 'stream': True}
    assert build.call_args.args[0].proxies == {}
    assert isinstance(build.call_args.args[1], model_setup.NoRedirect)


@pytest.mark.parametrize('stream', [
    b'{"status":"pulling","total":100,"completed":40}\n',
    b'{"error":"PRIVATE download error"}\n',
    b'{invalid json}\n',
    b'x' * 65537,
    b'',
], ids=['truncated', 'error', 'bad-json', 'oversized', 'empty'])
def test_download_errors_and_truncated_stream_are_not_success(monkeypatch, stream):
    mock_download_stream(monkeypatch, stream)
    download = model_setup.ModelDownload()
    download._run()
    result = download.snapshot()
    assert result['state'] == 'error'
    assert 'PRIVATE' not in json.dumps(result)


def test_duplicate_download_start_spawns_once_and_retry_clears_error(monkeypatch):
    thread = Mock()
    monkeypatch.setattr(model_setup.threading, 'Thread', thread)
    download = model_setup.ModelDownload()
    assert download.start()['state'] == 'downloading'
    assert download.start()['state'] == 'downloading'
    assert thread.call_count == 1
    thread.return_value.start.assert_called_once()
    # The UI gets an independent snapshot, so changing it cannot change state.
    state = download.snapshot()
    state['state'] = 'error'
    assert download.snapshot()['state'] == 'downloading'
    download._update(state='error', error='Previous failure')
    assert 'error' not in download.start()
    assert thread.call_count == 2


def test_download_api_only_allows_supported_model(workstation, monkeypatch):
    backend, download = Mock(), Mock()
    download.start.return_value = {'state': 'downloading'}
    monkeypatch.setattr(server, 'ollama', backend)
    monkeypatch.setattr(server, 'MODEL_DOWNLOAD', download)
    headers = {'X-Local-Token': server.TOKEN}
    assert request(workstation, 'POST', '/api/model-download',
        {'model': 'other:cloud'}, **headers)[0] == 400
    backend.assert_not_called()
    download.start.assert_not_called()
    status, _, body = request(workstation, 'POST', '/api/model-download',
        {'model': 'gemma3:4b'}, **headers)
    assert status == 200
    assert json.loads(body)['state'] == 'downloading'
    backend.assert_called_once_with('/api/tags')
    download.start.assert_called_once()
