# Değerlendirme aktarıcısı / Rating relay

Vardiya'nın Windows ve Android uygulamalarından gelen, kullanıcının **gördüğü ve onayladığı** değerlendirme
katkısını alır ve bu depoya `contributions/<anahtar[0:2]>/<anahtar>.json` olarak yazar. Günlük workflow bu
dosyaları özetleyip imzalı manifestin `ratings` alanına koyar.

## Neden gerekli?

Anonim katkı, kullanıcının GitHub hesabı olmadan gönderilebilmeli. Uygulamaya yazma anahtarı konamaz (APK ve
EXE açılıp okunabilir). Bu yüzden anahtar yalnızca bu küçük aktarıcıda, sunucu tarafında durur.

## Gizlilik

- IP adresi, tarayıcı/uygulama bilgisi, çerez ve başlık saklanmaz ya da GitHub'a aktarılmaz.
- Paket katı biçimde doğrulanır: yalnızca 14 izinli alan, 0–10 puanlar, en çok 2000 karakter açıklama. Başka
  alan içeren paket reddedilir.
- Yalnızca yayımlanmış katalogda bulunan prompt kimlikleri kabul edilir.
- Dosya adı katkı anahtarıdır: aynı katkı yeniden gönderilirse dosya güncellenir, sayım artmaz.
- Kişisel veri ya da gizli bilgi gibi görünen açıklamalar yayın adımında manifeste konmaz (puan sayılır).

## Dil sürümü adayları (`POST /v1/variants`)

Aynı aktarıcı, kullanıcının onayladığı dil sürümü adaylarını da alır ve `variants/<katalog-kimliği>/<dil>/<anahtar>.json`
olarak yazar. **Aday yayımlanmaz:** yalnızca depo sahibinin `variants/approved.json` listesine eklediği ve metin özeti
tutan adaylar günlük workflow'la imzalı manifeste girer (bkz. `variants/README.md`).

- İkinci kilit: API anahtarı, parola, e-posta, telefon ya da kullanıcı adı içeren yol benzeri metin reddedilir
  (uygulama bunu zaten göndermeden önce durdurur; yayın adımı üçüncü kez denetler).
- Paket katı biçimde doğrulanır (16 izinli alan; en çok 20.000 karakter metin; amaç, tür ve risk kodları listeden).
- Bu yol eklendiği için aktarıcının yeniden yayına alınması gerekir: bu klasörde `npx wrangler deploy`.

## Kurulum (depo sahibi yapar; yaklaşık 15 dakika)

1. **GitHub anahtarı:** GitHub → Settings → Developer settings → Fine-grained tokens → yeni anahtar.
   Repository access: yalnızca `vardiya-prompt-katalogu`. Permissions: **Contents: Read and write**. Başka izin
   verme. Süre: 1 yıl önerilir.
2. **Cloudflare hesabı** aç (ücretsiz plan yeterli) ve bilgisayara Node.js kur.
3. Bu klasörde:
   ```
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN      # 1. adımdaki anahtarı yapıştır
   npx wrangler deploy
   ```
   Çıktıdaki adres örneğin `https://vardiya-rating-relay.<hesap>.workers.dev` olur.
4. **Uygulamalara adresi ver:** katkı adresi `https://.../v1/contributions` biçimindedir.
   - Windows: `prompt_degerlendirme.py` içindeki `VARSAYILAN_KATKI_ADRESI` değerine yaz (ya da
     `VARDIYA_KATKI_ADRESI` ortam değişkeni).
   - Android: APK'yı `--dart-define=VARDIYA_KATKI_ADRESI=https://.../v1/contributions` ile derle.
5. Deneme: uygulamada bir promptu değerlendir, "Katkı olarak paylaş" de; birkaç saniye içinde bu depoda
   `contributions/` altında dosya görünmeli. Ertesi günkü workflow çalışmasında manifestte `ratings` oluşur.

## Bakım

- Uygunsuz bir katkıyı kaldırmak için dosyasını silmek yeterli.
- Anahtarın süresi dolunca 1. ve 3. adımdaki `secret put` yenilenir.
- Kötüye kullanım olursa `wrangler.toml` içindeki istek sınırını düşür ya da aktarıcıyı geçici olarak kapat
  (`npx wrangler delete`); uygulamalar katkıları cihazda bekletmeye devam eder, hiçbir değerlendirme kaybolmaz.

---

Accepts confirmed rating packets from the Vardiya apps and stores them as `contributions/<key[0:2]>/<key>.json`.
The GitHub token (fine-grained, Contents read/write on this repository only) lives only in the worker. No IP
addresses or headers are stored. See the Turkish steps above for deployment.
