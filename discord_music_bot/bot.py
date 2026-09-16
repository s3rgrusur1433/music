import os
import asyncio
import tempfile
import uuid
from collections import deque
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN en el archivo .env")


intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True


# ============================================================
# YT-DLP
# ============================================================

SEARCH_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch1",
    "skip_download": True,
}


# ============================================================
# DATOS DE LAS CANCIONES
# ============================================================

@dataclass
class Track:
    title: str
    webpage_url: str
    requested_by: str


class MusicState:

    def __init__(self):
        self.queue = deque()
        self.current: Track | None = None
        self.lock = asyncio.Lock()


states: dict[int, MusicState] = {}


def get_state(guild_id: int):

    if guild_id not in states:
        states[guild_id] = MusicState()

    return states[guild_id]


# ============================================================
# BOT
# ============================================================

class MusicBot(commands.Bot):

    def __init__(self):

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        await self.tree.sync()

        print("✅ Comandos slash sincronizados.")


bot = MusicBot()


# ============================================================
# BUSCAR CANCIÓN
# ============================================================

async def extract_track(query: str, requested_by: str) -> Track:

    loop = asyncio.get_running_loop()

    def search():

        with yt_dlp.YoutubeDL(SEARCH_OPTIONS) as ydl:

            info = ydl.extract_info(
                query,
                download=False
            )

            if "entries" in info:

                entries = [
                    entry
                    for entry in info["entries"]
                    if entry
                ]

                if not entries:
                    raise RuntimeError(
                        "No encontré ninguna canción."
                    )

                info = entries[0]

            title = info.get(
                "title",
                "Canción sin título"
            )

            webpage_url = (
                info.get("webpage_url")
                or info.get("original_url")
            )

            if not webpage_url:
                raise RuntimeError(
                    "No pude obtener el enlace de la canción."
                )

            return Track(
                title=title,
                webpage_url=webpage_url,
                requested_by=requested_by
            )

    return await loop.run_in_executor(
        None,
        search
    )


# ============================================================
# DESCARGAR AUDIO TEMPORAL
# ============================================================

async def download_audio(webpage_url: str):

    loop = asyncio.get_running_loop()

    def download():

        temp_folder = tempfile.gettempdir()

        unique_name = (
            f"sergru_music_{uuid.uuid4().hex}.%(ext)s"
        )

        output_template = os.path.join(
            temp_folder,
            unique_name
        )

        download_options = {

            "format": "bestaudio/best",

            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,

            "outtmpl": output_template,

            "restrictfilenames": True,
        }

        with yt_dlp.YoutubeDL(download_options) as ydl:

            info = ydl.extract_info(
                webpage_url,
                download=True
            )

            filename = ydl.prepare_filename(info)

            return filename

    return await loop.run_in_executor(
        None,
        download
    )


# ============================================================
# CONECTAR AL CANAL DE VOZ
# ============================================================

