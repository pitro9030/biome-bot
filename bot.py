import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import re
import os
import asyncio
import time

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

cursor.execute("CREATE TABLE IF NOT EXISTS source_channels (channel_id TEXT PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS output_channel (channel_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS rare_channel (channel_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS event_channel (channel_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS jester_channel (channel_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS mari_channel (channel_id TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_links (discord_id INTEGER PRIMARY KEY, roblox_name TEXT, server_url TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS acrux_user_links (discord_id INTEGER PRIMARY KEY, roblox_name TEXT, webhook_name TEXT, server_url TEXT)")
conn.commit()

ACTIVE_BIOME_MESSAGES = {}
RECENT_ALERTS = {}
ACTIVE_BIOME_SIGNATURES = {}  # 🛡️ [추가] (유저/웹훅, 바이옴이름, 서버시간) 조합을 저장하여 완벽한 중복 감지

# ==========================================
# ⚙️ [설정 구역] 
# ==========================================
ROLE_SPECIAL_GROUP_1 = "1562830412332404766"
ROLE_SPECIAL_GROUP_2 = "1566090108170670342"

ROLE_JESTER = "1562830501461631016"
ROLE_MARI = "1562830587549712414"

ALLOWED_CHANNEL_ROLE_ID = 1562831439802798152

BIOME_ROLE_CONFIG = {
    "Hell": "1562828440443293816",
    "Heaven": "1562828596471533631",
    "Null": "1567368669053460540",
    "Lost Forest": "1562828696178528417",
    "Sandstorm": "1567368780261228736",
    "Sand Storm": "1567368780261228736",
    "Starfall": "1562830216001228850",
    "Corruption": "1562830718659469383",
    "Singularity": "1562830295559053432",
    "The Radiant Forest": "1562828821340880936",
}

