"""Explicit, user-started download of one local vision model through Ollama."""
import json
import threading
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ModelDownload:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {'state': 'idle', 'status': '', 'completed': 0, 'total': 0}

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def start(self):
        with self._lock:
            if self._state['state'] == 'downloading':
                return dict(self._state)
            self._state = {'state': 'downloading', 'status': 'Подготовка загрузки…',
                           'completed': 0, 'total': 0}
        threading.Thread(target=self._run, daemon=True, name='model-download').start()
        return self.snapshot()

    def _run(self):
        request = urllib.request.Request('http://127.0.0.1:11434/api/pull',
            data=json.dumps({'model': 'gemma3:4b', 'stream': True}).encode(),
            headers={'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=120) as response:
                while True:
                    line = response.readline(65537)
                    if not line:
                        break
                    if len(line) > 65536:
                        raise ValueError('Invalid response')
                    event = json.loads(line)
                    if event.get('error'):
                        raise ValueError('Download failed')
                    if event.get('status') == 'success':
                        self._update(state='complete', status='Модель загружена.')
                        return
                    total = max(0, int(event.get('total', 0)))
                    completed = max(0, min(int(event.get('completed', 0)), total))
                    self._update(status='Загрузка модели…' if total else 'Проверка файлов модели…',
                                 total=total, completed=completed)
            raise ValueError('Incomplete stream')
        except Exception:
            self._update(state='error', status='Загрузка не завершена.',
                         error='Проверьте интернет, свободное место и работу Ollama. Повторная загрузка продолжит скачивание доступных частей.')
