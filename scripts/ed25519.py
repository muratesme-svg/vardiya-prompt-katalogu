"""Saf Python Ed25519 imzası (RFC 8032). Dış kütüphane gerektirmez.

Kural güncellemelerinin geliştiriciden geldiğini doğrulamak için kullanılır.
RFC 8032 bölüm 6'daki başvuru algoritmasını (genişletilmiş koordinatlar) izler;
hız önemli değildir, doğruluk önemlidir. Sabit zamanlı değildir: gizli anahtarla
imzalama yalnızca geliştiricinin kendi bilgisayarında yapılır, programın kendisi
sadece doğrulama yapar (doğrulamada gizli bilgi yoktur).

    acik_anahtar(gizli32) -> 32 bayt açık anahtar
    imzala(gizli32, mesaj) -> 64 bayt imza
    dogrula(acik32, mesaj, imza64) -> True/False  (bozuk girdide hata vermez, False döner)
"""
import hashlib

P = 2 ** 255 - 19                                   # alan asal sayısı
L = 2 ** 252 + 27742317777372353535851937790883648493  # grup mertebesi
D = (-121665 * pow(121666, P - 2, P)) % P
_KOK_EKSI_BIR = pow(2, (P - 1) // 4, P)             # sqrt(-1) mod p


def _sha512(veri):
    return hashlib.sha512(veri).digest()


def _sha512_mod_l(veri):
    return int.from_bytes(_sha512(veri), "little") % L


# Noktalar genişletilmiş koordinatlarda tutulur: (X, Y, Z, T), x = X/Z, y = Y/Z, x*y = T/Z
def _topla(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % P
    B = (a[1] + a[0]) * (b[1] + b[0]) % P
    C = 2 * a[3] * b[3] * D % P
    Dd = 2 * a[2] * b[2] % P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return (E * F % P, G * H % P, F * G % P, E * H % P)


def _carp(s, nokta):
    sonuc = (0, 1, 1, 0)                            # etkisiz öğe
    while s > 0:
        if s & 1:
            sonuc = _topla(sonuc, nokta)
        nokta = _topla(nokta, nokta)
        s >>= 1
    return sonuc


def _esit(a, b):
    if (a[0] * b[2] - b[0] * a[2]) % P != 0:
        return False
    return (a[1] * b[2] - b[1] * a[2]) % P == 0


def _x_bul(y, isaret):
    """y koordinatından x'i bulur. Geçersizse None döndürür."""
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if x2 == 0:
        return None if isaret else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * _KOK_EKSI_BIR % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != isaret:
        x = P - x
    return x


_GY = 4 * pow(5, P - 2, P) % P
_GX = _x_bul(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)                    # taban noktası


def _sikistir(nokta):
    zinv = pow(nokta[2], P - 2, P)
    x = nokta[0] * zinv % P
    y = nokta[1] * zinv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _ac(baytlar):
    if len(baytlar) != 32:
        return None
    y = int.from_bytes(baytlar, "little")
    isaret = y >> 255
    y &= (1 << 255) - 1
    x = _x_bul(y, isaret)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _gizli_genislet(gizli):
    if not isinstance(gizli, (bytes, bytearray)) or len(gizli) != 32:
        raise ValueError("gizli anahtar 32 bayt olmalı")
    h = _sha512(bytes(gizli))
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def acik_anahtar(gizli32: bytes) -> bytes:
    """32 baytlık gizli anahtardan 32 baytlık açık anahtarı üretir."""
    a, _ = _gizli_genislet(gizli32)
    return _sikistir(_carp(a, G))


def imzala(gizli32: bytes, mesaj: bytes) -> bytes:
    """Mesajı imzalar; 64 baytlık imza döndürür."""
    a, onek = _gizli_genislet(gizli32)
    A = _sikistir(_carp(a, G))
    mesaj = bytes(mesaj)
    r = _sha512_mod_l(onek + mesaj)
    R = _sikistir(_carp(r, G))
    h = _sha512_mod_l(R + A + mesaj)
    s = (r + h * a) % L
    return R + int.to_bytes(s, 32, "little")


def dogrula(acik32: bytes, mesaj: bytes, imza64: bytes) -> bool:
    """İmza bu açık anahtar ve bu mesaj için geçerliyse True. Hiçbir girdide hata vermez."""
    try:
        if not isinstance(acik32, (bytes, bytearray)) or len(acik32) != 32:
            return False
        if not isinstance(imza64, (bytes, bytearray)) or len(imza64) != 64:
            return False
        if not isinstance(mesaj, (bytes, bytearray)):
            return False
        acik32, imza64, mesaj = bytes(acik32), bytes(imza64), bytes(mesaj)
        A = _ac(acik32)
        if A is None:
            return False
        Rs = imza64[:32]
        R = _ac(Rs)
        if R is None:
            return False
        s = int.from_bytes(imza64[32:], "little")
        if s >= L:                                   # kanonik olmayan S reddedilir
            return False
        h = _sha512_mod_l(Rs + acik32 + mesaj)
        return _esit(_carp(s, G), _topla(R, _carp(h, A)))
    except Exception:
        return False
