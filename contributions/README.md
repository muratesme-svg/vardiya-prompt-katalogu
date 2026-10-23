# Katkılar / Contributions

Bu klasöre yalnızca değerlendirme aktarıcısı (`relay/`) yazar. Her dosya bir katkı anahtarıdır
(`<anahtar[0:2]>/<anahtar>.json`); aynı anahtar yeniden gönderilirse dosya güncellenir, sayım artmaz.
Günlük workflow geçerli dosyaları özetleyip imzalı manifestin `ratings` alanına yazar. Geçersiz dosyalar
atlanır; kişisel veri ya da gizli bilgi gibi görünen açıklamalar yayımlanmaz (puan yine sayılır).
Uygunsuz bir katkıyı silmek için dosyayı silmeniz yeterlidir; bir sonraki çalıştırmada özetten çıkar.

Only the rating relay writes here. One file per contribution key; re-sending replaces the file. The daily
workflow summarizes valid files into the signed manifest's `ratings` field. Delete a file to remove a
contribution.
