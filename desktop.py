"""Windows desktop launcher. The application and browser run entirely locally."""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_VERSION = "1.0.0"
APP_NAME = "SonoCopilot VLM"
EXTERNAL_HOSTS = {"ollama.com", "www.ollama.com", "github.com"}


def navigation_kind(url: str, port: int) -> str:
    """Never pass arbitrary schemes or local files to the operating system."""
    try:
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            return "blocked"
        if parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port:
            return "local"
        if parsed.scheme == "https" and parsed.hostname in EXTERNAL_HOSTS and parsed.port in (None, 443):
            return "external"
    except ValueError:
        pass
    return "blocked"


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:180]
    if not name or Path(name).suffix.lower() not in (".json", ".pdf"):
        raise ValueError("Unsupported report download")
    if name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "report-" + name
    return name


class LocalServer:
    def __init__(self):
        from server import Handler
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": .1}, name="SonoCopilot-local", daemon=True)
        self._started = False

    @property
    def port(self):
        return self.httpd.server_port

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread.start()
        self._started = True

    def stop(self):
        if self._started:
            self.httpd.shutdown()
            self.thread.join(timeout=3)
            self._started = False
        self.httpd.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", type=Path, metavar="OUTPUT_DIR", help="Run the packaged browser smoke test with synthetic data only")
    args = parser.parse_args(argv)
    runtime_result = {}
    if args.self_test:
        from runtime_check import check_runtime
        runtime_result = check_runtime(args.self_test)

    from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl, QStandardPaths
    from PySide6.QtGui import QIcon, QDesktopServices
    from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineDownloadRequest, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("SonoCopilot")
    icon_path = Path(__file__).parent / "packaging" / "sonocopilot.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    try:
        local = LocalServer()
        local.start()
    except Exception as exc:
        if args.self_test:
            raise
        QMessageBox.critical(None, APP_NAME, "Не удалось запустить локальный сервис. Закройте приложение и повторите запуск.\n" + type(exc).__name__)
        return 1

    class LocalOnlyRequests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            kind = navigation_kind(url.toString(), local.port)
            allowed = kind == "local" or url.scheme() in ("data", "blob")
            info.block(not allowed)

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, kind, is_main):
            policy = navigation_kind(url.toString(), local.port)
            if policy == "local":
                return True
            if policy == "external" and kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                QDesktopServices.openUrl(url)
            return False

        def javaScriptConsoleMessage(self, level, message, line, source):
            # A console message can contain clinical text. Do not persist or print it.
            if args.self_test and level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                window.smoke_errors.append({"line": line, "source": QUrl(source).path()})

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"{APP_NAME}  {APP_VERSION}")
            self.resize(1440, 960)
            self.setMinimumSize(900, 680)
            self.force_close = False
            self.close_pending = False
            self.downloads = set()
            self.smoke_errors = []
            self.smoke_complete = False
            self.smoke_data = {'runtime_checks': runtime_result}
            self.view = QWebEngineView(self)
            self.setCentralWidget(self.view)
            # An unnamed profile is off-the-record: no disk cache, cookies or localStorage.
            self.profile = QWebEngineProfile(self)
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.interceptor = LocalOnlyRequests(self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.page = Page(self.profile, self.view)
            self.view.setPage(self.page)
            settings = self.page.settings()
            for attribute in (QWebEngineSettings.WebAttribute.LocalStorageEnabled,
                              QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                              QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
                              QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                              QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls):
                settings.setAttribute(attribute, False)
            self.page.permissionRequested.connect(lambda permission: permission.deny())
            self.profile.downloadRequested.connect(self.download_requested)
            self.page.renderProcessTerminated.connect(self.renderer_failed)
            self.page.loadFinished.connect(self.loaded)
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.statusBar().showMessage("Локальное приложение · данные сеанса хранятся в памяти")
            self.view.setUrl(QUrl(local.url))

        def renderer_failed(self, *_):
            if args.self_test:
                return self.finish_smoke(False, "renderer_terminated")
            QMessageBox.critical(self, APP_NAME, "Окно приложения остановилось. Несохранённые изменения могли быть потеряны. Перезапустите приложение.")

        def loaded(self, ok):
            if not ok:
                if args.self_test:
                    return self.finish_smoke(False, "page_load_failed")
                QMessageBox.critical(self, APP_NAME, "Не удалось открыть интерфейс. Перезапустите приложение.")
            elif args.self_test:
                QTimer.singleShot(1500, self.run_smoke)

        def download_requested(self, download):
            try:
                name = safe_filename(download.suggestedFileName())
            except ValueError:
                download.cancel()
                return
            url = download.url().toString()
            if download.page() is not self.page or not (navigation_kind(url, local.port) == "local" or url.startswith(f"blob:{local.url}/")):
                download.cancel()
                return
            if args.self_test:
                selected = str(args.self_test.resolve() / name)
            else:
                extension = Path(name).suffix.lower()
                filters = "Протокол JSON (*.json)" if extension == ".json" else "Документ PDF (*.pdf)"
                initial = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)) / name)
                selected, _ = QFileDialog.getSaveFileName(self, "Сохранить протокол", initial, filters)
            if not selected:
                download.cancel()
                return
            target = Path(selected)
            download.setDownloadDirectory(str(target.parent))
            download.setDownloadFileName(target.name)
            self.downloads.add(download)
            download.isFinishedChanged.connect(lambda: self.download_finished(download, name, target))
            download.accept()

        def download_finished(self, download, name, target):
            if not download.isFinished():
                return
            self.downloads.discard(download)
            if download.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                if Path(name).suffix.lower() == ".json":
                    self.page.runJavaScript("if (window.sonoMarkSaved) window.sonoMarkSaved(" + json.dumps(name) + ");")
                self.statusBar().showMessage("Протокол сохранён", 6000)
                if args.self_test and name == "sonocopilot-selftest.json":
                    try:
                        self.smoke_data["native_download"] = json.loads(target.read_text(encoding="utf-8")) == {"synthetic": True, "text": "Тест УЗИ"}
                        self.view.grab().save(str(args.self_test / "desktop-window.png"))
                        self.finish_smoke(self.smoke_data["native_download"] and not self.smoke_errors and all(runtime_result.values()))
                    except Exception as exc:
                        self.finish_smoke(False, type(exc).__name__)
            else:
                if args.self_test:
                    return self.finish_smoke(False, "download_failed")
                QMessageBox.warning(self, APP_NAME, "Файл не сохранён. Проверьте доступ к выбранной папке и свободное место.")

        def closeEvent(self, event):
            if self.force_close:
                event.accept()
                return
            event.ignore()
            if self.close_pending:
                return
            self.close_pending = True
            self.page.runJavaScript("({dirty:!!window.sonoHasUnsavedChanges,busy:!!window.sonoIsBusy})", self.confirm_close)

        def confirm_close(self, state):
            self.close_pending = False
            state = state if isinstance(state, dict) else {}
            if state.get("dirty") or state.get("busy") or self.downloads:
                answer = QMessageBox.question(self, "Закрыть SonoCopilot?", "Есть несохранённые изменения или незавершённая операция. Закрыть приложение и удалить данные текущего сеанса из памяти?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.page.runJavaScript('if (window.sonoAllowClose) window.sonoAllowClose();', self.perform_close)

        def perform_close(self, _=None):
            self.force_close = True
            self.close()

        def run_smoke(self):
            # Only synthetic data; exercising the real packaged renderer and download.
            self.page.runJavaScript("JSON.stringify({title:document.title,body:document.body.innerText.length,forms:document.querySelectorAll('input,textarea,select').length})", self.smoke_dom)

        def smoke_dom(self, result):
            try:
                dom = json.loads(result)
                self.smoke_data.update({"dom": dom, "off_the_record": self.profile.isOffTheRecord(), "version": APP_VERSION})
                if dom["body"] < 300 or dom["forms"] < 5:
                    return self.finish_smoke(False, "incomplete_dom")
                self.page.runJavaScript("(() => {const b=new Blob([JSON.stringify({synthetic:true,text:'Тест УЗИ'})],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='sonocopilot-selftest.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),10000);})()")
            except Exception as exc:
                self.finish_smoke(False, type(exc).__name__)

        def finish_smoke(self, success, error=None):
            if self.smoke_complete:
                return
            self.smoke_complete = True
            self.smoke_data.update({"success": bool(success), "error": error, "javascript_errors": self.smoke_errors})
            (args.self_test / "desktop-smoke.json").write_text(json.dumps(self.smoke_data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.force_close = True
            app.exit(0 if success else 1)

    if args.self_test:
        args.self_test = args.self_test.resolve()
        args.self_test.mkdir(parents=True, exist_ok=True)
    window = Window()
    if not args.self_test:
        window.show()
    else:
        # Render without an interactive window; keep a real Qt/Chromium page.
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        window.show()
        QTimer.singleShot(45000, lambda: window.finish_smoke(False, "timeout"))
    try:
        result = app.exec()
    finally:
        window.force_close = True
        for download in tuple(window.downloads):
            download.cancel()
        window.view.setPage(None)
        window.page.deleteLater()
        app.processEvents()
        local.stop()
    return result


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except Exception as exc:
        if '--self-test' in sys.argv:
            import traceback
            destination = Path(sys.argv[sys.argv.index('--self-test') + 1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'desktop-smoke.json').write_text(json.dumps({
                'success': False, 'error': type(exc).__name__,
                'traceback': traceback.format_exc()}, ensure_ascii=False, indent=2), encoding='utf-8')
            raise SystemExit(1)
        raise
