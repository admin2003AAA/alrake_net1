# 🛡️ Network Monitor — نظام مراقبة الشبكات مع Cisco Bootstrap Discovery وتنبيهات Telegram

نظام مراقبة شبكات احترافي ومفتوح المصدر، يبدأ من جهاز Cisco رئيسي (Switch/Router) ويبني خريطة topology تلقائيًا، مع إرسال تنبيهات فورية عبر Telegram عند اكتشاف أي مشكلة.

---

## 📋 الميزات

| الميزة | الوصف |
|--------|-------|
| **Cisco Bootstrap** | يبدأ من IP + username + password لجهاز Cisco ويكتشف بقية الشبكة |
| **Auto Discovery** | يجمع جيران CDP/LLDP وجداول ARP/MAC تلقائيًا |
| **دعم متعدد الأجهزة** | Cisco كامل، MikroTik وUBNT مُهيأة للتوسعة |
| **Telegram Bot** | تنبيهات فورية مع اسم الجهاز وIP والمنفذ والوصف والسبب المرجح |
| **Deduplication** | لا تكرار للتنبيهات (debounce + dedup key) |
| **Recovery Alerts** | إشعار عند رجوع الحالة للطبيعي |
| **REST API** | FastAPI مع docs تلقائية |
| **قاعدة بيانات** | PostgreSQL + SQLAlchemy 2 + Alembic |
| **جدولة مهام** | APScheduler لـ polling ودورات الاكتشاف |
| **Docker** | Dockerfile + docker-compose.yml جاهز |
| **تشغيل محلي** | `python run.py` مباشرة على Kali/VPS |

---

## 🏗️ بنية المشروع

```
alrake_net1/
├── app/
│   ├── main.py              # FastAPI app + startup/shutdown
│   ├── config.py            # إعدادات pydantic-settings
│   ├── api/
│   │   ├── router.py        # تجميع كل endpoints
│   │   ├── health.py        # /api/health, /api/status
│   │   ├── devices.py       # /api/devices
│   │   ├── alerts.py        # /api/alerts
│   │   └── discovery.py     # /api/discovery/run
│   ├── bot/
│   │   ├── bot.py           # aiogram Bot instance + sender
│   │   ├── handlers.py      # أوامر Telegram (/start, /devices, ...)
│   │   └── formatters.py    # تنسيق رسائل التنبيهات
│   ├── db/
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   └── session.py       # async engine + session
│   ├── drivers/
│   │   ├── base.py          # Abstract base class للـ drivers
│   │   ├── cisco/ssh.py     # Cisco SSH driver (Netmiko)
│   │   ├── mikrotik/api.py  # MikroTik API driver (stub)
│   │   └── ubnt/snmp.py     # Ubiquiti SNMP driver (stub)
│   ├── services/
│   │   └── discovery.py     # Topology discovery من Cisco bootstrap
│   └── monitoring/
│       ├── alert_manager.py # إنشاء/إلغاء تنبيهات مع debounce
│       ├── poller.py        # polling دوري للأجهزة
│       ├── scheduler.py     # APScheduler jobs
│       └── thresholds.py   # دوال تقييم العتبات
├── tests/
│   ├── test_health.py       # اختبارات API health
│   ├── test_thresholds.py   # اختبارات threshold logic
│   ├── test_formatters.py   # اختبارات تنسيق الرسائل
│   └── test_cisco_parser.py # اختبارات parser الـ Cisco
├── alembic/
│   ├── env.py
│   └── versions/
├── Dockerfile
├── docker-compose.yml
├── run.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚙️ المتطلبات

### للتشغيل المحلي (Kali Linux / VPS)
- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- `pip install -r requirements.txt`

### للتشغيل عبر Docker
- Docker 24+
- Docker Compose v2+

---

## 🔧 إعداد `.env`

```bash
cp .env.example .env
nano .env
```

### المتغيرات الإلزامية:

```env
# Telegram Bot Token من @BotFather
TELEGRAM_BOT_TOKEN=123456789:AAAA...

# Chat ID للمدير (أو Group ID)
TELEGRAM_ADMIN_CHAT_ID=987654321

# Cisco Bootstrap Device (السويتش/الراوتر الرئيسي)
CISCO_BOOTSTRAP_HOST=192.168.1.1
CISCO_BOOTSTRAP_USERNAME=admin
CISCO_BOOTSTRAP_PASSWORD=my_password
CISCO_BOOTSTRAP_ENABLE_PASSWORD=enable_pass

# قاعدة البيانات
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/network_monitor
DATABASE_SYNC_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/network_monitor

# Redis
REDIS_URL=redis://localhost:6379/0
```

### الحصول على `TELEGRAM_ADMIN_CHAT_ID`:
1. افتح المحادثة مع بوتك على Telegram.
2. أرسل أي رسالة.
3. افتح: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. ابحث عن `chat.id`.

---

## 🚀 تشغيل محلي على Kali Linux / VPS

### 1. تثبيت المتطلبات

```bash
# PostgreSQL
sudo apt install postgresql postgresql-contrib -y
sudo systemctl start postgresql
sudo -u postgres createdb network_monitor

# Redis
sudo apt install redis-server -y
sudo systemctl start redis

# Python dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. إعداد `.env`

```bash
cp .env.example .env
# عدّل .env وأضف قيمك
nano .env
```

