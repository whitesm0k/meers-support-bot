import discord
from discord import app_commands
from discord.ui import Button, View
from discord.ext import commands
import logging
import json
import os
from datetime import datetime

# --- НАСТРОЙКИ (из переменных окружения) ---
# Если переменная не задана, ставим 0 (бот выдаст ошибку при старте, если ID неверны)
CONTROL_PANEL_CHANNEL_ID = int(os.getenv("CONTROL_PANEL_CHANNEL_ID", 0))
TICKET_CATEGORY_NAME = "✦ 𝗧𝗶𝗰𝗸𝗲𝘁 ✦"
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID", 0))

# Получение токена
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    try:
        with open("token.txt", "r", encoding="utf-8") as f:
            TOKEN = f.read().strip()
    except FileNotFoundError:
        raise RuntimeError("❌ Ошибка: Токен не найден! Проверьте переменные окружения BOT_TOKEN или файл token.txt")

DATA_FILE = "ticket_stats.json"
DAILY_NORM = 2
# -----------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

claimed_tickets = {}
stats_data = {
    "total_closed": 0,
    "users": {},
    "last_update": None,
    "panel_msg_id": None
}


def load_stats():
    global stats_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                stats_data = json.load(f)
            logger.info("Статистика загружена.")
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
    else:
        logger.info("Файл статистики не найден, будет создан при первом действии.")


def save_stats():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")


load_stats()


# --- КЛАВИШИ ---
class ThemeButton(Button):
    def __init__(self, theme_name):
        super().__init__(label=theme_name, style=discord.ButtonStyle.blurple, custom_id=f"theme_{theme_name.lower()}")

    async def callback(self, interaction: discord.Interaction):
        msg_id = interaction.message.id
        if not hasattr(bot, 'temp_ticket_data'):
            bot.temp_ticket_data = {}
        if msg_id not in bot.temp_ticket_data:
            bot.temp_ticket_data[msg_id] = {}

        bot.temp_ticket_data[msg_id]['theme'] = self.label

        product_view = View(timeout=120)
        product_view.add_item(ProductButton("MeersExternal"))
        product_view.add_item(ProductButton("MeersMacro"))
        product_view.add_item(ProductButton("Другое"))

        await interaction.response.edit_message(
            content=f"✅ Вы выбрали тему: **{self.label}**.\n\nТеперь выберите **Продукт**:",
            view=product_view
        )


class ProductButton(Button):
    def __init__(self, product_name):
        super().__init__(label=product_name, style=discord.ButtonStyle.green, custom_id=f"prod_{product_name.lower()}")

    async def callback(self, interaction: discord.Interaction):
        msg_id = interaction.message.id
        if not hasattr(bot, 'temp_ticket_data') or msg_id not in bot.temp_ticket_data:
            await interaction.response.send_message("Сессия истекла. Начните заново.", ephemeral=True)
            return

        bot.temp_ticket_data[msg_id]['product'] = self.label
        data = bot.temp_ticket_data[msg_id]

        final_embed = discord.Embed(
            title="Тикет готов к созданию",
            description=f"Тема: **{data['theme']}**\nПродукт: **{data['product']}**\n\nНажмите кнопку ниже, чтобы создать канал поддержки.",
            color=discord.Color.teal()
        )
        final_view = View(timeout=120)
        final_view.add_item(ConfirmCreateButton(data))

        await interaction.response.edit_message(content="", embed=final_embed, view=final_view)