async def ensure_voice(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        raise RuntimeError(
            "Este comando solo funciona dentro de un servidor."
        )

    member = interaction.user

    if not isinstance(
        member,
        discord.Member
    ):

        raise RuntimeError(
            "No pude detectar tu usuario."
        )

    if (
        not member.voice
        or not member.voice.channel
    ):

        raise RuntimeError(
            "Entra primero en un canal de voz."
        )

    channel = member.voice.channel

    voice_client = interaction.guild.voice_client

    if voice_client is None:

        voice_client = await channel.connect()

    elif voice_client.channel != channel:

        await voice_client.move_to(channel)

    return voice_client


# ============================================================
# REPRODUCIR SIGUIENTE
# ============================================================

async def play_next(
    guild: discord.Guild
):

    state = get_state(
        guild.id
    )

    voice_client = guild.voice_client

    if (
        voice_client is None
        or not voice_client.is_connected()
    ):

        state.current = None

        return

    async with state.lock:

        if (
            voice_client.is_playing()
            or voice_client.is_paused()
        ):

            return

        if not state.queue:

            state.current = None

            print(
                f"📭 Cola vacía en {guild.name}"
            )

            return

        track = state.queue.popleft()

        state.current = track

    audio_file = None

    try:

        print(
            f"⬇️ Descargando temporalmente: {track.title}"
        )

        audio_file = await download_audio(
            track.webpage_url
        )

        print(
            f"✅ Audio preparado: {track.title}"
        )

        source = discord.FFmpegPCMAudio(
            audio_file,
            options="-vn"
        )

        def after_play(error):

            if error:

                print(
                    f"❌ Error reproduciendo: {error}"
                )

            # Borrar archivo temporal
            if audio_file:

                try:

                    if os.path.exists(
                        audio_file
                    ):

                        os.remove(
                            audio_file
                        )

                        print(
                            "🗑️ Archivo temporal eliminado."
                        )

                except Exception as exc:

                    print(
                        f"⚠️ No se pudo borrar "
                        f"el archivo temporal: {exc}"
                    )

            # Pasar a la siguiente canción
            future = asyncio.run_coroutine_threadsafe(
                play_next(guild),
                bot.loop
            )

            try:

                future.result()

            except Exception as exc:

                print(
                    f"❌ Error pasando a "
                    f"la siguiente canción: {exc}"
                )

        voice_client.play(
            source,
            after=after_play
        )

        print(
            f"▶️ Reproduciendo en "
            f"{guild.name}: "
            f"{track.title}"
        )

    except Exception as exc:

        print(
            f"❌ No se pudo reproducir "
            f"{track.title}: {exc}"
        )

        if audio_file:

            try:

                if os.path.exists(audio_file):

                    os.remove(audio_file)

            except Exception:

                pass

        state.current = None

        await play_next(guild)


# ============================================================
# BOT CONECTADO
# ============================================================

@bot.event
async def on_ready():

    print(
        f"🎵 Bot conectado como "
        f"{bot.user} "
        f"({bot.user.id})"
    )


# ============================================================
# /PLAY
# ============================================================

@bot.tree.command(
    name="play",
    description="Busca y reproduce una canción."
)
@app_commands.describe(
    busqueda="Nombre de la canción o enlace"
)
async def play(
    interaction: discord.Interaction,
    busqueda: str
):

    await interaction.response.defer()

    try:

        voice_client = await ensure_voice(
            interaction
        )

        track = await extract_track(
            busqueda,
            interaction.user.display_name
        )

        state = get_state(
            interaction.guild_id
        )

        state.queue.append(
            track
        )

        await interaction.followup.send(
            f"🎶 **{track.title}** "
            f"añadida a la cola.\n"
            f"👤 Pedido por "
            f"**{track.requested_by}**"
        )

        if (
            not voice_client.is_playing()
            and not voice_client.is_paused()
        ):

            await play_next(
                interaction.guild
            )

    except Exception as exc:

        await interaction.followup.send(
            f"❌ {exc}",
            ephemeral=True
        )


# ============================================================
# /PAUSE
# ============================================================

@bot.tree.command(
    name="pause",
    description="Pausa la música."
)
async def pause(
    interaction: discord.Interaction
):

    voice_client = (
        interaction.guild.voice_client
        if interaction.guild
        else None
    )

    if (
        voice_client
        and voice_client.is_playing()
    ):

        voice_client.pause()

        await interaction.response.send_message(
            "⏸️ Música pausada."
        )

    else:

        await interaction.response.send_message(
            "❌ No hay música reproduciéndose.",
            ephemeral=True
        )


# ============================================================
# /RESUME
# ============================================================

@bot.tree.command(
    name="resume",
    description="Continúa la música."
)
async def resume(
    interaction: discord.Interaction
):

    voice_client = (
        interaction.guild.voice_client
        if interaction.guild
        else None
    )

    if (
        voice_client
        and voice_client.is_paused()
    ):

        voice_client.resume()

        await interaction.response.send_message(
            "▶️ Música reanudada."
        )

    else:

        await interaction.response.send_message(
            "❌ No hay ninguna canción pausada.",
            ephemeral=True
        )


# ============================================================
# /SKIP
# ============================================================

@bot.tree.command(
    name="skip",
    description="Salta la canción actual."
)
async def skip(
    interaction: discord.Interaction
):

    voice_client = (
        interaction.guild.voice_client
        if interaction.guild
        else None
    )

    if voice_client and (
        voice_client.is_playing()
        or voice_client.is_paused()
    ):

        voice_client.stop()

        await interaction.response.send_message(
            "⏭️ Canción saltada."
        )

    else:

        await interaction.response.send_message(
            "❌ No hay ninguna canción para saltar.",
            ephemeral=True
        )


# ============================================================
# /STOP
# ============================================================

@bot.tree.command(
    name="stop",
    description="Para la música y vacía la cola."
)
async def stop(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Solo funciona dentro de servidores.",
            ephemeral=True
        )

        return

    state = get_state(
        interaction.guild.id
    )

    state.queue.clear()

    state.current = None

    voice_client = (
        interaction.guild.voice_client
    )

    if voice_client and (
        voice_client.is_playing()
        or voice_client.is_paused()
    ):

        voice_client.stop()

    await interaction.response.send_message(
        "⏹️ Música detenida y cola vaciada."
    )


# ============================================================
# /QUEUE
# ============================================================

@bot.tree.command(
    name="queue",
    description="Muestra la cola de canciones."
)
async def queue(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Solo funciona dentro de servidores.",
            ephemeral=True
        )

        return

    state = get_state(
        interaction.guild.id
    )

    lines = []

    if state.current:

        lines.append(
            f"▶️ **Ahora suena:**\n"
            f"{state.current.title}"
        )

    if state.queue:

        lines.append(
            "\n🎵 **Próximas canciones:**"
        )

        for index, track in enumerate(
            list(state.queue)[:10],
            start=1
        ):

            lines.append(
                f"{index}. {track.title} "
                f"— {track.requested_by}"
            )

        if len(state.queue) > 10:

            lines.append(
                f"\n...y "
                f"{len(state.queue) - 10} más."
            )

    if not lines:

        lines.append(
            "📭 La cola está vacía."
        )

    await interaction.response.send_message(
        "\n".join(lines)
    )


# ============================================================
# /NOWPLAYING
# ============================================================

@bot.tree.command(
    name="nowplaying",
    description="Muestra la canción actual."
)
async def nowplaying(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        return

    state = get_state(
        interaction.guild.id
    )

    if not state.current:

        await interaction.response.send_message(
            "❌ No hay ninguna canción reproduciéndose.",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        f"🎧 **Ahora está sonando:**\n"
        f"**{state.current.title}**\n"
        f"👤 Pedido por "
        f"**{state.current.requested_by}**"
    )


# ============================================================
# /LEAVE
# ============================================================

@bot.tree.command(
    name="leave",
    description="Desconecta el bot del canal de voz."
)
async def leave(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        return

    state = get_state(
        interaction.guild.id
    )

    state.queue.clear()

    state.current = None

    voice_client = (
        interaction.guild.voice_client
    )

    if voice_client:

        await voice_client.disconnect()

        await interaction.response.send_message(
            "👋 Me he desconectado del canal."
        )

    else:

        await interaction.response.send_message(
            "❌ No estoy conectado "
            "a ningún canal.",
            ephemeral=True
        )


# ============================================================
# ARRANCAR BOT
# ============================================================

bot.run(TOKEN)