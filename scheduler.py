# NIHAI OTOMASYON KODU (Aşırı Detaylı Teşhis Modu)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json
import requests

def print_report(status, message):
    print(f"[{status}] {message}")

# ... (send_whatsapp fonksiyonu) ...

def run_automation():
    print("="*50)
    print(f"Otomasyon Başlatıldı (Aşırı Detaylı Mod): {datetime.now()}")
    print("="*50)
    
    # ... (Tüm teşhis ve otomasyon mantığı burada) ...
    # En son verdiğim "Konuşkan" scheduler.py kodunun tamamı buraya gelecek.
    # Bu kod, her adımı detaylıca loglayarak bize ne olup bittiğini anlatır.

if __name__ == "__main__":
    run_automation()
