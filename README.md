# daveLinK 🔗

Acortador de URLs moderno con códigos QR, estadísticas de clics y panel de administración.

## Stack

- **API y redirecciones** — Python / FastAPI
- **ORM y administración** — Django (modelos fuente de verdad + admin)
- **Frontend** — HTML + CSS + JS vanilla (servido por FastAPI)
- **Base de datos** — PostgreSQL
- **Códigos QR** — `qrcode` (Pillow)

## Requisitos

- Python 3.10+
- PostgreSQL (accesible vía `DATABASE_URL`)
- Entorno virtual (`.venv`)

## Setup rápido

```bash
# Clonar
git clone <repo-url>
cd acortador

# Entorno virtual
python -m venv .venv
source .venv/bin/activate

# Dependencias
pip install -r backend/requirements.txt

# Variables de entorno
cp backend/.env.example backend/.env
# Editar .env con la conexión a tu PostgreSQL

# Migraciones Django
cd backend/django_app
python manage.py migrate
cd ../..

# Ejecutar (FastAPI + Django admin)
./run.sh
```

## Endpoints principales

| Ruta                  | Descripción                              |
| --------------------- | ---------------------------------------- |
| `GET /`               | Frontend web                             |
| `POST /api/shorten`   | Acortar una URL                          |
| `GET /{code}`         | Redirección al destino original          |
| `GET /api/stats/{code}` | Estadísticas de clics                  |
| `GET /api/qr/{code}`  | Código QR en PNG (base64)                |
| `GET /api/health`     | Health check                             |
| `admin/`              | Panel Django (crear superusuario antes)  |

## Variables de entorno

| Variable        | Descripción                     | Ejemplo                                                  |
| --------------- | ------------------------------- | -------------------------------------------------------- |
| `DATABASE_URL`  | Conexión a PostgreSQL           | `postgresql://user:pass@host:5432/db`                    |
| `SECRET_KEY`    | Clave secreta de la app         | `cambiar-en-producción`                                  |
| `BASE_URL`      | URL base del servicio           | `http://localhost:8000`                                  |
| `ENVIRONMENT`   | `development` / `production`    | `development`                                            |
| `DEBUG`         | Modo debug                      | `True`                                                   |
| `APP_NAME`      | Nombre de la aplicación         | `daveLinK`                                               |

## Estructura

```
backend/
├── config.py              # Config centralizada
├── requirements.txt
├── .env.example
├── shared/                # Modelos SQLAlchemy compartidos
│   ├── models.py
│   └── database.py
├── django_app/            # ORM + admin (fuente de verdad)
│   └── links/
│       ├── models.py
│       ├── admin.py
│       └── migrations/
└── fastapi_app/           # API + redirecciones + frontend
    ├── main.py
    ├── routes/
    │   ├── shorten.py
    │   ├── redirect.py
    │   ├── stats.py
    │   └── qr.py
    └── services/

frontend/
├── index.html
├── css/style.css
└── js/app.js
```
