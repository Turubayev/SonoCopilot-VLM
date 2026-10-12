# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata, collect_entry_point

root = Path(SPECPATH)
datas = [(str(root / name), '.') for name in ('index.html','app.js','style.css','THIRD_PARTY_NOTICES.md')]
datas += [(str(root / 'assets'), 'assets'), (str(root / 'packaging' / 'sonocopilot.ico'), 'packaging')]
datas += [(str(root / 'packaging' / 'licenses'), 'licenses')]
datas += collect_data_files('reportlab')
hiddenimports = collect_submodules('pydicom.pixels.decoders')
hiddenimports += collect_submodules('pydicom.pixels.encoders')
hiddenimports += collect_submodules('pylibjpeg') + collect_submodules('libjpeg') + collect_submodules('openjpeg')
for package in ('pylibjpeg','pylibjpeg-libjpeg','pylibjpeg-openjpeg'):
    datas += copy_metadata(package)
for group in ('pylibjpeg.pixel_data_decoders', 'pylibjpeg.jpeg_decoders', 'pylibjpeg.jpeg_ls_decoders', 'pylibjpeg.jpeg_2000_decoders'):
    more_data, more_imports = collect_entry_point(group)
    datas += more_data
    hiddenimports += more_imports

a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter','matplotlib','scipy','pandas','IPython','pytest'], noarchive=False)
# Qt 6.12 uses Windows' unversioned ICU API. A version-suffixed ICU DLL
# discovered on the build host's PATH must not shadow the Windows component.
# UCRT is also supplied by the supported Windows versions, not copied across OSes.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ('icuuc.dll', 'ucrtbase.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SonoCopilot',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon=str(root / 'packaging' / 'sonocopilot.ico'),
          version=str(root / 'packaging' / 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SonoCopilot')
