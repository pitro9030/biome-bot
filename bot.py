import discord
from discord.ext import commands
import sqlite3
import re
import os

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

# 테이블 자동 생성 (일반 출력방, rare 출력방, 이벤트 출력방, 유저 링크)
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
        discord_id INTEGER,
        roblox_name TEXT,
        server_url TEXT
    )
""")
conn.commit()

SOURCE_CHANNELS = set()
ACTIVE_BIOME_MESSAGES = {}

# ==========================================
# ⚙️ [설정 구역] 
# ==========================================
ROLE_SPECIAL_GROUP_1 = "여기에_글리치드림스페이스사이버스페이스_통일역할ID입력"
ROLE_SPECIAL_GROUP_2 = "여기에_펌킨문그레이브야드블러드레인_통일역할ID입력"

BIOME_ROLE_CONFIG = {
    "Hell": "역할ID_입력",
    "Heaven": "역할ID_입력",
    "Null": "역할ID_입력",
    "Lost Forest": "역할ID_입력",
    "Sandstorm": "역할ID_입력",
    "Starfall": "역할ID_입력",
    "Corruption": "역할ID_입력",
    "Singularity": "역할ID_입력",
    "The Radiant Forest": "역할ID_입력",
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
    "The Radiant Forest": 0xCC99FF
}

CUSTOM_CHECK_EMOJI = discord.PartialEmoji(name="check", id=1572517054693777588) # 본인 서버 체크 이모티콘 ID 입력
CUSTOM_CROSS_EMOJI = discord.PartialEmoji(name="cross", id=1572517290111672431) # 본인 서버 엑스 이모티콘 ID 입력
# ==========================================

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (ID: {bot.user.id})")
    print("----------------------------------------")

@bot.command()
@commands.has_permissions(administrator=True)
async def 채널등록(ctx):
    channel_id = str(ctx.channel.id)
    SOURCE_CHANNELS.add(channel_id)
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **매크로 감지 채널**로 즉시 등록되었습니다!")

@bot.command()
@commands.has_permissions(administrator=True)
async def 출력방등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM output_channel")
    cursor.execute("INSERT INTO output_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **일반 알림 출력방(test방)**으로 설정되었습니다!")

@bot.command()
@commands.has_permissions(administrator=True)
async def rare방등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM rare_channel")
    cursor.execute("INSERT INTO rare_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **특수 바이옴 전용 방(rare방)**으로 설정되었습니다!")

# 💡 Pumpkin Moon, Graveyard, Blood Rain 전용 방 등록 명령어
@bot.command()
@commands.has_permissions(administrator=True)
async def 이벤트방등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM event_channel")
    cursor.execute("INSERT INTO event_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **이벤트 바이옴 전용 방(Pumpkin Moon/Graveyard/Blood Rain)**으로 설정되었습니다!")

@bot.command()
async def 링크등록(ctx, roblox_name: str, url: str):
    discord_id = ctx.author.id
    cursor.execute("SELECT * FROM user_links WHERE roblox_name = ?", (roblox_name,))
    if cursor.fetchone():
        cursor.execute("UPDATE user_links SET discord_id = ?, server_url = ? WHERE roblox_name = ?", (discord_id, url, roblox_name))
    else:
        cursor.execute("INSERT INTO user_links (discord_id, roblox_name, server_url) VALUES (?, ?, ?)", (discord_id, roblox_name, url))
    conn.commit()
    await ctx.send(f"✅ **{roblox_name}**님의 비공개 서버 링크와 디스코드 계정({ctx.author.mention})이 연동되었습니다!")

class BiomeControlView(discord.ui.View):
    def __init__(self, server_url: str):
        super().__init__(timeout=None)
        self.check_count = 0
        self.cross_count = 0
        self.checked_users = set()
        self.crossed_users = set()
        
        self.add_item(discord.ui.Button(
            label="서버 참가",
            url=server_url,
            style=discord.ButtonStyle.link,
            row=0
        ))

    @discord.ui.button(label="0", emoji=CUSTOM_CHECK_EMOJI, style=discord.ButtonStyle.secondary, row=1)
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

    @discord.ui.button(label="0", emoji=CUSTOM_CROSS_EMOJI, style=discord.ButtonStyle.secondary, row=1)
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

async def process_macro_message(message):
    if message.author == bot.user:
        return

    channel_id_str = str(message.channel.id)
    if channel_id_str not in SOURCE_CHANNELS:
        return

    embed_texts = []
    for embed in message.embeds:
        data = embed.to_dict()
        t = data.get("title", "")
        d = data.get("description", "")
        fields = data.get("fields", [])
        f = "".join([f"\n{f.get('name', '')}: {f.get('value', '')}" for f in fields])
        u = data.get("url", "")
        embed_texts.append(f"{t}\n{d}\n{f}\n{u}")
    
    full_text = f"{message.content}\n" + "\n".join(embed_texts)

    account_match = re.search(r"Account[:\s]+\*\*([^*]+)\*\*", full_text)
    if not account_match:
        account_match = re.search(r"Account[:\s]+([^\n\r]+)", full_text)
    
    roblox_username = account_match.group(1).strip() if account_match else None

    if "Ended" in full_text:
        tracking_key = (channel_id_str, roblox_username)
        if tracking_key in ACTIVE_BIOME_MESSAGES:
            sent_msg = ACTIVE_BIOME_MESSAGES[tracking_key]
            try:
                if sent_msg.embeds:
                    old_embed = sent_msg.embeds[0]
                    new_embed = discord.Embed.from_dict(old_embed.to_dict())
                    
                    for i, field in enumerate(new_embed.fields):
                        if field.name == "Detection Time" or field.name == "바이옴 감지 시간":
                            new_embed.set_field_at(i, name="Detection Time", value="방금 전 - (사라짐)", inline=False)

                    await sent_msg.edit(content=sent_msg.content, embed=new_embed)
            except Exception as e:
                print(f"메시지 수정 중 오류 발생: {e}")
            
            del ACTIVE_BIOME_MESSAGES[tracking_key]
        return

    if "Started" not in full_text:
        return

    biome_name = None
    match = re.search(r"Biome\s+Started\s*-\s*([^\n\r]+)", full_text, re.IGNORECASE)
    if match:
        biome_name = match.group(1).strip()
    else:
        if "Biome Started -" in full_text:
            parts = full_text.split("Biome Started -")
            if len(parts) > 1:
                biome_name = parts[1].split("\n")[0].strip()

    if not biome_name:
        biome_name = "Unknown"

    exclude_biomes = ["normal", "snowy", "windy", "rainy"]
    if biome_name.lower() in exclude_biomes:
        return

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
    owner_display = f"@알수없는-사용자 ({roblox_username})" if roblox_username else "@알수없는-사용자"

    if roblox_username:
        cursor.execute("SELECT discord_id, server_url FROM user_links WHERE roblox_name = ?", (roblox_username,))
        result = cursor.fetchone()
        if result:
            discord_id, user_private_url = result[0], result[1]
            if discord_id:
                owner_display = f"<@{discord_id}>"

    embed_color = 0x00A2FF
    for key, color_val in BIOME_COLORS.items():
        if key.lower() == biome_lower:
            embed_color = color_val
            break

    new_embed = discord.Embed(
        title=f"**{biome_name}**",
        color=embed_color
    )
    new_embed.add_field(name="Macroer", value=owner_display, inline=False)
    new_embed.add_field(name="Detection Time", value="방금 전", inline=False)
    new_embed.add_field(name="Session Duration", value="4h 34m", inline=False)

    view = BiomeControlView(user_private_url)

    # 💡 [출력 채널 3갈래 분기 처리]
    # 1. Dreamspace, Glitch, Cyberspace -> rare_channel
    # 2. Pumpkin Moon, Graveyard, Blood Rain -> event_channel
    # 3. 그 외 바이옴 -> output_channel (test방)
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
        if roblox_username:
            ACTIVE_BIOME_MESSAGES[(channel_id_str, roblox_username)] = sent_message

@bot.event
async def on_message(message):
    await process_macro_message(message)
    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    await process_macro_message(after)

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
