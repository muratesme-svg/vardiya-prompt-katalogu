# Vardiya Prompt Kataloğu / Vardiya Prompt Catalog

Windows ve Android Vardiya uygulamalarının kullandığı kaynak bağlantılı prompt kataloğu.
This public repository supplies the source-linked prompt catalog used by Vardiya for Windows and Android.

Her kayıt görev, bir veya birden fazla kategori (daima **Genel kullanım** dahil), dil, model ailesi, kaynak, kullanım hakkı, inceleme durumu ve uyarılarla aranabilir. Kaynak hakkı tam metni yeniden yayımlamaya izin vermiyorsa yalnızca açıklama ve kaynak bağlantısı tutulur. Konu başlığı tek başına kaydı silmez; tarama/risk bilgileri uyarı olarak gösterilir.

Records are searchable by task, one or more categories (always including **General use**), language, model family, source, reuse rights, review status, and warnings. When the source does not permit republishing the full text, the catalog keeps a description and source link. Topic alone does not remove a record; scan and risk findings are shown as warnings.

## Güncelleme / Updates

- GitHub Actions, depo kurulup imzalama etkinleştirildiğinde günde bir çalışır; ayrıca elle başlatılabilir.
- Her çalıştırma 18 İngilizce ve çok dilli arama sorgusundan kayan bir pencereyle 3 tanesini kullanır; en fazla 60 açık depoyu ve depo başına en fazla 2 prompt benzeri dosyayı inceler. Türkçe, Almanca, Fransızca, İspanyolca, Portekizce, Çince, Arapça, Rusça, Japonca, Korece, İtalyanca ve Hollandaca aramalar dahildir. Bu, tüm web'i tarama iddiası değildir.
- Tarayıcı yalnızca genel GitHub API/açık dosya içeriklerini okur; kaynak kodunu içe aktarmaz veya çalıştırmaz. API anahtarı yalnızca `api.github.com` isteklerinde kullanılır; `raw.githubusercontent.com` içeriklerine gönderilmez.
- Açıkça tanınan lisans ve yeniden dağıtım koşulları varsa tam metin alınabilir. Hak belirsizse, içerik çıkarılamıyorsa veya kaynak resmi model dokümantasyonuysa kayıt bağlantı-only kalır.
- Otomatik keşfedilen kayıtlar **aday** ve modelde denenmemiş olarak işaretlenir. Resmî sayfa olması da prompt başarısı kanıtı değildir.
- Dil, yazı sistemi açıkça ayırt edilebiliyorsa tahmin edilir; Latin alfabelerinde belirsizlik varsa `und` (bilinmiyor) kalır. Tahmin edilmiş dil doğrulanmış çeviri veya kalite iddiası değildir.
- Değişen katalog Ed25519 ile imzalanır. Vardiya imzayı ve her metnin SHA-256 özetini denetler; ağ/bozuk indirme durumunda son iyi kopyayı korur ve eski sürüme dönmeyi reddeder. İçerik değişmediyse yeni uygulama sürümü çıkarılmaz.
- Vardiya'nın arama sözcükleri, yazdığın promptlar, servis anahtarları, özel prompt koleksiyonların ve puanların bu depoya gönderilmez.

GitHub Actions imzalama için `VARDIYA_CATALOG_SIGNING_KEY_B64` adlı, `public_key.txt` ile eşleşen 32 baytlık Ed25519 tohumunun Base64 değerine ihtiyaç duyar. Gizli anahtarı Git'e, uygulamaya veya iş günlüklerine koyma. Otomasyonu açmadan önce çevrim dışı yedek bulundur. Gizli anahtar yoksa workflow yayın verisini değiştirmez.

İmzalama anahtarına erişebilen depo yazma yetkisi olan kişiler, GitHub Actions üzerinden anahtarı kullanabilir. Depo sahibinin `main` dalına yazma yetkisini sınırlaması ve dal koruması açması gerekir. Workflow yalnızca `main` üzerinde çalışır ve yalnızca bu depodaki katalog verisini güncellemek için `contents: write` kullanır.

## Haklar ve lisans otomasyonu / Rights and licensing automation

- Tarayıcı otomatik sinyallere bakar: GitHub'ın depo için tanıdığı lisans (SPDX kimliği) ve metindeki belirgin telif (`all rights reserved`, `copyright`, `adapted from` gibi) ya da kişisel veri (e-posta adresi, telefon numarası) işaretleri.
- Bu işlem tek tek her dosyanın yeniden dağıtım hakkını hukuken kesin olarak doğrulamaz. Depo lisansı, depodaki her dosyayı kapsamayabilir; başka kaynaktan kopyalanmış metinler gözden kaçabilir. Bu bir hukuki inceleme değildir.
- Hak belirsizse, lisans tanınmıyorsa ya da telif/kişisel veri işareti varsa tam metin kopyalanmaz; kayıtta yalnızca kaynak bağlantısı ve açıklama tutulur.
- Hak sahibiyseniz ve bir kaydın kaldırılmasını ya da düzeltilmesini istiyorsanız bu depoda konu (issue) açabilirsiniz.