### 3. ترحيل قاعدة البيانات (Alembic)

```bash
# إنشاء migration جديدة
alembic revision --autogenerate -m "initial"

# تطبيق الـ migrations
alembic upgrade head
```

### 4. تشغيل النظام

```bash
python run.py
```

سيعمل النظام على:
- **API**: `http://localhost:8000`
- **Docs**: `http://localhost:8000/docs`
- **Health**: `http://localhost:8000/api/health`

---

## 🐳 تشغيل عبر Docker Compose

```bash
# 1. إعداد .env
cp .env.example .env
nano .env

# 2. بناء وتشغيل
docker compose up -d --build

# 3. مراقبة السجلات
docker compose logs -f app

# 4. إيقاف
docker compose down
```

> ملاحظة: Docker Compose يدير PostgreSQL وRedis تلقائيًا.
> لا تحتاج لتثبيت أي شيء آخر.

---

## 🗄️ ترحيل قاعدة البيانات (Alembic)

```bash
# إنشاء migration من النماذج الحالية
alembic revision --autogenerate -m "initial schema"

# تطبيق migrations
alembic upgrade head

# التراجع خطوة
alembic downgrade -1

# عرض السجل
alembic history
```

---

## 📡 API Endpoints

| Method | Endpoint | الوصف |
|--------|----------|-------|
| GET | `/api/health` | فحص صحة التطبيق |
| GET | `/api/status` | حالة موسعة مع DB |
| GET | `/api/devices` | قائمة الأجهزة |
| GET | `/api/devices/{id}` | تفاصيل جهاز |
| GET | `/api/alerts` | قائمة التنبيهات |
| GET | `/api/alerts?active_only=true` | التنبيهات النشطة |
| GET | `/api/alerts/{id}` | تفاصيل تنبيه |
| POST | `/api/discovery/run` | بدء اكتشاف يدوي |

---

## 🤖 أوامر Telegram Bot

| الأمر | الوصف |
|-------|-------|
| `/start` | ترحيب وقائمة الأوامر |
| `/help` | قائمة الأوامر |
| `/status` | إحصائيات النظام |
| `/devices` | قائمة الأجهزة |
| `/alerts` | آخر التنبيهات النشطة |
| `/discover` | بدء اكتشاف يدوي |

---

## 📊 نماذج البيانات

| Model | الوصف |
|-------|-------|
| `Device` | جهاز شبكي (Cisco/MikroTik/UBNT) |
| `Interface` | منفذ/واجهة على جهاز |
| `TopologyLink` | رابط بين جهازين (CDP/LLDP) |
| `Alert` | تنبيه مع dedup + debounce |
| `Metric` | قياس نقطي (CCQ, Signal, ...) |

---

## 🔌 إضافة Driver جديد

1. أنشئ مجلدًا في `app/drivers/` (مثلاً `cambium/`)
2. أنشئ class يرث من `app.drivers.base.BaseDriver`
3. نفّذ `connect()`, `disconnect()`, `collect_device_info()`, `get_interfaces()`, `get_neighbors()`
4. أضفه لدالة `poll_device()` في `app/monitoring/poller.py`

مثال:
```python
from app.drivers.base import BaseDriver, DeviceInfo, InterfaceInfo, NeighborInfo

class CambiumDriver(BaseDriver):
    async def connect(self): ...
    async def disconnect(self): ...
    async def collect_device_info(self) -> DeviceInfo: ...
    async def get_interfaces(self) -> list[InterfaceInfo]: ...
    async def get_neighbors(self) -> list[NeighborInfo]: ...
```

---

## 🔐 ملاحظات الأمان

1. **لا تضع الأسرار في الكود** — استخدم `.env` دائمًا.
2. **أضف `.env` لـ `.gitignore`** — موجود بالفعل.
3. **قيّد SSH على الـ Cisco** إلى IP السيرفر فقط (`access-list`).
4. **استخدم حساب `read-only`** للمراقبة (privilege level 1 أو 7 لـ show commands).
5. **فعّل HTTPS** على API إذا كانت متاحة للإنترنت (nginx + certbot).
6. **حدّث** `SECRET_KEY` في `.env` لقيمة عشوائية قوية.
7. **لا تشارك** `.env` أو PostgreSQL password في repositories.

---

## 🧪 تشغيل الاختبارات

```bash
# تثبيت dependencies
pip install -r requirements.txt

# تشغيل كل الاختبارات
pytest

# مع coverage
pytest --cov=app

# اختبار ملف معين
pytest tests/test_thresholds.py -v
```

---

## 🗺️ خارطة الطريق

- [x] Cisco SSH discovery (CDP/LLDP/ARP/MAC)
- [x] PostgreSQL + Alembic models
- [x] Telegram bot + professional Arabic alerts
- [x] Alert deduplication + debounce + recovery
- [x] APScheduler polling
- [x] FastAPI REST API
- [x] Docker Compose deployment
- [ ] MikroTik RouterOS API driver (v2)
- [ ] Ubiquiti SNMP driver — Signal/CCQ/Clients (v2)
- [ ] SNMP polling for Cisco interfaces
- [ ] Grafana dashboard integration
- [ ] Web UI for topology map
- [ ] Slack / Email alerts
- [ ] Multi-tenant support

---

## 📄 الرخصة

MIT License — حر الاستخدام لأغراض شخصية وتجارية.