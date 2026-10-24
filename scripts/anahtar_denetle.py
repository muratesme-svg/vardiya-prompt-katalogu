#!/usr/bin/env python3
"""İmza anahtarını GitHub sırrına koymadan önce denetler. Anahtar ekranda GÖRÜNMEZ, hiçbir yere yazılmaz ya da
gönderilmez; yalnızca biçimi ve public_key.txt ile eşleşip eşleşmediği söylenir.

Kullanım (katalog_yayin_repo klasöründe):  python scripts\\anahtar_denetle.py
"""
import base64
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ed25519  # noqa: E402

ham = getpass.getpass("Anahtarı yapıştır (ekranda görünmez) ve Enter'a bas: ").strip()
if ham.startswith("-----BEGIN"):
    print("HATA: Bu bir PEM dosyası. Gereken: 32 baytlık anahtarın tek satırlık base64 hâli (44 karakter).")
    sys.exit(1)
try:
    anahtar = base64.b64decode(ham, validate=True)
except Exception:
    print(f"HATA: Geçerli base64 değil ({len(ham)} karakter). Boşluk, tırnak ya da satır sonu kalmış olabilir.")
    sys.exit(1)
if len(anahtar) != 32:
    print(f"HATA: Anahtar {len(anahtar)} bayt; 32 bayt olmalı.")
    sys.exit(1)
acik = base64.b64encode(ed25519.acik_anahtar(anahtar)).decode("ascii")
beklenen = (Path(__file__).resolve().parents[1] / "public_key.txt").read_text(encoding="ascii").strip()
if acik == beklenen:
    print("TAMAM: Anahtar doğru biçimde ve public_key.txt ile eşleşiyor. Bu metni GitHub sırrına aynen koyabilirsin.")
else:
    print("HATA: Biçim doğru ama bu anahtar public_key.txt ile EŞLEŞMİYOR (başka bir anahtar).")
    sys.exit(1)
