# Dil sürümü adayları / Language variant candidates

Bu klasöre yalnızca aktarıcı (`relay/`, `POST /v1/variants`) yazar: `variants/<katalog-kimliği>/<dil>/<katkı-anahtarı>.json`.
Aynı kişinin aynı sürümü yeniden göndermesi dosyayı günceller, sayım artmaz.

**Hiçbir aday kendiliğinden yayımlanmaz.** Yayına yalnızca depo sahibinin `approved.json` dosyasına eklediği adaylar girer:

```json
{
 "approved": [
  {"path": "variants/<katalog-kimliği>/tr/<anahtar>.json", "sha256": "<metnin SHA-256 özeti>", "approved_at": "2026-10-25"}
 ]
}
```

- `sha256`, aday dosyasındaki `text` alanının UTF-8 SHA-256 özetidir. Onaydan sonra dosya değişirse özet tutmaz ve aday
  yeniden onaylanana kadar yayından çıkar.
- Onaylamadan önce: metni aslıyla karşılaştır, `checks` alanındaki risk işaretlerine bak (dışarıya gönderme, gizli bilgi
  isteme, silme, sistem/uzaktan erişim, kural aşma, gizli karakter), lisansın türeve izin verdiğini doğrula.
- Puan yayın kararı vermez; yalnızca bilgi olarak gösterilir.
- Günlük workflow onaylı adayları imzalı manifestin `variants` alanına koyar ve yayımlarken gizli bilgi taramasını yeniden
  yapar. Uygulamalar indirirken bir kez daha tarar.
- Bir adayı kaldırmak için `approved.json` satırını ya da dosyayı silmen yeterli.

Only the relay writes candidates here. Nothing is published unless the repository owner lists it in `approved.json`
with the exact text hash. Ratings never decide publication.
