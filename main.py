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

# Веб-сервер для авторизации
web_server = Flask(__name__)

# База данных (в памяти)
keys_db = {}
user_activations = {}

@web_server.route('/')
def home():
    return """
    <h1>🔒 SigeoJoiner Auth Server</h1>
    <p>Status: <span style="color: green;">✅ ONLINE</span></p>
    <p>Host: <strong>Render.com</strong></p>
    <p>Endpoints:</p>
    <ul>
    <li><code>/auth?key=KEY</code> - авторизация</li>
    <li><code>/validate</code> - проверка ключа</li>
    <li><code>/stats</code> - статистика</li>
    </ul>
    """

@web_server.route('/auth', methods=['POST', 'GET'])
def auth_endpoint():
    """Основная точка авторизации"""
    
    # Получаем ключ
    key = request.args.get('key') or request.form.get('key')
    
    if not key:
        return "ERROR: No key provided", 400
    
    # Проверяем ключ в базе
    if key not in keys_db:
        return "ERROR: Invalid key", 403
    
    key_data = keys_db[key]
    
    # Проверяем активацию
    if not key_data['activated']:
        return "ERROR: Key not activated", 403
    
    # Проверяем срок действия
    expires_at = datetime.datetime.fromisoformat(key_data['expires_at'])
    if datetime.datetime.now() > expires_at:
        return "ERROR: Key expired", 403
    
    # Автоматическая проверка HWID
    client_hwid = request.args.get('hwid') or request.form.get('hwid')
    
    # Если HWID не передан - генерируем его
    if not client_hwid:
        client_hwid = hashlib.md5(str(uuid.getnode()).encode()).hexdigest()[:16].upper()
        
        return f'''
getgenv().Key = "{key}"
getgenv().HWID = "{client_hwid}"

print("🆔 Auto-detected HWID:", getgenv().HWID)

local function register_hwid()
    local response = request({{
        Url = "https://{os.environ.get('RENDER_EXTERNAL_URL', 'localhost:8080')}/auth?key={key}&hwid={client_hwid}",
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
    
    # Проверяем HWID
    if key_data['hwid'] and key_data['hwid'] != client_hwid:
        return "ERROR: HWID mismatch", 403
    
    # Привязываем HWID если нужно
    if not key_data['hwid']:
        keys_db[key]['hwid'] = client_hwid
    
    # Возвращаем основной скрипт
    try:
        with open('encrypted_script.lua', 'r') as f:
            encrypted_content = f.read()
        
        return f"""
print("✅ SigeoJoiner loaded successfully!")
print("🔑 License valid until: {expires_at.strftime('%Y-%m-%d')}")

{encrypted_content}
"""
    except Exception as e:
        return f"ERROR: Failed to load script - {str(e)}"

@web_server.route('/stats')
def stats():
    """Статистика"""
    active = sum(1 for data in keys_db.values() if data['activated'])
    total = len(keys_db)
    
    return jsonify({
        'total_keys': total,
        'active_keys': active,
        'status': 'online'
    })

# Discord бот
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Утилиты
def generate_key():
    return f"SIEO-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

# Views (упрощенные)
class PublicControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Get Script", style=discord.ButtonStyle.green, emoji="📜", custom_id="get_script")
    async def get_script(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        # Ищем ключ пользователя
        user_key = None
        for key, data in keys_db.items():
            if data.get('discord_id') == user_id and data['activated']:
                user_key = key
                break

        if not user_key:
            await interaction.response.send_message("❌ Нет активированных ключей!", ephemeral=True)
            return

        render_url = os.environ.get('RENDER_EXTERNAL_URL', 'localhost:8080')
        script_code = f'getgenv().Key = "{user_key}"\nloadstring(game:HttpGet("https://{render_url}/auth", true))()'

        embed = discord.Embed(title="✅ Ваш скрипт:", color=0x00ff00)
        embed.description = f"```lua\n{script_code}\n```"
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✅ Скрипт отправлен в ЛС!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Откройте ЛС!", ephemeral=True)

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} is ready!')
    
    bot.add_view(PublicControlPanel())
    
    # Создаем каналы
    guild = bot.get_guild(GUILD_ID)
    if guild:
        channel = discord.utils.get(guild.channels, name="🔑-control-panel")
        if not channel:
            channel = await guild.create_text_channel("🔑-control-panel")
        
        await channel.purge(limit=10)
        embed = discord.Embed(title="🔒 SigeoJoiner", description="Нажми кнопку для получения скрипта", color=0x00ff00)
        await channel.send(embed=embed, view=PublicControlPanel())

# Запуск
if __name__ == '__main__':
    # Запускаем бота в потоке
    def run_bot():
        bot.run(DISCORD_TOKEN)
    
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем веб-сервер
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Starting on port {port}...")
    web_server.run(host='0.0.0.0', port=port, debug=False)
