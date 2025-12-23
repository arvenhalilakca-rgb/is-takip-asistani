# scheduler.py (Versiyon 4: Aşırı Detaylı Konuşma Modu)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json
import requests

def print_report(status, message):
    print(f"[{status}] {message}")

def send_whatsapp(chat_id, message, secrets):
    # ... (Bu fonksiyon aynı, değişiklik yok) ...
    ID_INSTANCE = secrets.get("GREEN_API_ID_INSTANCE")
    API_TOKEN = secrets.get("GREEN_API_TOKEN")
    if not all([ID_INSTANCE, API_TOKEN, chat_id]):
        print_report("UYARI", f"WhatsApp bilgileri eksik, mesaj gönderilemedi.")
        return False
    if "@" not in str(chat_id): chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': message}
    try:
        response = requests.post(url, json=payload, timeout=10 )
        if response.status_code == 200:
            print_report("BAŞARI", f"Mesaj hedefe gönderildi: {chat_id}")
            return True
        else:
            print_report("HATA", f"WhatsApp API Hatası: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print_report("HATA", f"WhatsApp'a bağlanırken ağ hatası: {e}")
        return False

def run_automation():
    print("="*50)
    print(f"Otomasyon Başlatıldı (Aşırı Detaylı Mod): {datetime.now()}")
    print("="*50)

    # --- Adım 1: Sırları Oku ---
    secrets = {
        "GCP_SA_KEY": os.environ.get("GCP_SA_KEY"),
        "GREEN_API_ID_INSTANCE": os.environ.get("GREEN_API_ID_INSTANCE"),
        "GREEN_API_TOKEN": os.environ.get("GREEN_API_TOKEN"),
        "WHATSAPP_GRUP_ID": os.environ.get("WHATSAPP_GRUP_ID")
    }
    if not secrets["GCP_SA_KEY"]: print_report("HATA", "GCP_SA_KEY sırrı bulunamadı."); return
    
    # --- Adım 2: Google Sheets'e Bağlan ---
    try:
        keyfile_dict = json.loads(secrets["GCP_SA_KEY"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope )
        client = gspread.authorize(creds)
        is_takip_sistemi = client.open("Is_Takip_Sistemi")
        isler_sheet = is_takip_sistemi.worksheet("Sheet1")
        personel_sheet = is_takip_sistemi.worksheet("Personel")
        mevcut_isler = isler_sheet.get_all_records()
        personel_data = personel_sheet.get_all_records()
        print_report("OK", "Tüm Google Sheets verileri başarıyla okundu.")
    except Exception as e:
        print_report("HATA", f"Google Sheets'e bağlanırken kritik hata: {e}"); return

    # --- Adım 3: Proaktif Uyarı Sistemi (Detaylı Konuşma Modu) ---
    print("\n" + "-"*50)
    print_report("BİLGİ", "Proaktif Uyarı Sistemi Başlatılıyor...")
    bugun = datetime.now().date()
    print_report("BİLGİ", f"Bugünün tarihi: {bugun.strftime('%d.%m.%Y')}")
    
    personel_telefonlari = {str(p.get('Personel_Adi')).strip(): str(p.get('Telefon')).strip() for p in personel_data}
    print_report("BİLGİ", f"Telefon rehberi oluşturuldu: {personel_telefonlari}")
    
    GRUP_ID = secrets.get("WHATSAPP_GRUP_ID")
    uyari_gonderilecek_is_sayisi = 0

    if not mevcut_isler:
        print_report("UYARI", "'Sheet1' sayfasında hiç görev bulunamadı."); return

    for i, is_kaydi in enumerate(mevcut_isler):
        print("\n" + f"--- Görev {i+1} Kontrol Ediliyor ---")
        is_tanimi = is_kaydi.get("Is Tanimi", "İsimsiz Görev")
        print_report("GÖREV", f"'{is_tanimi}'")

        # 1. Kontrol: Görev tamamlanmış mı?
        durum = str(is_kaydi.get("Durum", "")).strip()
        if durum.lower() == "tamamlandi":
            print_report("ATLANDI", "Görevin durumu 'Tamamlandi'.")
            continue
        print_report("OK", f"Görevin durumu: '{durum}' (Devam ediyor).")

        # 2. Kontrol: Son teslim tarihi var mı?
        son_tarih_str = str(is_kaydi.get("Son_Teslim_Tarihi", "")).strip()
        if not son_tarih_str:
            print_report("ATLANDI", "Görevin son teslim tarihi belirtilmemiş.")
            continue
        print_report("OK", f"Görevin son teslim tarihi: '{son_tarih_str}'.")

        # 3. Kontrol: Tarih formatı doğru mu?
        try:
            son_tarih = datetime.strptime(son_tarih_str, "%d.%m.%Y").date()
        except (ValueError, TypeError):
            print_report("UYARI", "Tarih formatı anlaşılamadı (GG.AA.YYYY olmalı). Atlanıyor.")
            continue
        
        # 4. Kontrol: Uyarı göndermeye değer mi?
        kalan_gun = (son_tarih - bugun).days
        sorumlu = str(is_kaydi.get("Personel", "")).strip()
        mesaj, hedef_tel = "", None

        if kalan_gun < 0:
            print_report("KARAR", f"Görev {abs(kalan_gun)} gün gecikmiş. GRUP mesajı hazırlanacak.")
            mesaj = f"🚨 GECİKEN GÖREV ({abs(kalan_gun)} gün): '{is_tanimi}'. Sorumlu: {sorumlu or 'Atanmamış'}"
            hedef_tel = GRUP_ID
        elif kalan_gun == 0:
            print_report("KARAR", "Görevin son günü. GRUP mesajı hazırlanacak.")
            mesaj = f"⚠️ ACİL - SON GÜN: '{is_tanimi}' görevi için bugün son gün! Sorumlu: {sorumlu or 'Atanmamış'}"
            hedef_tel = GRUP_ID
        elif 1 <= kalan_gun <= 3:
            print_report("KARAR", f"Görevin son tarihine {kalan_gun} gün kalmış. PERSONEL hatırlatması hazırlanacak.")
            if not sorumlu:
                print_report("UYARI", "Sorumlu atanmamış, hatırlatma mesajı gönderilemiyor.")
                continue
            sorumlu_tel = personel_telefonlari.get(sorumlu)
            if not sorumlu_tel:
                print_report("UYARI", f"'{sorumlu}' isimli personelin telefonu rehberde bulunamadı. (İsimler eşleşmiyor olabilir).")
                continue
            mesaj = f"🔔 HATIRLATMA ({kalan_gun} gün kaldı): '{is_tanimi}' görevinin son teslim tarihi yaklaşıyor."
            hedef_tel = sorumlu_tel
        else:
            print_report("ATLANDI", f"Görevin son tarihine daha var ({kalan_gun} gün).")
            continue
        
        # 5. Mesaj Gönderme
        if mesaj and hedef_tel:
            uyari_gonderilecek_is_sayisi += 1
            send_whatsapp(hedef_tel, mesaj, secrets)
        else:
            print_report("BİLGİ", "Mesaj gönderme koşulları oluşmadı.")

    print("\n" + "="*50)
    if uyari_gonderilecek_is_sayisi == 0:
        print_report("SONUÇ", "Tüm görevler kontrol edildi ancak uyarı gönderilecek bir durum bulunamadı.")
    else:
        print_report("SONUÇ", f"{uyari_gonderilecek_is_sayisi} adet uyarı mesajı gönderildi/gönderilmeye çalışıldı.")
    print("="*50)

if __name__ == "__main__":
    run_automation()
