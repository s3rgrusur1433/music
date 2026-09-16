# Bot de música para Discord

Bot de música en Python con comandos slash:

- `/play <nombre o URL>`
- `/pause`
- `/resume`
- `/skip`
- `/stop`
- `/queue`
- `/leave`

## 1. Requisitos

- Python 3.11 o superior recomendado
- FFmpeg instalado y disponible en el PATH
- Una aplicación/bot creada en Discord Developer Portal

## 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

## 3. Instalar FFmpeg

### Windows
Instala FFmpeg y asegúrate de que el comando siguiente funcione:

```bash
ffmpeg -version
```

También puedes instalarlo con winget si tienes un paquete disponible en tu sistema.

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install ffmpeg -y
```

## 4. Configurar el token

Copia `.env.example` como `.env`:

```bash
copy .env.example .env
```

En Linux:

```bash
cp .env.example .env
```

Edita `.env`:

```env
DISCORD_TOKEN=TU_TOKEN
```

Nunca publiques ese token.

## 5. Crear e invitar el bot

En Discord Developer Portal:

1. Crea una aplicación.
2. Abre la sección **Bot** y crea el bot.
3. Copia el token y colócalo en `.env`.
4. En **OAuth2 > URL Generator**, selecciona:
   - `bot`
   - `applications.commands`
5. Permisos recomendados:
   - View Channels
   - Send Messages
   - Connect
   - Speak
6. Abre la URL generada e invita el bot a tu servidor.

No hace falta activar Message Content Intent porque este proyecto usa comandos slash.

## 6. Ejecutarlo

```bash
python bot.py
```

Cuando aparezca:

```text
✅ Comandos slash sincronizados.
🎵 Bot conectado como ...
```

entra en un canal de voz y prueba:

```text
/play Myke Towers LALA
```

o pega una URL compatible con yt-dlp.

## Notas

- La cola se mantiene en memoria. Si reinicias el bot, se borra.
- El stream se resuelve al empezar cada canción para reducir problemas con URLs temporales.
- Usa el bot únicamente con fuentes y contenido que tengas derecho a reproducir y respetando las condiciones de los servicios de origen.