class ConfirmCreateButton(Button):
    def __init__(self, data):
        super().__init__(label="✅ Создать тикет", style=discord.ButtonStyle.green, custom_id="confirm_create")
        self.data = data

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(name=TICKET_CATEGORY_NAME)

        ticket_count = sum(
            1 for ch in category.channels if isinstance(ch, discord.TextChannel) and ch.name.startswith("ticket-"))
        ticket_number = ticket_count + 1
        channel_name = f"ticket-{ticket_number}"

        # --- ДОБАВЛЕНО: Права для саппортов ---
        support_role = guild.get_role(SUPPORT_ROLE_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        # -------------------------------------

        ticket_channel = await category.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            topic=f"Тикет: {self.data['theme']} | {self.data['product']}",
            reason=f"Тикет создан пользователем {user.id}"
        )

        role = guild.get_role(ADMIN_ROLE_ID)
        mention = role.mention if role else "@everyone"
        await ticket_channel.send(
            f"{mention} 🚨 **Новый тикет!**\nТема: {self.data['theme']}\nПродукт: {self.data['product']}\nАвтор: {user.mention}")

        welcome_embed = discord.Embed(
            title="Ваш тикет создан!",
            description=(
                f"Тема: **{self.data['theme']}**\n"
                f"Продукт: **{self.data['product']}**\n\n"
                f"👇 **Опишите проблему ниже:**\n"
                f"• Что делали перед ошибкой?\n"
                f"• Что произошло вместо ожидаемого?\n"
                f"• Приложите скриншоты или текст ошибки."
            ),
            color=discord.Color.blurple()
        )
        welcome_embed.add_field(name="Автор", value=user.mention, inline=True)
        welcome_embed.add_field(name="Статус", value="⏳ Ожидает ответа", inline=True)
        welcome_embed.set_footer(text=f"ID тикета: #{ticket_number}")

        control_view = View(timeout=None)
        control_view.add_item(ClaimTicketButton())
        control_view.add_item(CloseTicketButton())

        await ticket_channel.send(embed=welcome_embed, view=control_view)

        msg_id = interaction.message.id
        if hasattr(bot, 'temp_ticket_data') and msg_id in bot.temp_ticket_data:
            del bot.temp_ticket_data[msg_id]

        await interaction.response.send_message(
            embed=discord.Embed(title="Готово", description=f"Канал создан: <#{ticket_channel.id}>",
                                color=discord.Color.green()),
            ephemeral=True
        )


