# SignalConvert

TradingView webhook'larını **güzel Telegram kartlarına** çeviren küçük bir köprü.

- **Çoklu bot**: Her Telegram botu (farklı token + farklı kanal) için ayrı webhook URL
- **Pillow kart üretici**: YENİ SİNYAL / HEDEF OK / STOP OLDU / TRAILING / PUSU şablonları
- **Web UI dashboard**: Bot oluşturma, webhook URL kopyalama, mesaj geçmişi takibi, kart önizleme
- **Docker-ready**: Coolify veya başka bir host'a tek tıklık deploy
- **SQLite**: Konfigürasyon ve geçmiş için tek dosya DB (volume'a bağlı)

## Mimari

```
TradingView Alert (JSON)
        │
        ▼ HTTP POST
/webhook/{slug}?secret=...     ◄── her bot için benzersiz URL
        │
        ▼
SignalConvert (FastAPI)
   ├─ JSON parse (payload.py)
   ├─ Pillow kart üret (card_renderer.py)
   └─ Telegram sendPhoto (telegram.py)
        │
        ▼
Telegram kanalı/grubu
```

## Yerelde Çalıştırma

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt

copy .env.example .env
# .env'i düzenle: ADMIN_PASSWORD, SECRET_KEY, PUBLIC_BASE_URL

uvicorn app.main:app --reload
```

Tarayıcı: <http://localhost:5000> → `/login` → parolanı gir.

Port 5000 meşgulse: `uvicorn app.main:app --reload --port 5001`

## Docker ile Çalıştırma

```bash
docker compose up -d --build
```

Log: `docker compose logs -f`

## Coolify'a Deploy

1. **GitHub'a push** (aşağıya bak).
2. Coolify Dashboard → **+ New Resource → Application**.
3. **Public Repository** seç → `https://github.com/coinfxpro/signalconvert`.
4. Build Pack: **Dockerfile**.
5. **Environment Variables**:
   - `ADMIN_PASSWORD` → güçlü bir parola
   - `SECRET_KEY` → rastgele uzun string (örn. `openssl rand -hex 32`)
   - `PUBLIC_BASE_URL` → Coolify'ın sana verdiği domain, örn. `https://signalconvert.senin-domain.com`
6. **Persistent Storage**: `/app/data` yolunu bir volume'a bağla (aksi halde botlar restart'ta silinir).
7. **Port**: `5000`.
8. Deploy → Coolify otomatik SSL bağlar.

## GitHub'a Push (İlk Sefer)

```bash
cd C:\Users\HakanG\Desktop\SignalConvert
git init
git add .
git commit -m "initial commit: SignalConvert v0.1"
git branch -M main
git remote add origin https://github.com/coinfxpro/signalconvert.git
git push -u origin main
```

> Not: `data/`, `.env` ve `*.db` zaten `.gitignore`'da.

## Bot Kurulumu

1. Telegram'da [@BotFather](https://t.me/botfather) → `/newbot` → token al.
2. Botu hedef kanalına/grubuna **yönetici olarak ekle**.
3. Chat ID'yi bul (kanal için `@kanal_adi`, grup için `-100…` ID).
4. SignalConvert dashboard → **+ Yeni Bot** → token + chat_id gir → kaydet.
5. Bot detay sayfasındaki **Webhook URL**'i kopyala.
6. **Test Mesajı Gönder** butonu ile doğrula.

## TradingView Alert Kurulumu

1. Göstergeyi grafiğe ekle (`DipAlert_v2.pine` yüklü olsun).
2. Sağ panelde **Alert oluştur**.
3. **Condition**: göstergen + `Any alert() function call`.
4. **Webhook URL**: SignalConvert'teki bot webhook URL'i.
5. **Message**: `{{message}}` (Pine `alert()` gönderdiği JSON'u buraya koyar)
6. Kaydet.

Alert tetiklendiğinde TradingView → SignalConvert webhook → Pillow kart → Telegram kanalı akışı işler.

## Yeni Kart Tipi Ekleme

`app/card_renderer.py` içindeki `THEMES` sözlüğüne ekle, `EVENT_TO_THEME` eşlemesine yeni event'i yaz. Pine script tarafında da aynı `event` kelimesini JSON'a yaz.

## Dizin Yapısı

```
SignalConvert/
├── app/
│   ├── main.py              # FastAPI uygulaması
│   ├── config.py            # env yükleme
│   ├── db.py                # SQLite + SQLModel
│   ├── models.py            # Bot, Message tabloları
│   ├── auth.py              # Cookie-based admin auth
│   ├── telegram.py          # Telegram API istemcisi
│   ├── card_renderer.py     # Pillow kart üretici
│   ├── payload.py           # TV JSON → CardData parser
│   ├── routes/
│   │   ├── webhook.py       # POST /webhook/{slug}
│   │   └── dashboard.py     # UI + bot CRUD
│   ├── templates/           # Jinja2 + Tailwind CDN
│   └── static/              # (boş — CDN kullanıyoruz)
├── data/                    # runtime: signalconvert.db, images/ (git ignore)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── DipAlert.pine            # Orijinal strateji
├── DipAlert_v2.pine         # JSON webhook uyumlu bölüm
└── README.md
```

## Güvenlik Notları

- `ADMIN_PASSWORD`'ü mutlaka değiştir.
- Webhook URL `secret` query parametresi içerir — URL gizli tutulmalı.
- Coolify'ın verdiği HTTPS domain üzerinden yayınla; TradingView sadece HTTPS webhook destekler.
- Bot token'ları DB'de plaintext — DB volume'una erişimi kısıtla.

## Yol Haritası

- [ ] Bot başına kart şablonu seçimi (ileride birden fazla tema)
- [ ] Mesaj tekrar deneme (retry) kuyruğu
- [ ] Telegram'a inline buton (Tradingview'e git) ekleme
- [ ] İstatistik grafikleri (Chart.js)
