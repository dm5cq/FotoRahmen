# -----------------------------------------------------------------------------
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: MIT
# -----------------------------------------------------------------------------
"""Erzeugt buildinfo/version_info.txt für PyInstaller (Windows).

Damit stehen Version und Copyright unter Windows in
„Eigenschaften → Details“ der FotoRahmen.exe. Die Werte kommen aus app_info.py.
"""
from pathlib import Path

import app_info

nums = [int(x) for x in app_info.VERSION.split(".")] + [0] * 4
v = tuple(nums[:4])

text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', '{app_info.AUTHOR}'),
      StringStruct('FileDescription', '{app_info.APP_NAME} – Rahmen für Fotos'),
      StringStruct('FileVersion', '{app_info.VERSION}'),
      StringStruct('InternalName', '{app_info.APP_NAME}'),
      StringStruct('LegalCopyright', '{app_info.COPYRIGHT}. {app_info.IMPLEMENTATION}'),
      StringStruct('OriginalFilename', '{app_info.APP_NAME}.exe'),
      StringStruct('ProductName', '{app_info.APP_NAME}'),
      StringStruct('ProductVersion', '{app_info.VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""

out = Path(__file__).resolve().parent / "buildinfo" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(text, encoding="utf-8")
print(f"geschrieben: {out}")
