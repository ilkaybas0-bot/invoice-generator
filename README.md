# Fatura & Teklif Oluşturucu

Freelancer'lar, ajanslar ve küçük işletmeler için Streamlit tabanlı, profesyonel görünümlü PDF fatura/teklif oluşturma uygulaması.

## Kurulum ve Çalıştırma

```bash
cd invoice-generator
pip install -r requirements.txt
streamlit run app.py
```

Tarayıcı otomatik olarak `http://localhost:8501` adresini açar. Durdurmak için terminalde `Ctrl+C`.

## Özellikler

### Temel
- **Fatura / Teklif** seçimi, otomatik numaralandırma, düzenleme/son ödeme tarihi
- Firma (gönderen) ve müşteri bilgileri, logo yükleme
- Dinamik kalem tablosu (açıklama, miktar, birim fiyat) — toplamlar otomatik hesaplanır
- Profesyonel, temiz tasarımlı PDF çıktısı, indirilebilir

### Dil ve Para Birimi
- **Türkçe / İngilizce** arayüz ve PDF çıktısı (sidebar'daki 🌐 menüsünden değiştirilir)
- ₺ / $ / € / £ para birimi seçimi, dile göre doğru sayı formatı (TR: `1.234,50` — EN: `1,234.50`)
- Türkçe karakterler (ı, İ, ş, ğ, ö, ü, ç) ve ₺ simgesi PDF'te düzgün görünür

### KDV ve Fiyatlandırma
- Hızlı KDV butonları (%1, %10, %20) veya özel oran
- **KDV dahil / hariç** fiyat girişi seçeneği
- Sabit tutarlı indirim
- **Kısmi ödeme / avans takibi** — "Alınan Avans" girilince PDF'te Ödenen / Kalan Bakiye satırları otomatik çıkar

### Tasarım
- 5 renk teması (Mavi, Yeşil, Mor, Lacivert, Antrasit)
- İmza / kaşe görseli ekleme (PDF'in altına otomatik yerleşir)

### Kayıt ve Tekrar Kullanım
- **Firma profili**: Firma bilgileri + logo + imza kaydedilir, her açılışta otomatik yüklenir
- **Adres defteri**: Müşterileri kaydedip tek tıkla formu doldurabilirsiniz
- **Ürün/hizmet şablonları**: Sık kullanılan kalemleri kaydedip tabloya tek tıkla ekleyebilirsiniz
- **Tekrarlayan fatura şablonları**: Müşteri + kalemler + KDV + notlar dahil tüm formu şablon olarak kaydedip (aylık abonelik gibi) her ay tek tıkla yeniden kullanabilirsiniz

### Belge Yönetimi
- **Belge geçmişi**: Her oluşturulan PDF otomatik kaydedilir, tekrar indirilebilir veya silinebilir
- **Ödeme durumu**: Bekliyor / Ödendi olarak işaretleme, duruma göre filtreleme
- **Vadesi geçmiş uyarısı**: Son ödeme tarihi geçmiş ve bakiyesi kapanmamış faturalar kırmızı ⚠️ etiketiyle işaretlenir
- **Genel bakış paneli**: Toplam faturalandırılan tutar, belge sayısı, en çok kazandıran müşteriler, aylık gelir grafiği
- **Toplu dışa aktarma**: Tüm PDF'ler + müşteri listesi + geçmiş özet CSV'si tek bir ZIP dosyasında indirilebilir

### E-posta
- Oluşturulan PDF'i uygulama içinden doğrudan müşteriye SMTP üzerinden gönderme
- Gmail için: `smtp.gmail.com`, port `587`, kullanıcı adı olarak tam e-posta adresi ve **Google Uygulama Şifresi** (normal şifre değil) gerekir — [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- Şifre hiçbir yerde kalıcı olarak saklanmaz, sadece o oturumda hafızada tutulur

## Veri Nerede Saklanıyor?

Tüm veriler proje klasöründeki `data/` dizininde, yerel JSON dosyaları ve PDF'ler olarak tutulur:

```
data/
├── profile.json              # Firma profili (logo/imza dahil)
├── clients.json               # Adres defteri
├── item_templates.json        # Ürün/hizmet şablonları
├── recurring_templates.json   # Tekrarlayan fatura şablonları
├── history.json                # Belge geçmişi metadatası
└── documents/                  # Oluşturulan PDF'lerin kendisi
```

Bu klasör `.gitignore` ile versiyon kontrolünden hariç tutulmuştur — kişisel/müşteri verisi içerir, GitHub'a yüklenmez.

## Proje Yapısı

```
invoice-generator/
├── app.py                  # Streamlit arayüzü (tüm sayfa akışı)
├── requirements.txt
└── utils/
    ├── pdf_builder.py       # ReportLab ile PDF üretim motoru
    ├── storage.py            # Yerel JSON tabanlı kayıt/okuma
    ├── i18n.py                # Türkçe/İngilizce çeviri sözlüğü
    └── emailer.py             # SMTP e-posta gönderimi
```

## Sık Karşılaşılan Sorunlar

**"E-posta gönderilemedi: getaddrinfo failed"** → SMTP Sunucusu alanı boş veya yanlış. Gmail için `smtp.gmail.com` yazın.

**Gmail "Uygulama Şifreleri" seçeneğini göremiyorum** → Önce 2 Adımlı Doğrulamayı açın, sonra doğrudan [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) linkine gidin.

**Kod değişikliği yaptıktan sonra uygulama eski haliyle çalışıyor** → Terminalde `Ctrl+C` ile durdurup `streamlit run app.py` ile yeniden başlatın.
