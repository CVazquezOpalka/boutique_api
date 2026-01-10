## BoutiqueOS API (MVP)

### Run
uvicorn app.main:app --reload

### Seed users
- super: super@boutiqueos.com / 123456
- admin: admin@luna.com / 123456
- emp: emp@luna.com / 123456

### Frontend login
POST /auth/login-json
{ "email": "admin@luna.com", "password": "123456" }

### Flow POS
1) POST /cash/open
2) POST /sales
3) GET /stock/movements
4) GET /reports/dashboard


# BoutiqueOS – Deploy en AWS EC2 (Producción)

Este documento describe **paso a paso** cómo desplegar BoutiqueOS en una instancia EC2 usando:
- FastAPI
- PostgreSQL
- Docker + Docker Compose
- Nginx
- HTTPS (Certbot)
- Backups automáticos

El objetivo es tener un **SaaS estable, profesional y vendible**.

---

Excelente decisión 👍
Postgres + EC2 es exactamente el punto justo entre seriedad, velocidad de salida y costo controlado. Nada de juguete, nada de overengineering.

Te dejo el plan cerrado para que hoy mismo lo dejes listo para vender y mañana solo te enfoques en la UI con Loable.

🧠 Arquitectura final (la que vamos a usar)
Internet
   ↓
Route53 (dominio)
   ↓
Nginx (HTTPS – certbot)
   ↓
FastAPI (Docker / Uvicorn)
   ↓
PostgreSQL (Docker / volumen persistente)
   ↓
Backups diarios → S3


Todo en 1 EC2 (por ahora).
Simple, barato, profesional.

🧱 Stack definitivo

EC2: t3.small (mínimo) o t3.medium (ideal)

Docker + docker-compose

FastAPI (ya lo tenés)

PostgreSQL 15

SQLAlchemy

Nginx (reverse proxy)

Certbot (HTTPS)

Backups automáticos

🔧 Cambios que HAY que hacer en el backend (son pocos)
1️⃣ Cambiar SQLite → Postgres
.env
DATABASE_URL=postgresql+psycopg2://boutique:password@db:5432/boutiqueos
JWT_SECRET=super-secret-prod

Instalar driver
pip install psycopg2-binary


Tu db.py no cambia casi nada (SQLAlchemy ya está bien hecho).

2️⃣ docker-compose.yml (CLAVE)

Crealo en la raíz del proyecto:

version: "3.9"

services:
  api:
    build: .
    container_name: boutique_api
    env_file:
      - .env
    depends_on:
      - db
    restart: always
    ports:
      - "8000:8000"
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  db:
    image: postgres:15
    container_name: boutique_db
    environment:
      POSTGRES_DB: boutiqueos
      POSTGRES_USER: boutique
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always

volumes:
  postgres_data:

3️⃣ Dockerfile (backend)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

4️⃣ Nginx (reverse proxy)

Ejemplo /etc/nginx/sites-available/boutique:

server {
    server_name app.tuboutique.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}


Luego:

ln -s /etc/nginx/sites-available/boutique /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

5️⃣ HTTPS (esto VENDE confianza)
sudo certbot --nginx -d app.tuboutique.com


✔️ Automático
✔️ Gratis
✔️ Renovación sola

6️⃣ Backups (OBLIGATORIO para vender)

Script diario:

docker exec boutique_db pg_dump -U boutique boutiqueos | gzip > backup_$(date +%F).sql.gz
aws s3 cp backup_*.sql.gz s3://tu-bucket/backups/


Cron:

0 3 * * * /ruta/backup.sh

💰 Costos reales (aprox)

EC2 t3.small: ~USD 18–20 / mes

S3 backups: centavos

Dominio: ~USD 10/año

👉 Con 1 cliente anual ya lo pagás.

🟢 Estado final (para vender tranquilo)

✔️ Backend serio
✔️ Base de datos profesional
✔️ Infra simple
✔️ Backups
✔️ HTTPS
✔️ Multi-tenant
✔️ Escalable

Esto NO es un MVP de juguete.
Esto es un producto vendible.

🚀 Próximo paso inmediato

Si querés, en el próximo mensaje hago UNA de estas:

1️⃣ Te doy checklist exacto de creación de EC2 (click por click)
2️⃣ Ajustamos el backend para migrar SQLite → Postgres sin perder nada
3️⃣ Te preparo el mensaje comercial para cerrar los 5 clientes
4️⃣ Arrancamos mañana con el prompt perfecto para Loable (UI)

Decime con cuál seguimos y lo cerramos 💪

agrega en un README todo lo que vamos a hacer en el EC2

