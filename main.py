import discord
from discord.ext import commands
import datetime
import random
import os
import asyncio
import hashlib
import uuid
import json
import threading
from flask import Flask, request, jsonify

# 🔧 НАСТРОЙКИ
DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1117076342551359638'))
GUILD_ID = int(os.environ.get('GUILD_ID', '1431582239551918134'))

# 🔥 URL для Render.com
def get_server_url():
    """Получаем URL Render.com"""
    render_url = os.environ.get('RENDER_URL', 'https://sigeojoiner.onrender.com')
    return render_url

AUTH_SERVER_URL = get_server_url() + "/auth"
print(f"🔐 Auth Server URL: {AUTH_SERVER_URL}")

# Веб-сервер для авторизации
web_server = Flask(__name__)

@web_server.route('/')
def home():
    return f"""
    <h1>🔒 SigeoJoiner Auth Server</h1>
    <p>Status: <span style="color: green;">✅ ONLINE</span></p>
    <p>Server: <strong>Render.com</strong></p>
    <p>Auth URL: <code>{AUTH_SERVER_URL}</code></p>
    <p>Endpoints:</p>
    <ul>
    <li><code>{AUTH_SERVER_URL}?key=KEY</code> - авторизация</li>
    <li><code>/validate</code> - проверка ключа</li>
    <li><code>/stats</code> - статистика</li>
    <li><code>/test</code> - тест</li>
    </ul>
    """

@web_server.route('/test')
def test():
    return "<h1>✅ SigeoJoiner Server Working!</h1><p>Render.com deployment successful!</p>"

# 🔐 СЕРВЕР АВТОРИЗАЦИИ
@web_server.route('/auth', methods=['POST', 'GET'])
def auth_endpoint():
    """Основная точка авторизации с автоматическим HWID"""
    
    print(f"🔐 Auth request from {request.remote_addr}")
    
    # Получаем ключ из разных источников
    key = (
        request.args.get('key') or 
        request.form.get('key') or
        (request.json.get('key') if request.json else None)
    )
    
    print(f"🔑 Key received: {key}")
    
    if not key:
        return "ERROR: No key provided", 400
    
    # Проверяем ключ в базе
    if key not in keys_db:
        print(f"❌ Invalid key: {key}")
        return "ERROR: Invalid key", 403
    
    key_data = keys_db[key]
    
    # Проверяем активацию
    if not key_data['activated']:
        return "ERROR: Key not activated", 403
    
    # Проверяем срок действия
    expires_at = datetime.datetime.fromisoformat(key_data['expires_at'])
    if datetime.datetime.now() > expires_at:
        return "ERROR: Key expired", 403
    
    # 🔥 АВТОМАТИЧЕСКАЯ ПРОВЕРКА HWID
    client_hwid = request.args.get('hwid') or request.form.get('hwid')
    
    # Если HWID не передан - значит первый запуск, генерируем его
    if not client_hwid:
        # Генерируем HWID для пользователя
        client_hwid = hashlib.md5(str(uuid.getnode()).encode()).hexdigest()[:16].upper()
        
        # Возвращаем скрипт с автоматическим определением HWID
        return f'''
-- 🔒 SigeoJoiner Auto-HWID System
getgenv().Key = "{key}"
getgenv().HWID = "{client_hwid}"

print("🆔 Auto-detected HWID:", getgenv().HWID)

-- Автоматическая отправка HWID на сервер
local function register_hwid()
    local response = request({{
        Url = "{AUTH_SERVER_URL}?key={key}&hwid={client_hwid}",
        Method = "GET"
    }})
    
    if response.Success then
        loadstring(response.Body)()
    else
        game:GetService("Players").LocalPlayer:Kick("❌ Failed to register HWID")
    end
end

register_hwid()
'''
    
    # Если HWID передан - проверяем его
    if key_data['hwid'] and key_data['hwid'] != client_hwid:
        return "ERROR: HWID mismatch - This key is bound to another device", 403
    
    # Если у ключа нет HWID - привязываем его
    if not key_data['hwid']:
        keys_db[key]['hwid'] = client_hwid
        print(f"✅ HWID bound: {client_hwid} to key {key}")
    
    # Все проверки пройдены - возвращаем ОСНОВНОЙ скрипт
    print(f"✅ Key validated: {key} for user {key_data['discord_id']}")
    
    try:
        with open('encrypted_script.lua', 'r') as f:
            encrypted_content = f.read()
        
        return f"""
-- 🔒 SigeoJoiner Loader
-- Authorized: {key_data['discord_id']}
-- Valid until: {expires_at.strftime('%Y-%m-%d %H:%M')}
-- HWID: {client_hwid}

print("✅ SigeoJoiner loaded successfully!")
print("🔑 License valid until: {expires_at.strftime('%Y-%m-%d')}")
print("🆔 HWID: {client_hwid}")

{encrypted_content}
"""
    except Exception as e:
        return f"ERROR: Failed to load script - {str(e)}"

