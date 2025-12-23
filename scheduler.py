# scheduler.py (Versiyon 3: Akıllı Teşhis Modu)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json
import requests

# === TEŞHİS RAPORU İÇİN YARDIMCI FONKSİYON ===
def print_report(status, message):
    """Loglara daha okunaklı raporlar yazdırmak için kullanılır."""
    print(f"[{status}] {message}")

# === WHATSAPP GÖNDERME FONKSİYONU ===
def send_whatsapp(chat_id, message, secrets):
    ID_INSTANCE = secrets.get("GREEN_API_ID_INSTANCE")
    API_TOKEN = secrets.get("GREEN_API_TOKEN")
    if not all([ID_INSTANCE, API_TOKEN, chat_id]):
        print_report("UYARI", f"WhatsApp bilgileri eksik, mesaj gönderilemedi: {message}")
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

# === ANA OTOMASYON FONKSİYONU ===
def run_automation():
    print("="*40)
    print(f"Otomasyon Başlatıldı: {datetime.now()}")
    print("="*40)
    print_report("BİLGİ", "Teşhis Raporu Başlatılıyor...")

    # --- Adım 1: Tüm Sırları Oku ve Kontrol Et ---
    secrets = {
        "GCP_SA_KEY": os.environ.get("GCP_SA_KEY"),
        "GREEN_API_ID_INSTANCE": os.environ.get("GREEN_API_ID_INSTANCE"),
        "GREEN_API_TOKEN": os.environ.get("GREEN_API_TOKEN"),
        "WHATSAPP_GRUP_ID": os.environ.get("WHATSAPP_GRUP_ID")
    }
    
    if secrets["GCP_SA_KEY"]: print_report("OK", "GCP_SA_KEY sırrı başarıyla okundu.")
    else: print_report("HATA", "GCP_SA_KEY sırrı bulunamadı veya boş. Lütfen GitHub Secrets'ı kontrol edin."); return

    if secrets["GREEN_API_ID_INSTANCE"]: print_report("OK", "GREEN_API_ID_INSTANCE sırrı okundu.")
    else: print_report("UYARI", "GREEN_API_ID_INSTANCE sırrı eksik. Mesaj gönderilemeyebilir.")

    if secrets["GREEN_API_TOKEN"]: print_report("OK", "GREEN_API_TOKEN sırrı okundu.")
    else: print_report("UYARI", "GREEN_API_TOKEN sırrı eksik. Mesaj gönderilemeyebilir.")

    if secrets["WHATSAPP_GRUP_ID"]: print_report("OK", f"WHATSAPP_GRUP_ID okundu. Değer: {secrets['WHATSAPP_GRUP_ID']}")
    else: print_report("UYARI", "WHATSAPP_GRUP_ID sırrı eksik. Grup mesajları gönderilemeyebilir.")

    # --- Adım 2: Google Sheets'e Bağlan ---
    try:
        keyfile_dict = json.loads(secrets["GCP_SA_KEY"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope )
        client = gspread.authorize(creds)
        is_takip_sistemi = client.open("Is_Takip_Sistemi")
        print_report("OK", "Google Sheets'e başarıyla bağlanıldı ve 'Is_Takip_Sistemi' dosyası açıldı.")
        
        isler_sheet = is_takip_sistemi.worksheet("Sheet1")
        personel_sheet = is_takip_sistemi.worksheet("Personel")
        
        mevcut_isler = isler_sheet.get_all_records()
        personel_data = personel_sheet.get_all_records()
        print_report("OK", "'Sheet1' ve 'Personel' sayfalarındaki veriler başarıyla okundu.")
    except json.JSONDecodeError:
        print_report("HATA", "GCP_SA_KEY sırrının formatı bozuk. Geçerli bir JSON değil."); return
    except gspread.exceptions.WorksheetNotFound as e:
        print_report("HATA", f"Google Sheet'te sayfa bulunamadı: {e}. Lütfen sayfa adlarını kontrol edin ('Sheet1', 'Personel')."); return
    except Exception as e:
        print_report("HATA", f"Google Sheets'e bağlanırken beklenmedik bir sorun oluştu: {e}"); return

    # --- Adım 3: Proaktif Uyarı Sistemi ---
    print("\n" + "-"*40)
    print_report("BİLGİ", "Proaktif Uyarı Sistemi çalıştırılıyor...")
    bugun = datetime.now().date()
    personel_telefonlari = {p.get('Personel_Adi'): p.get('Telefon') for p in personel_data}
    GRUP_ID = secrets.get("WHATSAPP_GRUP_ID")
    uyari_gonderilecek_is_sayisi = 0

    for is_kaydi in mevcut_isler:
        if is_kaydi.get("Durum") == "Tamamlandi": continue
        son_tarih_str = is_kaydi.get("Son_Teslim_Tarihi")
        if not son_tarih_str: continue
        
        try:
            son_tarih = datetime.strptime(son_tarih_str, "%d.%m.%Y").date()
            kalan_gun = (son_tarih - bugun).days
            is_tanimi = is_kaydi.get("Is Tanimi", "İsimsiz Görev")
            sorumlu = is_kaydi.get("Personel")
            
            mesaj, hedef_tel = "", None

            if kalan_gun < 0:
                mesaj = f"🚨 GECİKEN GÖREV ({abs(kalan_gun)} gün): '{is_tanimi}'. Sorumlu: {sorumlu or 'Atanmamış'}"
                hedef_tel = GRUP_ID
            elif kalan_gun == 0:
                mesaj = f"⚠️ ACİL - SON GÜN: '{is_tanimi}' görevi için bugün son gün! Sorumlu: {sorumlu or 'Atanmamış'}"
                hedef_tel = GRUP_ID
            elif 1 <= kalan_gun <= 3:
                mesaj = f"🔔 HATIRLATMA ({kalan_gun} gün kaldı): '{is_tanimi}' görevinin son teslim tarihi yaklaşıyor."
                if not sorumlu:
                    print_report("UYARI", f"'{is_tanimi}' görevine sorumlu atanmamış, hatırlatma mesajı gönderilemiyor.")
                    continue
                sorumlu_tel = personel_telefonlari.get(sorumlu)
                if not sorumlu_tel:
                    print_report("UYARI", f"'{sorumlu}' isimli personelin telefonu 'Personel' sayfasında bulunamadı. Mesaj gönderilemiyor.")
                    continue
                hedef_tel = sorumlu_tel
            
            if mesaj and hedef_tel:
                uyari_gonderilecek_is_sayisi += 1
                print_report("BİLGİ", f"Mesaj hazırlanıyor -> Hedef: {hedef_tel}, İçerik: {mesaj}")
                send_whatsapp(hedef_tel, mesaj, secrets)

        except (ValueError, TypeError): continue
    
    if uyari_gonderilecek_is_sayisi == 0:
        print_report("BİLGİ", "Uyarı gönderilecek herhangi bir görev bulunamadı.")
    
    print_report("OK", "Uyarı sistemi kontrolü tamamlandı.")
    print("="*40)

if __name__ == "__main__":
    run_automation()