- The crawler relies on automatic signals: the repository license recognized by GitHub (SPDX id) and obvious copyright (`all rights reserved`, `copyright`, `adapted from`, etc.) or personal-data (email address, phone number) markers in the text.
- This does not legally verify the redistribution rights of each individual file. A repository license may not cover every file in it, and text copied from elsewhere can be missed. It is not legal review.
- When rights are unclear, the license is not recognized, or a copyright/personal-data marker is found, the full text is not copied; only the source link and a description are kept.
- Rights holders can open an issue in this repository to request removal or correction of a record.

## Kullanıcı değerlendirmeleri / User ratings

Uygulamalar değerlendirmeleri cihazda tutar. Kullanıcı isterse, gönderilecek her alanı görüp onayladıktan sonra
anonim ya da kendi yazdığı adla katkı gönderebilir. Katkılar `relay/` aktarıcısı üzerinden `contributions/`
klasörüne yazılır; günlük workflow bunları özetleyip imzalı manifestin `ratings` alanına koyar. Aynı katkı
yeniden gönderilirse sayım artmaz. Puan, lisans ve güvenlik ayrı bilgilerdir; düşük puan hiçbir kaydı gizlemez.

Apps keep ratings on the device. Users may send a contribution (anonymous or with a display name they type)
after reviewing every field. Contributions go through `relay/` into `contributions/`; the daily workflow
summarizes them into the signed manifest's `ratings` field. Re-sent ratings are not double-counted.

## Görünürlük / Visibility

EXE ve APK varsayılan olarak **Orta** düzeyi kullanır. **Yok** tüm kayıtları gösterir; **Düşük** yalnızca aşırı/kritik risk etiketlileri gizler; **Orta** aday ve doğrulanmamış kayıtları gizler; **Yüksek** yalnızca onaylı/doğrulanmış/denenmiş ve düşük/orta riskli kayıtları gösterir. Kullanıcı daha geniş görünüm seçtiğinde uyarılar yine görünür. Kaydın konusu tek başına silme veya gizleme gerekçesi değildir; risk ve hassasiyet bulguları uyarı olarak gösterilir ve hangi kayıtların listeleneceği kullanıcının görünürlük tercihidir. Bu seçim Vardiya izinlerini, uygulama kurallarını veya model sağlayıcılarının kurallarını değiştirmez.

The topic of a record alone is never a reason to delete or hide it; risk and sensitivity findings are shown as warnings, and which records are listed is the user's visibility choice. This choice does not change Vardiya's permissions, app rules, or model providers' rules.

## Kapsam sınırları / Coverage limits

Hiçbir tarayıcı internetteki her promptu eksiksiz bulamaz: özel, silinmiş, giriş gerektiren, arama motorlarında görünmeyen veya yalnızca uygulama içinde bulunan kaynaklar keşfedilemez. Otomatik tarama yalnızca kamuya açık GitHub depolarını kapsar; genel web siteleri taranmaz (resmî üretici rehberleri sabit bağlantı olarak eklenir). Katalog her kayıt için kaynak gösterir. “Tüm dünyadaki en iyi promptlar” ya da modelde doğrulanmışlık garantisi vermez.

No crawler can collect every prompt on the internet: private, deleted, login-gated, unindexed, or app-only material is not discoverable. Automatic discovery covers public GitHub repositories only; general websites are not crawled (official vendor guides are added as fixed links). The catalog preserves provenance, but it does not claim to contain every prompt or guarantee model performance.

## Uygulama adresleri / App endpoints

- Manifest: `https://raw.githubusercontent.com/muratesme-svg/vardiya-prompt-katalogu/main/manifest.json`
- Signature: `https://raw.githubusercontent.com/muratesme-svg/vardiya-prompt-katalogu/main/manifest.json.sig`
- Windows bundle: `https://raw.githubusercontent.com/muratesme-svg/vardiya-prompt-katalogu/main/catalog.zip`
- Prompt text: `texts/<first-two-hash-characters>/<sha256>.txt`

Katalog verisi uygulama kodu değildir. İmzalı katalog güncellemesi Vardiya ayarlarını, izinlerini veya davranışını değiştiremez. Üçüncü taraf kaynak/lisans bildirimleri `LICENSES.md` dosyasındadır.
