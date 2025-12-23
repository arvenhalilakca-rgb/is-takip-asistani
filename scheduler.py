# scheduler.py

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

def run_automation():
    print(f"Otomasyon çalıştırıldı: {datetime.now()}")

    # --- Google Secrets ---
    # GitHub Actions'da secrets'ı environment variable olarak alacağız
    keyfile_dict_str = os.environ.get("GCP_SA_KEY")
    if not keyfile_dict_str:
        print("Hata: GCP_SA_KEY environment variable bulunamadı.")
        return
    keyfile_dict = json.loads(keyfile_dict_str)

    # --- Google Sheets Bağlantısı ---
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope)
        client = gspread.authorize(creds)
        
        is_takip_sistemi = client.open("Is_Takip_Sistemi")
        kurallar_sheet = is_takip_sistemi.worksheet("Tekrarlayan_Isler")
        isler_sheet = is_takip_sistemi.sheet1
        
        kurallar = kurallar_sheet.get_all_records()
        mevcut_isler = isler_sheet.get_all_records()
    except Exception as e:
        print(f"Google Sheets'e bağlanırken hata oluştu: {e}")
        return

    # --- Otomasyon Mantığı ---
    bugun = datetime.now()
    yeni_gorev_eklendi = False

    for kural in kurallar:
        if kural.get("Aktif_Mi") != "EVET":
            continue

        kural_metni = kural.get("Tekrarlama_Kurali", "")
        
        # Kuralı işle: "Her Ayın 15'i" gibi
        try:
            parcalar = kural_metni.split()
            kural_gun = int(parcalar[-2].replace("'", ""))
        except (ValueError, IndexError):
            continue

        # Bugünün günü kurala uyuyor mu?
        if bugun.day == kural_gun:
            # Bu görev bu ay zaten oluşturulmuş mu? Kontrol et.
            is_tanimi = f"{kural.get('Musteri_Adi')} - {kural.get('Is_Tanimi_Sablonu')}"
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
                except ValueError:
                    continue
            
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
                yeni_gorev_eklendi = True

    if yeni_gorev_eklendi:
        print("Yeni görevler başarıyla eklendi.")
    else:
        print("Bugün için oluşturulacak yeni bir görev bulunamadı.")

if __name__ == "__main__":
    run_automation()
