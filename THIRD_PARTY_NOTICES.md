# Third-party components · SonoCopilot 1.0.0

This application bundles unmodified third-party libraries. Their copyright notices and license texts are included in `licenses/` inside the installed `_internal` directory, and in `packaging/licenses/` in the source archive. The font notice is in `assets/fonts/LICENSE_DEJAVU.txt`.

| Component | License / notices | Upstream |
|---|---|---|
| Python 3.12 | PSF license, bundled Python-LICENSE.txt | https://www.python.org/ |
| PySide6, shiboken6, Qt libraries | LGPL-3.0/GPL-3.0 or commercial alternative; this distribution uses the applicable open-source licenses | https://www.qt.io/ ; https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt WebEngine / Chromium | Qt LGPL-3.0/GPL alternatives and Chromium third-party notices | https://code.qt.io/cgit/qt/qtwebengine.git/ ; https://chromium.googlesource.com/chromium/src/+/main/LICENSE |
| NumPy | BSD and bundled third-party notices, see copied LICENSE.txt | https://numpy.org/ |
| Pillow | HPND / bundled codec licenses, see copied LICENSE | https://python-pillow.org/ |
| pydicom | MIT | https://github.com/pydicom/pydicom |
| pylibjpeg | MIT | https://github.com/pydicom/pylibjpeg |
| pylibjpeg-libjpeg | MIT wrapper and libjpeg/CharLS codec notices, copied LICENSE | https://github.com/pydicom/pylibjpeg-libjpeg |
| pylibjpeg-openjpeg | MIT wrapper and OpenJPEG BSD notices, copied LICENSE | https://github.com/pydicom/pylibjpeg-openjpeg |
| ReportLab | BSD, copied LICENSE; included font notices | https://www.reportlab.com/ |
| charset-normalizer | MIT | https://github.com/jawah/charset_normalizer |
| DejaVu Sans | Bitstream Vera font license / public-domain DejaVu additions | https://dejavu-fonts.github.io/ |
| PyInstaller bootloader | GPL with bootloader exception | https://pyinstaller.org/en/stable/license.html |
| Inno Setup installer engine | Inno Setup license | https://jrsoftware.org/files/is/license.txt |

Qt/PySide6 libraries are dynamically linked and shipped as replaceable DLLs/extensions under `_internal/`. The application does not restrict debugging, reverse engineering for library modifications, or replacement of LGPL components. To use a modified compatible library, replace the corresponding files in a copied portable directory, or rebuild the application with the source archive and `packaging/build.ps1`. Keep matching Qt/PySide6 versions and architecture. The full LGPL-3.0 and GPL-3.0 texts are included. Corresponding upstream source releases can be obtained from https://download.qt.io/official_releases/qt/ and https://code.qt.io/ ; library version records are included with their notices.

Ollama and Gemma weights are not bundled. Their separate installation/download is governed by their upstream licenses and model terms (https://ollama.com/library/gemma3).

The app icon was drawn for this project; it is not a copied third-party asset. This notice does not grant a commercial Qt license or make claims of clinical validation.