class ClaimTicketButton(Button):
    def __init__(self):
        super().__init__(label="Взять в работу", style=discord.ButtonStyle.green, custom_id="claim_ticket")

    async def callback(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        user = interaction.user

        # Проверка: только саппорт или админ может брать тикет
        if not any(role.id in [ADMIN_ROLE_ID, SUPPORT_ROLE_ID] for role in user.roles):
            await interaction.response.send_message("❌ Только саппорты и админы могут брать тикеты.", ephemeral=True)
            return

        if channel_id in claimed_tickets:
            claimer_id = claimed_tickets[channel_id]
            claimer = interaction.guild.get_member(claimer_id)
            name = claimer.display_name if claimer else "Пользователь"

            # Если тикет уже взял другой саппорт — нельзя забрать
            if claimer_id != user.id:
                await interaction.response.send_message(
                    f"❌ Этот тикет уже взят: {name}. Нельзя перехватывать чужие тикеты.", ephemeral=True)
                return
            else:
                # Если тот же самый саппорт нажал повторно — просто сообщаем
                await interaction.response.send_message("ℹ️ Этот тикет уже у вас в работе.", ephemeral=True)
                return

        claimed_tickets[channel_id] = user.id
        embed = discord.Embed(
            title="Тикет взят в работу",
            description=f"Пользователь {interaction.user.mention} взял этот тикет.",
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Вы взяли тикет в работу.", ephemeral=True)


class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="Закрыть тикет", style=discord.ButtonStyle.red, custom_id="close_ticket")

    async def callback(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        user_id = interaction.user.id

        # ТОЛЬКО АДМИНЫ МОГУТ ЗАКРЫВАТЬ
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Закрывать тикеты могут только администраторы.", ephemeral=True)
            return

        global stats_data
        stats_data["total_closed"] += 1

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        if str(user_id) not in stats_data["users"]:
            stats_data["users"][str(user_id)] = {"total": 0, "today": 0, "week": 0, "last_close_date": ""}

        user_stats = stats_data["users"][str(user_id)]

        if user_stats["last_close_date"] != date_str:
            user_stats["today"] = 0

        user_stats["today"] += 1
        user_stats["last_close_date"] = date_str
        user_stats["week"] += 1
        user_stats["total"] += 1

        stats_data["last_update"] = date_str
        save_stats()

        await update_control_panel(interaction.client)

        try:
            await interaction.channel.delete(reason=f"Закрытие тикета администратором {user_id}")
            if channel_id in claimed_tickets: del claimed_tickets[channel_id]
        except Exception as e:
            await interaction.response.send_message("Ошибка удаления канала.", ephemeral=True)


# --- ФУНКЦИЯ СТАТИСТИКИ ---
def create_stats_embed():
    total = stats_data.get("total_closed", 0)

    stats_text = "\n".join(
        f"{(bot.get_user(int(uid)).display_name if bot.get_user(int(uid)) else f'User {uid}'):<20} | Всего: {data['total']:>3} | Сегодня: {data['today']:>3}/{DAILY_NORM} | Статус: {('✅' if data['today'] >= DAILY_NORM else '❌')}"
        for uid, data in stats_data.get("users", {}).items()
    )

    desc_text = stats_text if stats_text else "Пока нет закрытых тикетов."

    embed = discord.Embed(
        title="Панель контроля тикетов",
        description=f"Всего закрыто тикетов: **{total}**\nНорма в день: **{DAILY_NORM}**\n\n"
                    f"```\n{'Пользователь':<20} | {'Всего':>5} | {'Сегодня':>7} | {'Статус'}\n{desc_text}\n```",
        color=0x2b2d42
    )
    embed.set_footer(text=f"Обновлено: {datetime.now().strftime('%H:%M:%S')}")
    return embed


async def update_control_panel(client):
    if CONTROL_PANEL_CHANNEL_ID == 0:
        return
    channel = client.get_channel(CONTROL_PANEL_CHANNEL_ID)
    if not channel:
        return

    panel_msg_id = stats_data.get("panel_msg_id")
    new_embed = create_stats_embed()

    if panel_msg_id:
        try:
            msg = await channel.fetch_message(panel_msg_id)
            await msg.edit(embed=new_embed)
            return
        except discord.NotFound:
            del stats_data["panel_msg_id"]
            save_stats()
        except Exception as e:
            logger.error(f"Ошибка редактирования: {e}")
            return

    try:
        msg = await channel.send(embed=new_embed)
        stats_data["panel_msg_id"] = msg.id
        save_stats()
    except Exception as e:
        logger.error(f"Ошибка отправки нового сообщения: {e}")


# --- ПАНЕЛЬ СОЗДАНИЯ ТИКЕТОВ ---
class StartTicketButton(Button):
    def __init__(self):
        super().__init__(label="🎫 Создать тикет", style=discord.ButtonStyle.blurple, custom_id="start_ticket")

    async def callback(self, interaction: discord.Interaction):
        view = View(timeout=120)
        view.add_item(ThemeButton("Вопрос"))
        view.add_item(ThemeButton("Проблема"))
        view.add_item(ThemeButton("Покупка"))
        await interaction.response.send_message(
            "👋 Привет! Выберите **тему** вашего обращения:",
            view=view,
            ephemeral=True
        )

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartTicketButton())

@bot.tree.command(name="setupticket", description="Установить панель создания тикетов")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛠️ Поддержка MeersProject",
        description=(
            "Нужна помощь? Создайте тикет — мы ответим быстро.\n\n"
            "**Правила подачи:**\n"
            "1. Выберите тему и продукт в меню.\n"
            "2. В канале тикета сразу укажите суть проблемы и шаги воспроизведения.\n"
            "3. Приложите скриншоты или логи ошибок — это ускорит решение в 3 раза."
        ),
        color=0x4a90e2,
        timestamp=datetime.utcnow()
    )
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    embed.set_footer(text="MeersProject Support System")

    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ Панель поддержки установлена!", ephemeral=True)


@bot.tree.command(name="setupcontrol", description="Установить панель контроля (Статистика)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_control(interaction: discord.Interaction):
    if CONTROL_PANEL_CHANNEL_ID == 0:
        await interaction.response.send_message("❌ Сначала задайте ID канала в переменных окружения!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(CONTROL_PANEL_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Канал не найден. Проверьте ID.", ephemeral=True)
        return

    msg = await channel.send(embed=create_stats_embed())
    stats_data["panel_msg_id"] = msg.id
    save_stats()
    await interaction.response.send_message(f"✅ Панель контроля установлена в канале #{channel.name}", ephemeral=True)


@bot.event
async def on_ready():
    logger.info(f"Бот запущен: {bot.user}")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Синхронизировано команд: {len(synced)}")
        if CONTROL_PANEL_CHANNEL_ID != 0:
            await update_control_panel(bot)
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}")


bot.run(TOKEN)
