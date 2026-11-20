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

cursor.execute("""
    CREATE TABLE IF NOT EXISTS output_channel (
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

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (ID: {bot.user.id})")
    print("----------------------------------------")

@bot.command()
@commands.has_permissions(administrator=True)
async def 채널등록(ctx):
    channel_id = str(ctx.channel.id)
    SOURCE_CHANNELS.add(channel_id)
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **매크로 감지 채널**로 즉시 등록되었습니다! (현재 감지 중인 채널 수: {len(SOURCE_CHANNELS)}개)")

@bot.command()
@commands.has_permissions(administrator=True)
async def 출력방등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM output_channel")
    cursor.execute("INSERT INTO output_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **최종 매크로 알림 출력방**으로 설정되었습니다!")

@bot.command()
async def 링크등록(ctx, roblox_name: str, url: str):
    discord_id = ctx.author.id
    cursor.execute("SELECT * FROM user_links WHERE discord_id = ?", (discord_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE user_links SET roblox_name = ?, server_url = ? WHERE discord_id = ?", (roblox_name, url, discord_id))
    else:
        cursor.execute("INSERT INTO user_links (discord_id, roblox_name, server_url) VALUES (?, ?, ?)", (discord_id, roblox_name, url))
    conn.commit()
    await ctx.send(f"✅ **{roblox_name}**님의 비공개 서버 링크가 성공적으로 등록되었습니다!")

# 🔍 공통 메시지 처리 함수 (웹훅 및 일반 메시지 모두 대응)
async def process_macro_message(message):
    if message.author == bot.user:
        return

    channel_id_str = str(message.channel.id)
    if channel_id_str not in SOURCE_CHANNELS:
        return

    # 텍스트와 임베드 내용 강제 결합
    embed_texts = []
    for embed in message.embeds:
        # 딕셔너리 형태로 안전하게 변환하여 모든 데이터 추출
        data = embed.to_dict()
        t = data.get("title", "")
        d = data.get("description", "")
        fields = data.get("fields", [])
        f = "".join([f"\n{f.get('name', '')}: {f.get('value', '')}" for f in fields])
        u = data.get("url", "")
        embed_texts.append(f"{t}\n{d}\n{f}\n{u}")
    
    full_text = f"{message.content}\n" + "\n".join(embed_texts)

    # 디버깅을 위해 콘솔에 수신된 텍스트 출력 (레일웨이 로그에서 확인 가능)
    print(f"[수신된 메시지 감지] 채널 ID: {channel_id_str} | 내용 일부: {full_text[:100]}...")

    if "Ended" in full_text or "Started" not in full_text:
        return

    # 바이옴 이름 추출
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

    # 로블록스 닉네임 추출
    account_match = re.search(r"Account[:\s]+\*\*([^*]+)\*\*", full_text)
    if not account_match:
        account_match = re.search(r"Account[:\s]+([^\n\r]+)", full_text)
    
    roblox_username = account_match.group(1).strip() if account_match else None

    user_private_url = "https://discord.gg/기본링크"
    if roblox_username:
        cursor.execute("SELECT server_url FROM user_links WHERE roblox_name = ?", (roblox_username,))
        result = cursor.fetchone()
        if result:
            user_private_url = result[0]

    new_embed = discord.Embed(
        title=f"Biome Started - {biome_name}",
        color=discord.Color.from_rgb(0, 162, 255)
    )
    new_embed.add_field(name="서버 주인", value=f"**{roblox_username if roblox_username else '알 수 없음'}**", inline=False)
    new_embed.add_field(name="바이옴 감지 시간", value="방금 전", inline=True)

    class CustomJoinView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.add_item(discord.ui.Button(
                label="Join Server",
                url=user_private_url,
                style=discord.ButtonStyle.link
            ))

    cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
    output_row = cursor.fetchone()
    
    if output_row:
        output_channel_id = int(output_row[0])
        output_channel = bot.get_channel(output_channel_id)
        if output_channel:
            await output_channel.send(embed=new_embed, view=CustomJoinView())

@bot.event
async def on_message(message):
    await process_macro_message(message)
    await bot.process_commands(message)

# 일부 웹훅은 메시지가 생성된 직후 임베드가 완성되거나 수정될 수 있으므로 수정 이벤트도 함께 감지
@bot.event
async def on_message_edit(before, after):
    await process_macro_message(after)

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
