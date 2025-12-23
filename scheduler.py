# scheduler.py (Nihai ve Temiz Versiyon)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

def run_automation():
    """
    Bu fonksiyon, Tekrarlayan_Isler sayfasını okur ve günü gelen görevleri
    ana iş listesine (Sheet1) otomatik olarak ekler.
    """
    print(f"Otomasyon çalıştırıldı: {datetime.now()}")

    # --- Adım 1: Google Secrets'ı Güvenli Bir Şekilde Oku ---
    # Bu kod, GitHub Actions'a eklenen GCP_SA_KEY adlı sırrı okumaya çalışır.
    keyfile_dict_str = os.environ.get("GCP_SA_KEY")
    
    # Sırrın boş olup olmadığını kontrol et. Eğer boşsa, hata ver ve dur.
    if not keyfile_dict_str:
        print("HATA: GCP_SA_KEY adlı sır bulunamadı veya içeriği boş.")
        print("Lütfen GitHub reponuzun 'Settings > Secrets and variables > Actions' bölümünü kontrol edin.")
        return # Fonksiyonu burada sonlandır.

    # Sır metnini JSON formatına çevir.
    try:
        keyfile_dict = json.loads(keyfile_dict_str)
    except json.JSONDecodeError:
        print("HATA: GCP_SA_KEY sırrının formatı bozuk. Geçerli bir JSON değil.")
        print("Lütfen sırrın '{' ile başlayıp '}' ile bittiğinden ve içeriğinin doğru olduğundan emin olun.")
        return # Fonksiyonu burada sonlandır.

    # --- Adım 2: Google Sheets'e Bağlan ---
    try:
        print("Google Sheets'e bağlanılıyor...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope )
        client = gspread.authorize(creds)
        
        is_takip_sistemi = client.open("Is_Takip_Sistemi")
        kurallar_sheet = is_takip_sistemi.worksheet("Tekrarlayan_Isler")
        isler_sheet = is_takip_sistemi.sheet1
        
        kurallar = kurallar_sheet.get_all_records()
        mevcut_isler = isler_sheet.get_all_records()
        print("Google Sheets bağlantısı başarılı ve veriler okundu.")
    except Exception as e:
        print(f"HATA: Google Sheets'e bağlanırken veya veri okunurken bir sorun oluştu: {e}")
        return

    # --- Adım 3: Otomasyon Kurallarını İşle ---
    print("Otomasyon kuralları işleniyor...")
    bugun = datetime.now()
    yeni_gorev_sayisi = 0

    for kural in kurallar:
        # Kuralın aktif olup olmadığını kontrol et
        if kural.get("Aktif_Mi") != "EVET":
            continue

        kural_metni = kural.get("Tekrarlama_Kurali", "")
        
        # Kural metnini işle (örn: "Her Ayın 15'i")
        try:
            parcalar = kural_metni.split()
            kural_gun = int(parcalar[-2].replace("'", ""))
        except (ValueError, IndexError):
            print(f"Uyarı: '{kural_metni}' kuralı anlaşılamadı. Atlanıyor.")
            continue
        
        # Bugünün günü, kuraldaki güne uyuyor mu?
        if bugun.day == kural_gun:
            is_tanimi = f"{kural.get('Musteri_Adi')} - {kural.get('Is_Tanimi_Sablonu')}"
            
            # Bu görev bu ay zaten oluşturulmuş mu? Kontrol et.
            gorev_bu_ay_var_mi = False
            for is_kaydi in mevcut_isler:
                tarih_str = is_kaydi.get("Tarih", "")
                try:
                    is_tarihi = datetime.strptime(tarih_str, "%d.%m.%Y")
                    if (is_kaydi.get("Is Tanimi") == is_tanimi and 
                        is_tarihi.month == bugun.month and 
                        is_tarihi.year == bugun.year):
                        gorev_bu_ay_var_mi = True
                        break
                except (ValueError, TypeError):
                    continue
            
            # Eğer görev bu ay daha önce oluşturulmadıysa, şimdi oluştur.
            if not gorev_bu_ay_var_mi:
                print(f"Yeni görev oluşturuluyor: {is_tanimi}")
                yeni_satir = [
                    bugun.strftime("%d.%m.%Y"),
                    bugun.strftime("%H:%M"),
                    is_tanimi,
                    "Gonderildi",
                    "Bekliyor",
                    "-",
                    kural.get("Sorumlu_Personel", "")
                ]
                isler_sheet.append_row(yeni_satir)
                yeni_gorev_sayisi += 1

    if yeni_gorev_sayisi > 0:
        print(f"{yeni_gorev_sayisi} adet yeni görev başarıyla eklendi.")
    else:
        print("İşlem tamamlandı. Bugün için oluşturulacak yeni bir görev bulunamadı.")

if __name__ == "__main__":
    run_automation()
