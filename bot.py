import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import re
import os

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("슬래시 명령어 동기화 완료!")

bot = MyBot()

conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_channels (
        channel_id TEXT PRIMARY KEY
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS output_channel (
        channel_id TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rare_channel (
        channel_id TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_channel (
        channel_id TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_links (
        discord_id INTEGER PRIMARY KEY,
        server_url TEXT
    )
""")
conn.commit()

ACTIVE_BIOME_MESSAGES = {}

# ==========================================
# ⚙️ [설정 구역] 
# ==========================================
ROLE_SPECIAL_GROUP_1 = "1562830412332404766"
ROLE_SPECIAL_GROUP_2 = "1566090108170670342"

BIOME_ROLE_CONFIG = {
    "Hell": "1562828440443293816",
    "Heaven": "1562828596471533631",
    "Null": "1567368669053460540",
    "Lost Forest": "1562828696178528417",
    "Sandstorm": "1567368780261228736",
    "Starfall": "1562830216001228850",
    "Corruption": "1562830718659469383",
    "Singularity": "1562830295559053432",
    "The Radiant Forest": "1562828821340880936",
}

BIOME_COLORS = {
    "Hell": 0xCC0000,
    "Heaven": 0xFFCC33,
    "Null": 0xCCCCCC,
    "Dreamspace": 0xFF99FF,
    "Cyberspace": 0x6666FF,
    "Glitch": 0x003300,
    "Pumpkin Moon": 0xFF6600,
    "Blood Rain": 0xFF0000,
    "Lost Forest": 0x66CC00,
    "Graveyard": 0x333333,
    "Sandstorm": 0xCC9966,
    "Starfall": 0x333399,
    "Corruption": 0x663399,
    "Singularity": 0x660000,
    "The Radiant Forest": 0xCC99FF,
    "Windy": 0x99FFFF,
    "Snowy": 0xFFFFFF,
    "Rainy": 0x0066CC
}

CUSTOM_CHECK_EMOJI = discord.PartialEmoji(name="check", id=1572517054693777588)
CUSTOM_CROSS_EMOJI = discord.PartialEmoji(name="cross", id=1572517290111672431)
# ==========================================

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (ID: {bot.user.id})")
    cursor.execute("SELECT channel_id FROM source_channels")
    saved_sources = [row[0] for row in cursor.fetchall()]
    print(f"현재 등록된 감지 채널 ID 목록: {saved_sources}")
    print("----------------------------------------")

@bot.tree.command(name="채널등록", description="현재 채널을 매크로 감지 채널로 영구 등록합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 채널등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("INSERT OR IGNORE INTO source_channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **매크로 감지 채널**로 영구 등록되었습니다!", ephemeral=True)

@bot.tree.command(name="출력방등록", description="현재 채널을 일반 알림 출력방(test방)으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 출력방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM output_channel")
    cursor.execute("INSERT INTO output_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **일반 알림 출력방(test방)**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="rare방등록", description="현재 채널을 특수 바이옴 전용 방(rare방)으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def rare방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM rare_channel")
    cursor.execute("INSERT INTO rare_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **특수 바이옴 전용 방(rare방)**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="이벤트방등록", description="현재 채널을 이벤트 바이옴 전용 방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 이벤트방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM event_channel")
    cursor.execute("INSERT INTO event_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **이벤트 바이옴 전용 방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="링크등록", description="본인의 비공개 서버 링크를 등록합니다.")
@app_commands.describe(url="비공개 서버 링크 URL")
async def 링크등록(interaction: discord.Interaction, url: str):
    discord_id = interaction.user.id
    cursor.execute("INSERT OR REPLACE INTO user_links (discord_id, server_url) VALUES (?, ?)", (discord_id, url))
    conn.commit()
    await interaction.response.send_message(f"✅ {interaction.user.mention}님의 비공개 서버 링크가 성공적으로 등록되었습니다!", ephemeral=True)

class BiomeControlView(discord.ui.View):
    def __init__(self, server_url: str):
        super().__init__(timeout=None)
        self.check_count = 0
        self.cross_count = 0
        self.checked_users = set()
        self.crossed_users = set()
        
        self.add_item(discord.ui.Button(
            label="Join Server",
            url=server_url,
            style=discord.ButtonStyle.link,
            row=0
        ))

    @discord.ui.button(label="0", emoji=CUSTOM_CHECK_EMOJI, style=discord.ButtonStyle.secondary, row=0)
    async def check_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.checked_users:
            self.checked_users.remove(user_id)
            self.check_count = max(0, self.check_count - 1)
        else:
            self.checked_users.add(user_id)
            self.check_count += 1
            if user_id in self.crossed_users:
                self.crossed_users.remove(user_id)
                self.cross_count = max(0, self.cross_count - 1)

        for child in self.children:
            if getattr(child, "emoji", None) == CUSTOM_CHECK_EMOJI:
                child.label = f"{self.check_count}"
            elif getattr(child, "emoji", None) == CUSTOM_CROSS_EMOJI:
                child.label = f"{self.cross_count}"

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="0", emoji=CUSTOM_CROSS_EMOJI, style=discord.ButtonStyle.secondary, row=0)
    async def cross_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.crossed_users:
            self.crossed_users.remove(user_id)
            self.cross_count = max(0, self.cross_count - 1)
        else:
            self.crossed_users.add(user_id)
            self.cross_count += 1
            if user_id in self.checked_users:
                self.checked_users.remove(user_id)
                self.check_count = max(0, self.check_count - 1)

        for child in self.children:
            if getattr(child, "emoji", None) == CUSTOM_CHECK_EMOJI:
                child.label = f"{self.check_count}"
            elif getattr(child, "emoji", None) == CUSTOM_CROSS_EMOJI:
                child.label = f"{self.cross_count}"

        await interaction.response.edit_message(view=self)

def extract_all_text(message) -> str:
    parts = []
    if message.content:
        parts.append(message.content)

    for embed in message.embeds:
        data = embed.to_dict()
        if data.get("title"):
            parts.append(str(data["title"]))
        if data.get("description"):
            parts.append(str(data["description"]))
        for field in data.get("fields", []):
            parts.append(f"{field.get('name', '')}: {field.get('value', '')}")
        if data.get("footer", {}).get("text"):
            parts.append(str(data["footer"]["text"]))

    def walk_components(comps):
        for comp in comps:
            c_dict = comp.to_dict() if hasattr(comp, "to_dict") else (comp if isinstance(comp, dict) else {})
            if c_dict.get("content"):
                parts.append(str(c_dict["content"]))
            if c_dict.get("label"):
                parts.append(str(c_dict["label"]))
            if "components" in c_dict:
                walk_components(c_dict["components"])

    if getattr(message, "components", None):
        walk_components(message.components)

    return "\n".join(parts)

async def process_macro_message(message):
    if message.author == bot.user:
        return

    channel_id_str = str(message.channel.id)
    cursor.execute("SELECT 1 FROM source_channels WHERE channel_id = ?", (channel_id_str,))
    if not cursor.fetchone():
        return

    full_text = extract_all_text(message)
    clean_text = re.sub(r"[*#>`]", "", full_text)

    end_pattern = r"Biome\s+Ended|Ended|Strange\s+Controller\s+was\s+used|Biome\s+Randomizer\s+was\s+used"
    
    if re.search(end_pattern, clean_text, re.IGNORECASE):
        target_keys = [k for k in ACTIVE_BIOME_MESSAGES.keys() if k[0] == channel_id_str]
        for tracking_key in target_keys:
            sent_msg = ACTIVE_BIOME_MESSAGES[tracking_key]
            try:
                if sent_msg.embeds:
                    old_embed = sent_msg.embeds[0]
                    old_desc = old_embed.description
                    
                    if "(사라짐)" not in old_desc:
                        new_desc = re.sub(r"(\*\*감지 시간:\*\*\s*<t:\d+:R>)", r"\1 (사라짐)", old_desc)
                        if "(사라짐)" not in new_desc:
                            new_desc = re.sub(r"\*\*감지 시간:\*\*.*", "**감지 시간:** (사라짐)", old_desc)
                    else:
                        new_desc = old_desc
                    
                    new_embed = discord.Embed(
                        title=f"{old_embed.title}",
                        description=new_desc,
                        color=old_embed.color
                    )
                    await sent_msg.edit(content=sent_msg.content, embed=new_embed)
            except Exception as e:
                print(f"메시지 수정 중 오류 발생: {e}")
            
            del ACTIVE_BIOME_MESSAGES[tracking_key]
        return

    if not re.search(r"Biome\s+Started", clean_text, re.IGNORECASE):
        return

    biome_name = None
    match = re.search(r"Biome\s+Started\s*[-–—:]\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    if match:
        biome_name = match.group(1).strip()

    if not biome_name:
        biome_name = "Unknown"

    exclude_biomes = ["normal"]
    if biome_name.lower() in exclude_biomes:
        return

    # 💡 바이옴 이름을 모두 대문자로 변환 (.upper() 추가)
    biome_name = biome_name.upper()

    biome_lower = biome_name.lower()
    role_to_mention = None

    rare_group = ["dreamspace", "glitch", "cyberspace"]
    event_group = ["pumpkin moon", "graveyard", "blood rain"]

    if biome_lower in rare_group:
        role_to_mention = ROLE_SPECIAL_GROUP_1
    elif biome_lower in event_group:
        role_to_mention = ROLE_SPECIAL_GROUP_2
    else:
        for key, r_id in BIOME_ROLE_CONFIG.items():
            if key.lower() == biome_lower:
                role_to_mention = r_id
                break

    mention_text = f"<@&{role_to_mention}>" if role_to_mention and role_to_mention.isdigit() else ""

    user_private_url = "https://discord.gg/기본링크"
    owner_display = "@알수없는-사용자"

    cursor.execute("SELECT discord_id, server_url FROM user_links ORDER BY rowid DESC LIMIT 1")
    link_result = cursor.fetchone()
    
    if link_result:
        discord_id, user_private_url = link_result[0], link_result[1]
        owner_display = f"<@{discord_id}>"

    embed_color = 0x00A2FF
    for key, color_val in BIOME_COLORS.items():
        if key.lower() == biome_lower:
            embed_color = color_val
            break

    session_match = re.search(r"Session\s+Time\s*:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    if not session_match:
        session_match = re.search(r"Uptime\s*:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    session_duration = session_match.group(1).strip() if session_match else "4h 34m"

    msg_timestamp = int(message.created_at.timestamp())
    dynamic_time_str = f"<t:{msg_timestamp}:R>"

    embed_description = (
        f"**유저:** {owner_display}\n"
        f"**감지 시간:** {dynamic_time_str}\n"
        f"**서버 시간:** {session_duration}"
    )

    new_embed = discord.Embed(
        title=f"{biome_name}",
        description=embed_description,
        color=embed_color
    )

    view = BiomeControlView(user_private_url)

    target_channel = None

    if biome_lower in rare_group:
        cursor.execute("SELECT channel_id FROM rare_channel LIMIT 1")
        rare_row = cursor.fetchone()
        if rare_row:
            target_channel = bot.get_channel(int(rare_row[0]))
    elif biome_lower in event_group:
        cursor.execute("SELECT channel_id FROM event_channel LIMIT 1")
        event_row = cursor.fetchone()
        if event_row:
            target_channel = bot.get_channel(int(event_row[0]))
    else:
        cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
        output_row = cursor.fetchone()
        if output_row:
            target_channel = bot.get_channel(int(output_row[0]))

    if target_channel:
        sent_message = await target_channel.send(content=mention_text, embed=new_embed, view=view)
        ACTIVE_BIOME_MESSAGES[(channel_id_str, "default")] = sent_message

@bot.event
async def on_message(message):
    await process_macro_message(message)

@bot.event
async def on_message_edit(before, after):
    await process_macro_message(after)

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