@web_server.route('/validate', methods=['POST'])
def validate_key():
    """Дополнительная валидация"""
    data = request.json
    key = data.get('key')
    hwid = data.get('hwid')
    
    if not key or key not in keys_db:
        return jsonify({'valid': False, 'error': 'Invalid key'})
    
    key_data = keys_db[key]
    expires_at = datetime.datetime.fromisoformat(key_data['expires_at'])
    
    checks = {
        'activated': key_data['activated'],
        'hwid_match': key_data['hwid'] == hwid,
        'not_expired': datetime.datetime.now() < expires_at,
        'discord_linked': key_data['discord_id'] is not None
    }
    
    valid = all(checks.values())
    
    return jsonify({
        'valid': valid,
        'checks': checks,
        'expires': key_data['expires_at'],
        'discord_id': key_data['discord_id'],
        'days_left': (expires_at - datetime.datetime.now()).days
    })

@web_server.route('/stats')
def stats():
    """Статистика для админа"""
    active = sum(1 for data in keys_db.values() if data['activated'])
    total = len(keys_db)
    expired = sum(1 for data in keys_db.values() 
                if data['activated'] and datetime.datetime.now() > datetime.datetime.fromisoformat(data['expires_at']))
    
    return jsonify({
        'total_keys': total,
        'active_keys': active,
        'expired_keys': expired,
        'server': 'Render.com',
        'status': 'online'
    })

# Discord бот
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# База данных
keys_db = {}
user_activations = {}

# 🔧 УТИЛИТЫ
def generate_hwid():
    return hashlib.md5(str(uuid.getnode()).encode()).hexdigest()[:16].upper()

def validate_hwid(hwid):
    return len(hwid) == 16 and all(c in '0123456789ABCDEF' for c in hwid)

def generate_key():
    return f"SIEO-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

