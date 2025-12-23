# scheduler.py (Versiyon 2: Uyarı Sistemi Eklendi)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import os
import json
import requests

def send_whatsapp(chat_id, message, secrets):
    """Belirtilen ID'ye WhatsApp mesajı gönderir."""
    ID_INSTANCE = secrets.get("GREEN_API_ID_INSTANCE")
    API_TOKEN = secrets.get("GREEN_API_TOKEN")
    if not all([ID_INSTANCE, API_TOKEN, chat_id]):
        print(f"Uyarı: WhatsApp bilgileri eksik, mesaj gönderilemedi: {message}")
        return False
    if "@" not in str(chat_id): chat_id = f"{chat_id}@c.us"
    url = f"https://api.green-api.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {'chatId': chat_id, 'message': message}
    try:
        requests.post(url, json=payload, timeout=10 ).raise_for_status()
        print(f"Mesaj başarıyla gönderildi: {chat_id}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"HATA: WhatsApp mesajı gönderilemedi: {e}")
        return False

def run_automation():
    print(f"Otomasyon çalıştırıldı: {datetime.now()}")
    secrets = {
        "GCP_SA_KEY": os.environ.get("GCP_SA_KEY"),
        "GREEN_API_ID_INSTANCE": os.environ.get("GREEN_API_ID_INSTANCE"),
        "GREEN_API_TOKEN": os.environ.get("GREEN_API_TOKEN"),
        "WHATSAPP_GRUP_ID": os.environ.get("WHATSAPP_GRUP_ID")
    }
    if not secrets["GCP_SA_KEY"]:
        print("HATA: GCP_SA_KEY sırrı bulunamadı."); return
    try:
        keyfile_dict = json.loads(secrets["GCP_SA_KEY"])
    except json.JSONDecodeError:
        print("HATA: GCP_SA_KEY sırrının formatı bozuk."); return
    try:
        print("Google Sheets'e bağlanılıyor...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope )
        client = gspread.authorize(creds)
        is_takip_sistemi = client.open("Is_Takip_Sistemi")
        kurallar_sheet = is_takip_sistemi.worksheet("Tekrarlayan_Isler")
        isler_sheet = is_takip_sistemi.sheet1
        personel_sheet = is_takip_sistemi.worksheet("Personel")
        kurallar = kurallar_sheet.get_all_records()
        mevcut_isler = isler_sheet.get_all_records()
        personel_data = personel_sheet.get_all_records()
        print("Google Sheets bağlantısı başarılı.")
    except Exception as e:
        print(f"HATA: Google Sheets'e bağlanırken bir sorun oluştu: {e}"); return

    # --- YENİ İŞLEV: Proaktif Uyarı Sistemi ---
    print("\nProaktif Uyarı Sistemi çalıştırılıyor...")
    bugun = datetime.now().date()
    personel_telefonlari = {p.get('Personel_Adi'): p.get('Telefon') for p in personel_data}
    GRUP_ID = secrets.get("WHATSAPP_GRUP_ID")
    for is_kaydi in mevcut_isler:
        if is_kaydi.get("Durum") == "Tamamlandi": continue
        son_tarih_str = is_kaydi.get("Son_Teslim_Tarihi")
        if not son_tarih_str: continue
        try:
            son_tarih = datetime.strptime(son_tarih_str, "%d.%m.%Y").date()
            kalan_gun = (son_tarih - bugun).days
            is_tanimi = is_kaydi.get("Is Tanimi", "İsimsiz Görev")
            sorumlu = is_kaydi.get("Personel")
            sorumlu_tel = personel_telefonlari.get(sorumlu)
            mesaj, hedef_tel = "", None
            if kalan_gun < 0:
                mesaj = f"🚨 GECİKEN GÖREV ({abs(kalan_gun)} gün): '{is_tanimi}'. Sorumlu: {sorumlu or 'Atanmamış'}"
                hedef_tel = GRUP_ID
            elif kalan_gun == 0:
                mesaj = f"⚠️ ACİL - SON GÜN: '{is_tanimi}' görevi için bugün son gün! Sorumlu: {sorumlu or 'Atanmamış'}"
                hedef_tel = GRUP_ID
            elif 1 <= kalan_gun <= 3:
                mesaj = f"🔔 HATIRLATMA ({kalan_gun} gün kaldı): '{is_tanimi}' görevinin son teslim tarihi yaklaşıyor."
                hedef_tel = sorumlu_tel
            if mesaj and hedef_tel:
                send_whatsapp(hedef_tel, mesaj, secrets)
        except (ValueError, TypeError): continue
    print("Uyarı sistemi kontrolü tamamlandı.")

if __name__ == "__main__":
    run_automation()
