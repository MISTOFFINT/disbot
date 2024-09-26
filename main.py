import os
import discord
import asyncio
import logging
from discord.ext import commands
from config import (
    source_channel_id_create_voice,
    announcement_channel_id,
    created_channels,
    voice_category_id
)
from views import ChannelView, update_channel_panel

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.voice_states = True

token = ""

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logging.info(f'Bot is ready. Logged in as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

async def handle_user_join(guild, member):
    logging.info(f"{member.name} зашел в канал для создания голосового канала")
    category = discord.utils.get(guild.categories, id=voice_category_id)
    if not category:
        logging.error(f"Категория с ID {voice_category_id} не найдена")
        return

    try:
        new_channel = await category.create_voice_channel(name=f'{member.display_name}')
        logging.info(f"Создан новый голосовой канал {new_channel.id} для пользователя {member.name}")
        await member.move_to(new_channel)
        created_channels[new_channel.id] = {'leader': member.id, 'channel': new_channel}
        logging.info(f"Перемещен пользователь {member.name} в новый канал {new_channel.id}")
        await update_channel_panel(bot, new_channel.id, member.id)
    except discord.DiscordException as e:
        logging.error(f"Ошибка создания или перемещения в новый канал: {e}")

async def handle_user_leave(channel_id, member):
    if len(member.guild.get_channel(channel_id).members) == 0:
        await delete_voice_channel(channel_id)
    else:
        await update_channel_panel(bot, channel_id, created_channels[channel_id]['leader'])

async def delete_voice_channel(channel_id):
    channel_info = created_channels.get(channel_id)
    if not channel_info:
        logging.warning(f"Channel info for {channel_id} not found")
        return

    try:
        await channel_info['channel'].delete()
        await delete_channel_panel(channel_id)
        created_channels.pop(channel_id, None)
        logging.info(f"Удален пустой канал {channel_id}")
    except discord.DiscordException as e:
        logging.error(f"Ошибка удаления канала {channel_id}: {e}")

async def delete_channel_panel(channel_id: int):
    channel_info = created_channels.get(channel_id)
    if not channel_info:
        logging.warning(f"Channel info for {channel_id} не найден")
        return

    announcement_channel = bot.get_channel(announcement_channel_id)
    if not announcement_channel:
        logging.error(f"Канал с ID {announcement_channel_id} не найден")
        return

    message_id = channel_info.get('message_id')
    if message_id:
        try:
            message = await announcement_channel.fetch_message(message_id)
            await message.delete()
            logging.info(f"Панель управления для канала {channel_id} удалена")
        except discord.NotFound:
            logging.warning(f"Панель управления для канала {channel_id} не найдена")
        except discord.DiscordException as e:
            logging.error(f"Ошибка удаления панели управления: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild

    if after.channel and after.channel.id == source_channel_id_create_voice and (before.channel is None or before.channel.id != source_channel_id_create_voice):
        await handle_user_join(guild, member)

    if before.channel and before.channel.id in created_channels and (after.channel is None or after.channel.id != before.channel.id):
        await handle_user_leave(before.channel.id, member)

    if after.channel and after.channel.id in created_channels and (before.channel is None or before.channel.id != after.channel.id):
        await update_channel_panel(bot, after.channel.id, created_channels[after.channel.id]['leader'])

async def run_bot():
    try:
        await bot.start(token)
    except discord.errors.HTTPException as e:
        logging.error(f'HTTPException occurred: {e}')
        await bot.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bot())