# 🔥 PERSISTENT VIEWS
class PublicControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", style=discord.ButtonStyle.green, emoji="🔑", custom_id="public_redeem_key")
    async def redeem_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in user_activations:
            await interaction.response.send_message(
                f"❌ У вас уже активирован ключ: `{user_activations[user_id]}`",
                ephemeral=True
            )
            return
        modal = KeyModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Get Script", style=discord.ButtonStyle.blurple, emoji="📜", custom_id="public_get_script")
    async def get_script(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        user_key = None
        for key, data in keys_db.items():
            if data.get('discord_id') == user_id and data['activated']:
                user_key = key
                break

        if not user_key:
            await interaction.response.send_message("❌ Нет активированных ключей! Сначала активируйте ключ.", ephemeral=True)
            return

        key_data = keys_db[user_key]
        
        # 🔥 ВЫДАЕМ СКРИПТ
        ready_script = f'getgenv().Key = "{user_key}"\nloadstring(game:HttpGet("{AUTH_SERVER_URL}", true))()'

        embed = discord.Embed(
            title="✅ Ваш скрипт готов:",
            description=f"```lua\n{ready_script}\n```",
            color=0x00ff00
        )
        embed.add_field(name="📝 Инструкция", value="1. Скопируй код выше\n2. Вставь в исполнитель\n3. HWID определится автоматически", inline=False)
        embed.add_field(name="🔑 Ваш ключ", value=f"`{user_key}`", inline=True)
        embed.add_field(name="📅 Действует до", value=key_data['expires_at'][:10], inline=True)
        embed.add_field(name="🌐 Сервер", value="Render.com (24/7)", inline=True)
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Скрипт отправлен в ЛС!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Откройте ЛС для получения скрипта!", ephemeral=True)

class AdminControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Generate Keys", style=discord.ButtonStyle.green, emoji="🔑", custom_id="admin_generate_keys")
    async def generate_keys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ Только для администратора!", ephemeral=True)
            return
        modal = GenerateKeyModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Server Stats", style=discord.ButtonStyle.blurple, emoji="📊", custom_id="admin_server_stats")
    async def server_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ Только для администратора!", ephemeral=True)
            return

        active = sum(1 for data in keys_db.values() if data['activated'])
        total = len(keys_db)

        embed = discord.Embed(title="📊 Статистика сервера", color=0x00ff00)
        embed.add_field(name="Всего ключей", value=total, inline=True)
        embed.add_field(name="Активировано", value=active, inline=True)
        embed.add_field(name="🌐 Хостинг", value="Render.com", inline=True)
        embed.add_field(name="Auth URL", value=AUTH_SERVER_URL, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class KeyModal(discord.ui.Modal, title="Активация лицензионного ключа"):
    key_input = discord.ui.TextInput(
        label="Введите ваш лицензионный ключ",
        placeholder="SIEO-1234-5678-9012",
        max_length=50,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().upper()

        if not key:
            await interaction.response.send_message("❌ Введите ключ!", ephemeral=True)
            return

        if key not in keys_db:
            await interaction.response.send_message("❌ Неверный ключ! Ключ не найден.", ephemeral=True)
            return

        if keys_db[key]['activated']:
            await interaction.response.send_message("❌ Ключ уже активирован другим пользователем!", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in user_activations:
            await interaction.response.send_message(
                f"❌ У вас уже активирован ключ: `{user_activations[user_id]}`",
                ephemeral=True
            )
            return

        # Активируем ключ БЕЗ HWID
        keys_db[key]['activated'] = True
        keys_db[key]['discord_id'] = user_id
        keys_db[key]['hwid'] = None
        keys_db[key]['activated_at'] = datetime.datetime.now().isoformat()
        keys_db[key]['expires_at'] = (datetime.datetime.now() + datetime.timedelta(days=keys_db[key]['duration'])).isoformat()
        
        user_activations[user_id] = key

        embed = discord.Embed(
            title="✅ Ключ успешно активирован!",
            description=f"**Ключ:** `{key}`\n**Срок:** {keys_db[key]['duration']} дней\n**Действует до:** {keys_db[key]['expires_at'][:10]}",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class GenerateKeyModal(discord.ui.Modal, title="Генерация ключей"):
    count = discord.ui.TextInput(
        label="Количество ключей",
        placeholder="10",
        max_length=3,
        style=discord.TextStyle.short
    )
    duration = discord.ui.TextInput(
        label="Срок действия (дни)", 
        placeholder="30",
        max_length=4,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.count.value)
            duration = int(self.duration.value)

            if count > 50:
                await interaction.response.send_message("❌ Максимум 50 ключей за раз!", ephemeral=True)
                return

            generated = []
            for _ in range(count):
                key = generate_key()
                keys_db[key] = {
                    'activated': False,
                    'discord_id': None,
                    'hwid': None,
                    'duration': duration,
                    'created_at': datetime.datetime.now().isoformat(),
                    'activated_at': None,
                    'expires_at': None
                }
                generated.append(key)

            embed = discord.Embed(title="🔑 Сгенерированные ключи", color=0x00ff00)
            embed.description = "\n".join([f"`{k}` - {duration} дней" for k in generated])
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Введите числа!", ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} + Auth Server ready!')
    print(f'🔐 Auth URL: {AUTH_SERVER_URL}')
    
    # Восстанавливаем активации
    for key, data in keys_db.items():
        if data['activated'] and data['discord_id']:
            user_activations[data['discord_id']] = key

    bot.add_view(PublicControlPanel())
    bot.add_view(AdminControlPanel())

    guild = bot.get_guild(GUILD_ID)
    if guild:
        await setup_channels(guild)

async def setup_channels(guild):
    """Настройка каналов"""
    public_channel = discord.utils.get(guild.channels, name="🔑-control-panel")
    if not public_channel:
        public_channel = await guild.create_text_channel("🔑-control-panel")

    await public_channel.purge(limit=10)

    embed = discord.Embed(
        title="🔒 SigeoJoiner - Система защиты",
        description="**🔥 Премиум скрипт с серверной авторизацией**\n\n"
                   "**Хостинг:** Render.com (24/7)\n"
                   "**Автоматический HWID**\n"
                   "**Серверная проверка**\n\n"
                   "Используйте кнопки ниже:",
        color=0x00ff00
    )
    await public_channel.send(embed=embed, view=PublicControlPanel())

    admin_channel = discord.utils.get(guild.channels, name="👑-admin-panel")
    if not admin_channel:
        admin_channel = await guild.create_text_channel("👑-admin-panel")

    await admin_channel.purge(limit=10)

    embed = discord.Embed(title="👑 Панель администратора", color=0xff0000)
    embed.add_field(name="Auth Server", value=AUTH_SERVER_URL, inline=False)
    await admin_channel.send(embed=embed, view=AdminControlPanel())

# ЗАПУСК ДЛЯ RENDER.COM
if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 8080))
    
    # Запускаем Discord бот в отдельном потоке
    def run_bot():
        bot.run(DISCORD_TOKEN)
    
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask сервер
    print(f"🚀 Starting SigeoJoiner on Render.com (port {port})...")
    web_server.run(host='0.0.0.0', port=port, debug=False)