Perfecto. Acá tenés un README.md listo para pegar, pensado como guía operativa paso a paso para levantar Postgres + FastAPI en una EC2 y dejar el sistema vendible en producción.

Podés usarlo vos, dárselo a un socio, o incluso a futuro a alguien que te ayude con infra.

# BoutiqueOS – Deploy en AWS EC2 (Producción)

Este documento describe **paso a paso** cómo desplegar BoutiqueOS en una instancia EC2 usando:
- FastAPI
- PostgreSQL
- Docker + Docker Compose
- Nginx
- HTTPS (Certbot)
- Backups automáticos

El objetivo es tener un **SaaS estable, profesional y vendible**.

---

## 1. Infraestructura AWS

### 1.1 Crear instancia EC2
- Tipo recomendado: `t3.small` (mínimo) / `t3.medium` (ideal)
- SO: **Ubuntu 22.04 LTS**
- Storage: mínimo **30 GB**
- Security Group:
  - Puerto 22 (SSH)
  - Puerto 80 (HTTP)
  - Puerto 443 (HTTPS)

### 1.2 Acceder por SSH
```bash
ssh -i key.pem ubuntu@IP_PUBLICA

2. Instalación base del servidor
2.1 Actualizar sistema
sudo apt update && sudo apt upgrade -y

2.2 Instalar Docker
sudo apt install docker.io -y
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu


Cerrar sesión y volver a entrar para que tome el grupo.

2.3 Instalar Docker Compose
sudo apt install docker-compose -y

3. Estructura del proyecto
/opt/boutiqueos/
 ├─ app/
 ├─ Dockerfile
 ├─ docker-compose.yml
 ├─ requirements.txt
 ├─ .env


Ubicación recomendada:

sudo mkdir -p /opt/boutiqueos
sudo chown -R ubuntu:ubuntu /opt/boutiqueos
cd /opt/boutiqueos

4. Variables de entorno
.env
DATABASE_URL=postgresql+psycopg2://boutique:password@db:5432/boutiqueos
JWT_SECRET=CAMBIAR_EN_PROD

5. Dockerización
5.1 Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

5.2 docker-compose.yml
version: "3.9"

services:
  api:
    build: .
    container_name: boutique_api
    env_file:
      - .env
    depends_on:
      - db
    restart: always
    ports:
      - "8000:8000"
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  db:
    image: postgres:15
    container_name: boutique_db
    environment:
      POSTGRES_DB: boutiqueos
      POSTGRES_USER: boutique
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always

volumes:
  postgres_data:

6. Levantar el backend
docker-compose up -d --build


Verificar:

docker ps


API disponible en:

http://IP_PUBLICA:8000/docs

7. Nginx (Reverse Proxy)
7.1 Instalar Nginx
sudo apt install nginx -y

7.2 Configuración
sudo nano /etc/nginx/sites-available/boutique

server {
    server_name app.tuboutique.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}


Activar:

sudo ln -s /etc/nginx/sites-available/boutique /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

8. HTTPS (Certbot)
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d app.tuboutique.com


✔️ HTTPS automático
✔️ Renovación automática

9. Backups (OBLIGATORIO)
9.1 Script de backup
nano /opt/boutiqueos/backup.sh

#!/bin/bash
docker exec boutique_db pg_dump -U boutique boutiqueos | gzip > /tmp/boutiqueos_$(date +%F).sql.gz
aws s3 cp /tmp/boutiqueos_*.sql.gz s3://BUCKET/backups/

chmod +x backup.sh

9.2 Cron diario
crontab -e

0 3 * * * /opt/boutiqueos/backup.sh

10. Usuarios seed (iniciales)

Superadmin:

super@boutiqueos.com / 123456

Admin:

admin@luna.com / 123456

Employee:

emp@luna.com / 123456

11. Flujo de operación

Crear tenant (superadmin)

Crear admin

Crear empleados

Cargar productos

Ajustar stock

Abrir caja

Registrar ventas

Cerrar caja

Ver reportes

12. Escalado futuro (no ahora)

Migrar DB a RDS

Separar frontend

CI/CD

Multi-EC2

Estado final

✔️ Infra profesional
✔️ DB real (Postgres)
✔️ HTTPS
✔️ Backups
✔️ Listo para vender


---

## 🟢 Con esto estás cubierto
Este README **ya te respalda** si:
- mañana subís a EC2
- pasado mañana entra el primer cliente
- dentro de 6 meses lo retoma otra persona

Si querés, próximo paso puedo:
- adaptarlo a **Lightsail**
- agregar **diagrama de arquitectura**
- o armar el **mensaje comercial + pricing** para cerrar los 5 clientes

Decime cómo seguimos 💪