# --- BU FONKSİYONU GÜNCELLE (Eskisini sil bunu yapıştır) ---
def beyanname_analiz_et(pdf_file):
    sonuclar = []
    # Varsayılan boş veri yapısı (Hata almamak için)
    bos_df = pd.DataFrame(columns=["Mükellef", "Kredi_Karti", "Matrah", "KDV", "Ozel_Matrah", "Beyan_Edilen_Toplam", "Fark", "Durum"])
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                # 1. Mükellef Adını Bul
                isim_match = re.search(r"SOYADI \(UNVANI\)\s*[:\n]\s*(.*)", text)
                if not isim_match:
                    isim_match = re.search(r"TİCARET UNVANI\s*[:\n]\s*(.*)", text)
                
                # Eğer isim bulunamazsa bu sayfayı atla (Gereksiz sayfa olabilir)
                if not isim_match: continue

                musteri_adi = isim_match.group(1).strip().split("\n")[0]

                # 2. Verileri Çek
                kk_match = re.search(r"Kredi Kartı ile Tahsil.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                kk_tutar = text_to_float(kk_match.group(1)) if kk_match else 0.0

                matrah_match = re.search(r"TOPLAM MATRAH.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                # Alternatif matrah araması (Bazen format kayabilir)
                if not matrah_match:
                     matrah_match = re.search(r"Matrah Toplamı.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                matrah_tutar = text_to_float(matrah_match.group(1)) if matrah_match else 0.0

                kdv_match = re.search(r"TOPLAM HESAPLANAN KDV.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                kdv_tutar = text_to_float(kdv_match.group(1)) if kdv_match else 0.0

                ozel_matrah_match = re.search(r"Özel Matrah.*?(\d{1,3}(?:\.\d{3})*,\d{2})", text, re.IGNORECASE)
                ozel_matrah = text_to_float(ozel_matrah_match.group(1)) if ozel_matrah_match else 0.0

                # 3. Hesaplama
                beyan_edilen = matrah_tutar + kdv_tutar + ozel_matrah
                fark = kk_tutar - beyan_edilen
                durum = "RİSKLİ" if fark > 50 else "TEMİZ"
                
                sonuclar.append({
                    "Mükellef": musteri_adi,
                    "Kredi_Karti": kk_tutar,
                    "Matrah": matrah_tutar,
                    "KDV": kdv_tutar,
                    "Ozel_Matrah": ozel_matrah,
                    "Beyan_Edilen_Toplam": beyan_edilen,
                    "Fark": fark,
                    "Durum": durum
                })
    except Exception as e:
        st.error(f"PDF okuma hatası: {e}")
        return bos_df

    if not sonuclar:
        return bos_df
        
    return pd.DataFrame(sonuclar)


# --- KDV ANALİZ ROBOTU BÖLÜMÜNÜ DE GÜNCELLE ---
# (Kodun alt kısmındaki 'elif secim == "KDV Analiz Robotu":' bloğunu bununla değiştir)

elif secim == "KDV Analiz Robotu":
    st.title("🕵️‍♂️ KDV Analiz & İhbar Robotu")
    st.info("Toplu KDV beyannamesi PDF'ini yükleyin. Sistem Kredi Kartı vs. Matrah kontrolü yapar.")
    
    if st.session_state['tasdik_data'] is None:
        st.warning("⚠️ Personel eşleşmesi için önce 'Veri Yükle' kısmından Excel listesini yüklemeniz önerilir.")
    
    # PDF YÜKLEME
    pdf_up = st.file_uploader("Beyanname PDF'ini Yükle", type=["pdf"])
    
    if pdf_up:
        if st.button("🔍 Analizi Başlat"):
            with st.spinner("Beyannameler taranıyor..."):
                df_sonuc = beyanname_analiz_et(pdf_up)
                st.session_state['analiz_sonuclari'] = df_sonuc
    
    # SONUÇLARI GÖSTER
    if st.session_state['analiz_sonuclari'] is not None:
        df_res = st.session_state['analiz_sonuclari']
        
        # BOŞ VERİ KONTROLÜ (HATA ALMAMAK İÇİN)
        if df_res.empty:
            st.warning("PDF tarandı ancak okunabilir veri bulunamadı. Dosyanın resim (tarama) olmadığından ve metin içerdiğinden emin olun.")
        else:
            # Sadece Risklileri Filtrele Butonu
            sadece_risk = st.checkbox("Sadece Hatalı (Riskli) Olanları Göster", value=True)
            
            if sadece_risk:
                # "Durum" sütununun varlığını kontrol et
                if "Durum" in df_res.columns:
                    df_goster = df_res[df_res["Durum"] == "RİSKLİ"]
                else:
                    df_goster = df_res # Sütun yoksa hepsini göster (hata önleyici)
            else:
                df_goster = df_res
                
            c1, c2 = st.columns(2)
            c1.metric("Taranan Beyanname", len(df_res))
            # Hata almamak için sütun kontrolü
            riskli_sayisi = len(df_res[df_res["Durum"]=="RİSKLİ"]) if "Durum" in df_res.columns else 0
            c2.metric("🚨 Tespit Edilen Risk", riskli_sayisi)
            
            st.divider()
            
            # LİSTE VE AKSİYON
            if not df_goster.empty:
                for i, row in df_goster.iterrows():
                    musteri = row["Mükellef"]
                    fark = para_formatla(row["Fark"])
                    kk = para_formatla(row["Kredi_Karti"])
                    beyan = para_formatla(row["Beyan_Edilen_Toplam"])
                    
                    # Personeli Bulma Mantığı
                    personel_adi = "Yetkili"
                    
                    if st.session_state['tasdik_data'] is not None:
                        df_data = st.session_state['tasdik_data']
                        # Mükellef adını Excel'de ara
                        eslesme = df_data[df_data["Ünvan / Ad Soyad"].str.contains(str(musteri)[:10], case=False, na=False)]
                        if not eslesme.empty and "Sorumlu" in df_data.columns:
                            personel_adi = eslesme.iloc[0]["Sorumlu"]
                    
                    # KART GÖRÜNÜMÜ
                    with st.container():
                        col_detay, col_btn = st.columns([3, 1])
                        with col_detay:
                            st.markdown(f"""
                            <div class='risk-karti'>
                                <b>{musteri}</b><br>
                                Kredi Kartı: {kk} TL | Beyan (Dahil): {beyan} TL<br>
                                <b>FARK: {fark} TL (Eksik Beyan)</b>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with col_btn:
                            target_tel = st.text_input(f"Personel Tel ({i})", placeholder="53X...", key=f"tel_{i}")
                            
                            if st.button("🚨 İhbar Et", key=f"btn_{i}"):
                                if target_tel:
                                    msg = MESAJ_SABLONLARI["KDV Hata Uyarısı (Personele)"].format(
                                        personel=personel_adi,
                                        musteri=musteri,
                                        kk_tutar=kk,
                                        beyan_tutar=beyan,
                                        fark=fark
                                    )
                                    tels = numaralari_ayikla(target_tel)
                                    for t in tels:
                                        whatsapp_text_gonder(t, msg)
                                    st.toast("Personel Uyarıldı! 👮‍♂️", icon="✅")
                                else:
                                    st.error("Numara giriniz.")
            else:
                st.success("Taranan beyannamelerde riskli bir durum bulunamadı (veya filtreye takılan yok).")