BIOME_COLORS = {
    "hell": 0xCC0000,
    "heaven": 0xFFCC33,
    "null": 0x999999,
    "dreamspace": 0xFF99FF,
    "cyberspace": 0x6666FF,
    "glitch": 0x003300,
    "pumpkin moon": 0xFF6600,
    "blood rain": 0xFF0000,
    "lost forest": 0x66CC00,
    "graveyard": 0x333333,
    "sandstorm": 0xCC9966,
    "sand storm": 0xCC9966,
    "starfall": 0x333399,
    "corruption": 0x663399,
    "singularity": 0x660000,
    "the radiant forest": 0xCC99FF,
    "windy": 0x99FFFF,
    "snowy": 0xFFFFFF,
    "rainy": 0x0066CC,
    "jester": 0x6633CC,
    "mari": 0x99FF66
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

def has_allowed_role():
    async def predicate(interaction: discord.Interaction):
        role = interaction.guild.get_role(ALLOWED_CHANNEL_ROLE_ID)
        if role and role in interaction.user.roles:
            return True
        await interaction.response.send_message("❌ 이 명령어를 사용할 수 있는 권한이 없습니다.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.tree.command(name="도움말", description="봇에서 사용 가능한 명령어와 안내를 확인합니다.")
async def 도움말_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 밤크로 봇 도움말",
        description="바이옴 및 상인 감지 봇의 명령어 안내입니다.",
        color=0x00A2FF
    )
    
    embed.add_field(
        name="🔗 유저 링크 관리 명령어",
        value=(
            "• `/링크등록 [로블록스닉네임] [서버링크]`\n"
            "• `/아크록스링크등록 [로블록스닉네임] [웹훅봇닉네임] [서버링크]`\n"
            "• `/링크삭제`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛠️ 권한 필요 명령어",
        value=(
            "• `/채널등록` : 감지 채널 등록\n"
            "• `/출력방등록` / `/레어방등록` / `/이벤트방등록` / `/제스터방등록` / `/마리방등록`"
        ),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="채널등록", description="현재 채널을 매크로 감지 채널로 등록합니다.")
@has_allowed_role()
async def 채널등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("INSERT OR IGNORE INTO source_channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **매크로 감지 채널**로 등록되었습니다!", ephemeral=True)

@bot.tree.command(name="출력방등록", description="현재 채널을 일반 알림 출력방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 출력방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM output_channel")
    cursor.execute("INSERT INTO output_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **일반 알림 출력방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="레어방등록", description="현재 채널을 특수 바이옴 전용 방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 레어방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM rare_channel")
    cursor.execute("INSERT INTO rare_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **특수 바이옴 전용 방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="이벤트방등록", description="현재 채널을 이벤트 바이옴 전용 방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 이벤트방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM event_channel")
    cursor.execute("INSERT INTO event_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **이벤트 바이옴 전용 방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="제스터방등록", description="현재 채널을 제스터 상인 전용 방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 제스터방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM jester_channel")
    cursor.execute("INSERT INTO jester_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **제스터 상인 전용 방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="마리방등록", description="현재 채널을 마리 상인 전용 방으로 설정합니다.")
@app_commands.checks.has_permissions(administrator=True)
async def 마리방등록(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    cursor.execute("DELETE FROM mari_channel")
    cursor.execute("INSERT INTO mari_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await interaction.response.send_message(f"✅ 이 채널({interaction.channel.mention})이 **마리 상인 전용 방**으로 설정되었습니다!", ephemeral=True)

@bot.tree.command(name="링크등록", description="로블록스 닉네임과 비공개 서버 링크를 연동합니다.")
@app_commands.describe(roblox_name="로블록스 닉네임", url="비공개 서버 링크 URL")
async def 링크등록(interaction: discord.Interaction, roblox_name: str, url: str):
    await interaction.response.defer(ephemeral=True)
    discord_id = interaction.user.id
    clean_name = roblox_name.strip()
    clean_url = url.strip()

    try:
        cursor.execute("DELETE FROM user_links WHERE discord_id = ? OR LOWER(TRIM(roblox_name)) = LOWER(?)", (discord_id, clean_name))
        cursor.execute("INSERT INTO user_links (discord_id, roblox_name, server_url) VALUES (?, ?, ?)", (discord_id, clean_name, clean_url))
        conn.commit()
        await interaction.followup.send(f"✅ **{clean_name}**님의 비공개 서버 링크가 연동되었습니다!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {e}", ephemeral=True)

@bot.tree.command(name="아크록스링크등록", description="아크록스 유저 전용 연동")
@app_commands.describe(roblox_name="실제 로블록스 닉네임", webhook_name="웹훅에 표시되는 봇 닉네임", url="비공개 서버 링크 URL")
async def 아크록스링크등록(interaction: discord.Interaction, roblox_name: str, webhook_name: str, url: str):
    await interaction.response.defer(ephemeral=True)
    discord_id = interaction.user.id
    clean_roblox = roblox_name.strip()
    clean_webhook = webhook_name.strip()
    clean_url = url.strip()

    try:
        cursor.execute("DELETE FROM acrux_user_links WHERE discord_id = ? OR LOWER(TRIM(webhook_name)) = LOWER(?)", (discord_id, clean_webhook))
        cursor.execute("INSERT INTO acrux_user_links (discord_id, roblox_name, webhook_name, server_url) VALUES (?, ?, ?, ?)", 
                       (discord_id, clean_roblox, clean_webhook, clean_url))
        conn.commit()
        await interaction.followup.send(f"✅ **[아크록스 연동 완료]** {clean_roblox} ({clean_webhook})", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {e}", ephemeral=True)

@bot.tree.command(name="링크삭제", description="본인이 등록한 서버 링크 연동 정보를 삭제합니다.")
async def 링크삭제(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    discord_id = interaction.user.id
    try:
        cursor.execute("DELETE FROM user_links WHERE discord_id = ?", (discord_id,))
        d1 = cursor.rowcount
        cursor.execute("DELETE FROM acrux_user_links WHERE discord_id = ?", (discord_id,))
        d2 = cursor.rowcount
        conn.commit()
        if d1 > 0 or d2 > 0:
            await interaction.followup.send(f"🗑️ 링크 데이터가 모두 삭제되었습니다.", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ 등록된 링크 데이터가 없습니다.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {e}", ephemeral=True)

class BiomeControlView(discord.ui.View):
    def __init__(self, server_url: str):
        super().__init__(timeout=None)
        self.check_count = 0
        self.cross_count = 0
        self.checked_users = set()
        self.crossed_users = set()
        
        valid_url = server_url if server_url.startswith(("http://", "https://")) else "https://discord.gg/기본링크"
        self.add_item(discord.ui.Button(
            label="Join Server",
            url=valid_url,
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

def format_session_time(raw_time: str) -> str:
    raw_time = raw_time.strip()
    total_seconds = 0

    hms_colon = re.search(r"^(\d+):(\d+):(\d+)$", raw_time)
    if hms_colon:
        h = int(hms_colon.group(1))
        m = int(hms_colon.group(2))
        s = int(hms_colon.group(3))
        total_seconds = h * 3600 + m * 60 + s
    else:
        d_match = re.search(r"(\d+)\s*d", raw_time, re.IGNORECASE)
        h_match = re.search(r"(\d+)\s*(?:hr|h)", raw_time, re.IGNORECASE)
        m_match = re.search(r"(\d+)\s*m", raw_time, re.IGNORECASE)
        s_match = re.search(r"(\d+)\s*s", raw_time, re.IGNORECASE)

        if d_match: total_seconds += int(d_match.group(1)) * 86400
        if h_match: total_seconds += int(h_match.group(1)) * 3600
        if m_match: total_seconds += int(m_match.group(1)) * 60
        if s_match: total_seconds += int(s_match.group(1))

        if not (d_match or h_match or m_match or s_match):
            return raw_time

    if total_seconds >= 86400:
        days = total_seconds // 86400
        remainder = total_seconds % 86400
        hours = remainder // 3600
        minutes = (remainder % 3600) // 60
        return f"{days}d {hours}h {minutes}m"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours}h {minutes}m {seconds}s"

def get_user_link_info(roblox_username: str, webhook_author_name: str = None):
    if webhook_author_name:
        cursor.execute("SELECT discord_id, roblox_name, server_url FROM acrux_user_links WHERE LOWER(TRIM(webhook_name)) = LOWER(?)", (webhook_author_name.strip(),))
        result = cursor.fetchone()
        if result:
            discord_id, actual_roblox_name, server_url = result[0], result[1], result[2]
            owner_display = f"<@{discord_id}>" if discord_id else "@알수없는-사용자"
            return owner_display, server_url

    if roblox_username:
        cursor.execute("SELECT discord_id, server_url FROM user_links WHERE LOWER(TRIM(roblox_name)) = LOWER(?)", (roblox_username.strip(),))
        result = cursor.fetchone()
        if result:
            discord_id, server_url = result[0], result[1]
            owner_display = f"<@{discord_id}>" if discord_id else "@알수없는-사용자"
            return owner_display, server_url

    return "@알수없는-사용자", "https://discord.gg/기본링크"

async def process_macro_message(message):
    if message.author == bot.user:
        return

    channel_id_str = str(message.channel.id)
    cursor.execute("SELECT 1 FROM source_channels WHERE channel_id = ?", (channel_id_str,))
    if not cursor.fetchone():
        return

    full_text = extract_all_text(message)
    print(f"[감지된 원본 텍스트 - 채널 {channel_id_str}]\n{full_text}\n{'-'*30}")

    clean_text = re.sub(r"[*#>`]", "", full_text)

    end_pattern = r"Biome\s+Ended|Ended|Strange\s+Controller\s+was\s+used|Biome\s+Randomizer\s+was\s+used"
    
    account_match = re.search(r"Account\s*:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    roblox_username = account_match.group(1).strip() if account_match else None

    webhook_author_name = None
    if message.webhook_id and message.author and message.author.name:
        if "acrux" not in message.author.name.lower():
            webhook_author_name = message.author.name.strip()

    tracking_key_base = webhook_author_name or (roblox_username.lower() if roblox_username else None)

    # 세션 시간 추출 (중복 판단용)
    session_match = re.search(r"(?:Session\s+Time|Uptime)\s*:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    raw_session = session_match.group(1).strip() if session_match else "4h 34m"
    session_duration = format_session_time(raw_session)

    # 🛡️ [추가 필터] 동일 유저가 동일 바이옴명 + 동일 서버 시간(Uptime)으로 이미 알림을 보냈다면 무시
    # 바이옴 이름 또는 상인 이름 추출 시도
    detected_event_name = None
    merchant_match = re.search(r"Merchant\s+Arrived\s*[-–—:]\s*([^\n\r]+)", clean_text, re.IGNORECASE)
    biome_match = re.search(r"Biome\s+Started\s*[-–—:]\s*([^\n\r]+)", clean_text, re.IGNORECASE)

    if merchant_match:
        detected_event_name = merchant_match.group(1).strip().lower()
    elif biome_match:
        detected_event_name = biome_match.group(1).strip().lower()

    if tracking_key_base and detected_event_name:
        signature = (tracking_key_base, detected_event_name, session_duration)
        if not re.search(end_pattern, clean_text, re.IGNORECASE):
            if signature in ACTIVE_BIOME_SIGNATURES:
                print(f"🛡️ [중복 차단] {tracking_key_base님의 {detected_event_name} (서버 시간: {session_duration}) 이미 처리된 동일 로그 무시됨.")
                return
            ACTIVE_BIOME_SIGNATURES[signature] = channel_id_str

    if merchant_match:
        raw_merchant = merchant_match.group(1).strip().lower()
        
        merchant_name = None
        role_to_mention = None
        target_table = None

        if "jester" in raw_merchant:
            merchant_name = "제스터"
            role_to_mention = ROLE_JESTER
            target_table = "jester_channel"
        elif "mari" in raw_merchant:
            merchant_name = "마리"
            role_to_mention = ROLE_MARI
            target_table = "mari_channel"

        if merchant_name:
            mention_text = f"<@&{role_to_mention}>" if role_to_mention and role_to_mention.isdigit() else ""
            owner_display, user_private_url = get_user_link_info(roblox_username, webhook_author_name)

            embed_color = BIOME_COLORS.get(merchant_name.lower(), 0x00A2FF)

            msg_timestamp = int(message.created_at.timestamp())
            dynamic_time_str = f"<t:{msg_timestamp}:R>"

            embed_description = (
                f"# {merchant_name}\n"
                f"**유저** : {owner_display}\n"
                f"**감지 시간** : {dynamic_time_str}\n"
                f"**서버 시간** : {session_duration}"
            )

            new_embed = discord.Embed(title="", description=embed_description, color=embed_color)
            view = BiomeControlView(user_private_url)

            target_channel = None
            if target_table:
                cursor.execute(f"SELECT channel_id FROM {target_table} LIMIT 1")
                row = cursor.fetchone()
                if row:
                    target_channel = bot.get_channel(int(row[0]))
            
            if not target_channel:
                cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
                output_row = cursor.fetchone()
                if output_row:
                    target_channel = bot.get_channel(int(output_row[0]))

            if target_channel:
                sent_message = await target_channel.send(content=mention_text, embed=new_embed, view=view)
                
                async def expire_merchant():
                    await asyncio.sleep(160)
                    try:
                        if sent_message.embeds:
                            old_embed = sent_message.embeds[0]
                            old_desc = old_embed.description
                            new_desc = re.sub(r"(\*\*감지 시간\*\*\s*:\s*<t:\d+:R>)(.*)", r"\1 (사라짐)", old_desc)
                            if "(사라짐)" not in new_desc:
                                new_desc = re.sub(r"\*\*감지 시간\*\*\s*:\s*.*", "**감지 시간** : (사라짐)", old_desc)
                            
                            new_embed = discord.Embed(title="", description=new_desc, color=old_embed.color)
                            await sent_message.edit(content=sent_message.content, embed=new_embed)
                    except Exception as e:
                        print(f"상인 만료 오류: {e}")
                    finally:
                        if signature in ACTIVE_BIOME_SIGNATURES:
                            del ACTIVE_BIOME_SIGNATURES[signature]

                bot.loop.create_task(expire_merchant())
            return
    
    if re.search(end_pattern, clean_text, re.IGNORECASE):
        tracking_key = (channel_id_str, webhook_author_name or (roblox_username.lower() if roblox_username else None))
        if tracking_key in ACTIVE_BIOME_MESSAGES:
            sent_msg = ACTIVE_BIOME_MESSAGES[tracking_key]
            try:
                if sent_msg.embeds:
                    old_embed = sent_msg.embeds[0]
                    old_desc = old_embed.description
                    
                    new_desc = re.sub(r"(\*\*감지 시간\*\*\s*:\s*<t:\d+:R>)(.*)", r"\1 (사라짐)", old_desc)
                    if "(사라짐)" not in new_desc:
                        new_desc = re.sub(r"\*\*감지 시간\*\*\s*:\s*.*", "**감지 시간** : (사라짐)", old_desc)
                    
                    new_embed = discord.Embed(title="", description=new_desc, color=old_embed.color)
                    await sent_msg.edit(content=sent_msg.content, embed=new_embed)
            except Exception as e:
                print(f"메시지 수정 오류: {e}")
            
            del ACTIVE_BIOME_MESSAGES[tracking_key]
        
        # 시그니처 정리
        keys_to_del = [k for k in ACTIVE_BIOME_SIGNATURES if k[0] == tracking_key_base]
        for k in keys_to_del:
            del ACTIVE_BIOME_SIGNATURES[k]
        return

    if not re.search(r"Biome\s+Started", clean_text, re.IGNORECASE):
        return

    biome_name = biome_match.group(1).strip().upper() if biome_match else "UNKNOWN"

    exclude_biomes = ["normal"]
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
    owner_display, user_private_url = get_user_link_info(roblox_username, webhook_author_name)

    embed_color = 0x00A2FF
    for key, color_val in BIOME_COLORS.items():
        if key.lower() == biome_lower:
            embed_color = color_val
            break

    msg_timestamp = int(message.created_at.timestamp())
    dynamic_time_str = f"<t:{msg_timestamp}:R>"

    embed_description = (
        f"# {biome_name}\n"
        f"**유저** : {owner_display}\n"
        f"**감지 시간** : {dynamic_time_str}\n"
        f"**서버 시간** : {session_duration}"
    )

    new_embed = discord.Embed(title="", description=embed_description, color=embed_color)
    view = BiomeControlView(user_private_url)

    target_channel = None
    if biome_lower in rare_group:
        cursor.execute("SELECT channel_id FROM rare_channel LIMIT 1")
        rare_row = cursor.fetchone()
        if rare_row: target_channel = bot.get_channel(int(rare_row[0]))
    elif biome_lower in event_group:
        cursor.execute("SELECT channel_id FROM event_channel LIMIT 1")
        event_row = cursor.fetchone()
        if event_row: target_channel = bot.get_channel(int(event_row[0]))
    else:
        cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
        output_row = cursor.fetchone()
        if output_row: target_channel = bot.get_channel(int(output_row[0]))

    if target_channel:
        sent_message = await target_channel.send(content=mention_text, embed=new_embed, view=view)
        tracking_key = webhook_author_name or (roblox_username.lower() if roblox_username else None)
        if tracking_key:
            ACTIVE_BIOME_MESSAGES[(channel_id_str, tracking_key)] = sent_message

@bot.event
async def on_message(message):
    try:
        await process_macro_message(message)
    except Exception as e:
        print(f"메시지 처리 오류: {e}")

@bot.event
async def on_message_edit(before, after):
    try:
        await process_macro_message(after)
    except Exception as e:
        print(f"메시지 수정 처리 오류: {e}")

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
