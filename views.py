import discord
import asyncio
import logging
from discord.ext import commands
from discord.ui import Button, View, Select
from config import created_channels, announcement_channel_id

class KickMemberView(View):
    def __init__(self, bot, channel_id, members, leader_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.members = members
        self.leader_id = leader_id
        self.add_select_options()

    def add_select_options(self):
        self.clear_items()
        options = [
            discord.SelectOption(label=member.name, value=str(member.id)) for member in self.members if member.id != self.leader_id
        ]
        if options:
            select = Select(placeholder='Выберите пользователя', min_values=1, max_values=1, options=options)
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_user_id = int(self.children[0].values[0])
        member = interaction.guild.get_member(selected_user_id)
        if member:
            try:
                await member.move_to(None)
                await interaction.response.send_message(f'{member.name} был исключен из канала.', ephemeral=True)
                self.members = created_channels[self.channel_id]['channel'].members
                self.add_select_options()
                await update_channel_panel(self.bot, self.channel_id, self.leader_id)
            except discord.DiscordException as e:
                logging.error(f"Error kicking member: {e}")
                await interaction.response.send_message('Не удалось исключить пользователя.', ephemeral=True)
        else:
            await interaction.response.send_message('Пользователь не найден.', ephemeral=True)

class ChannelView(View):
    def __init__(self, bot, channel_id, leader_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.leader_id = leader_id
        self.add_control_buttons()

    def add_control_buttons(self):
        self.add_item(Button(label="Переименовать", emoji="📝", style=discord.ButtonStyle.primary, custom_id=f"rename_{self.channel_id}", row=1))
        self.add_item(Button(label="Выгнать", emoji="✖️", style=discord.ButtonStyle.danger, custom_id=f"kick_{self.channel_id}", row=1))
        self.children[-2].callback = self.rename_button
        self.children[-1].callback = self.kick_button

    def is_leader(self, user_id: int) -> bool:
        return self.leader_id == user_id

    async def rename_button(self, interaction: discord.Interaction):
        if self.is_leader(interaction.user.id):
            prompt_message = await interaction.response.send_message("Введите новое имя канала:", ephemeral=True)

            def check(msg):
                return msg.author == interaction.user and msg.channel == interaction.channel

            try:
                msg = await self.bot.wait_for('message', check=check, timeout=60)
                new_name = msg.content
                channel = created_channels[self.channel_id]['channel']
                await channel.edit(name=new_name)
                await msg.delete()
                await update_channel_panel(self.bot, self.channel_id, self.leader_id)
                if prompt_message:
                    await prompt_message.delete()
                await interaction.followup.send(f'Канал переименован в {new_name}', ephemeral=True)
            except asyncio.TimeoutError:
                timeout_message = await interaction.followup.send('Время ожидания истекло.', ephemeral=True)
                if prompt_message:
                    await prompt_message.delete()
                await asyncio.sleep(5)
                if timeout_message:
                    await timeout_message.delete()
            except discord.DiscordException as e:
                error_message = await interaction.followup.send('Не удалось переименовать канал.', ephemeral=True)
                logging.error(f"Error renaming channel: {e}")
                if prompt_message:
                    await prompt_message.delete()
                await asyncio.sleep(5)
                if error_message:
                    await error_message.delete()
        else:
            error_message = await interaction.response.send_message('У вас нет прав на переименование этого канала.', ephemeral=True)
            await asyncio.sleep(5)
            if error_message:
                await error_message.delete()

    async def kick_button(self, interaction: discord.Interaction):
        if self.is_leader(interaction.user.id):
            members = created_channels[self.channel_id]['channel'].members
            if len(members) == 1:
                error_message = await interaction.response.send_message('В канале нет других участников для исключения.', ephemeral=True)
                await asyncio.sleep(5)
                if error_message:
                    await error_message.delete()
                return
            kick_view = KickMemberView(self.bot, self.channel_id, members, self.leader_id)
            await interaction.response.send_message("Выберите пользователя для исключения:", view=kick_view, ephemeral=True)
        else:
            error_message = await interaction.response.send_message('У вас нет прав на исключение участников из этого канала.', ephemeral=True)
            await asyncio.sleep(5)
            if error_message:
                await error_message.delete()

async def update_channel_panel(bot: commands.Bot, channel_id: int, leader_id: int):
    logging.info(f"Обновление панели управления для канала {channel_id}")
    if channel_id not in created_channels:
        logging.warning(f"Channel ID {channel_id} not found in created_channels")
        return

    channel_info = created_channels[channel_id]
    channel = channel_info['channel']
    if not channel.members:
        logging.info(f"No members in channel {channel_id}, skipping panel update.")
        return

    announcement_channel = bot.get_channel(announcement_channel_id)
    if not announcement_channel:
        logging.error(f"Канал с ID {announcement_channel_id} не найден")
        return

    members_list = '\n'.join([f'{"👑" if member.id == leader_id else "👤"} {member.mention}' for member in channel.members])
    embed = discord.Embed(title="Панель управления", description=f"\nКанал: {channel.name}\n\nУчастники:\n{members_list}")

    if 'message_id' in channel_info:
        try:
            message = await announcement_channel.fetch_message(channel_info['message_id'])
            await message.edit(embed=embed, view=ChannelView(bot, channel_id, leader_id))
            logging.info(f"Панель управления для канала {channel_id} обновлена")
        except discord.NotFound:
            logging.warning(f"Панель управления для канала {channel_id} не найдена")
            new_message = await announcement_channel.send(embed=embed, view=ChannelView(bot, channel_id, leader_id))
            created_channels[channel_id]['message_id'] = new_message.id
    else:
        new_message = await announcement_channel.send(embed=embed, view=ChannelView(bot, channel_id, leader_id))
        created_channels[channel_id]['message_id'] = new_message.id
        logging.info(f"Создана новая панель управления для канала {channel_id}")
