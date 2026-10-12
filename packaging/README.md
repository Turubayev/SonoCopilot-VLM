# Windows build

Build with Python 3.12 x64 on Windows 10 22H2 or Windows 11 and Inno Setup 6.7.3.

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r packaging/build-lock.txt
.\.venv-build\Scripts\python.exe packaging/prepare_assets.py
powershell -File packaging/build.ps1 -Python C:\path\to\.venv-build\Scripts\python.exe -ISCC C:\path\to\ISCC.exe -BuildRoot C:\temp\SonoCopilot-build -ReleaseDir C:\temp\SonoCopilot-release
```

`packaging/build-lock.txt` records the actual build environment. DLLs and shared libraries remain separate and replaceable in the onedir distribution. No code-signing certificate is configured.

## Synthetic smoke test

```powershell
SonoCopilot.exe --self-test C:\temp\SonoCopilot-smoke
```

The test uses generated images and text only. It verifies PNG, DICOM and JPEG 2000 decoding, Cyrillic PDF generation, the real packaged Qt/Chromium renderer, private browser profile, JavaScript errors and native JSON download. It outputs `desktop-smoke.json` and a screenshot and exits. No Ollama/model download is initiated.

For testing extraction and the uninstaller in an isolated temporary directory, the installer accepts `/TESTINSTALL /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOICONS /DIR="C:\temp\SonoCopilot-install-test"`. `/TESTINSTALL` disables uninstall-registry entries, shortcuts and automatic launch; ordinary installation retains them. Check the absolute test directory before running the generated uninstaller. Test mode does not change the installation destination automatically.

The research VLM integration is exercised with mocks in unit tests. Clinical model quality and compatibility with each Windows/GPU configuration are not validated by packaging tests.
