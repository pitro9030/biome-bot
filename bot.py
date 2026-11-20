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

# 💡 활성화된 바이옴 알림 메시지들을 추적하기 위한 딕셔너리 (Ended 감지용)
# 키: (채널ID, 로블록스닉네임), 값: discord.Message 객체
ACTIVE_BIOME_MESSAGES = {}

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
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **최종 매크로 알림 출력방**으로 설정되었습니다!")

# 1. 링크 등록 시 명령어 입력자의 디스코드 ID와 로블록스 닉네임을 함께 저장
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

    # 로블록스 닉네임 먼저 추출
    account_match = re.search(r"Account[:\s]+\*\*([^*]+)\*\*", full_text)
    if not account_match:
        account_match = re.search(r"Account[:\s]+([^\n\r]+)", full_text)
    
    roblox_username = account_match.group(1).strip() if account_match else None

    # 출력방 가져오기
    cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
    output_row = cursor.fetchone()
    if not output_row:
        return
    output_channel_id = int(output_row[0])
    output_channel = bot.get_channel(output_channel_id)
    if not output_channel:
        return

    # -------------------------------------------------------------
    # Case A: Biome Ended 감지 시 -> 기존 메시지 수정 ("방금 전 - (사라짐)")
    # -------------------------------------------------------------
    if "Ended" in full_text:
        tracking_key = (channel_id_str, roblox_username)
        if tracking_key in ACTIVE_BIOME_MESSAGES:
            sent_msg = ACTIVE_BIOME_MESSAGES[tracking_key]
            try:
                # 기존에 보냈던 임베드 가져와서 내용 수정
                if sent_msg.embeds:
                    old_embed = sent_msg.embeds[0]
                    new_embed = discord.Embed.from_dict(old_embed.to_dict())
                    
                    # 필드 중 '바이옴 감지 시간'을 찾아 수정
                    for i, field in enumerate(new_embed.fields):
                        if field.name == "바이옴 감지 시간":
                            new_embed.set_field_at(i, name="바이옴 감지 시간", value="방금 전 - (사라짐)", inline=True)

                    # 버튼(뷰)은 그대로 유지하면서 메시지 내용 수정
                    await sent_msg.edit(embed=new_embed)
            except Exception as e:
                print(f"메시지 수정 중 오류 발생: {e}")
            
            # 처리 완료 후 추적 목록에서 제거
            del ACTIVE_BIOME_MESSAGES[tracking_key]
        return

    # -------------------------------------------------------------
    # Case B: Biome Started 감지 시 -> 새로운 알림 전송
    # -------------------------------------------------------------
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

    # DB에서 로블록스 닉네임과 매칭되는 디스코드 유저 ID 조회
    user_private_url = "https://discord.gg/기본링크"
    owner_display = f"**{roblox_username if roblox_username else '알 수 없음'}**"

    if roblox_username:
        cursor.execute("SELECT discord_id, server_url FROM user_links WHERE roblox_name = ?", (roblox_username,))
        result = cursor.fetchone()
        if result:
            discord_id, user_private_url = result[0], result[1]
            if discord_id:
                # 멘션 형식으로 변환 (<@디스코드ID>)
                owner_display = f"<@{discord_id}>"

    new_embed = discord.Embed(
        title=f"Biome Started - {biome_name}",
        color=discord.Color.from_rgb(0, 162, 255)
    )
    new_embed.add_field(name="서버 주인", value=owner_display, inline=False)
    new_embed.add_field(name="바이옴 감지 시간", value="방금 전", inline=True)

    class CustomJoinView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.add_item(discord.ui.Button(
                label="Join Server",
                url=user_private_url,
                style=discord.ButtonStyle.link
            ))

    sent_message = await output_channel.send(embed=new_embed, view=CustomJoinView())

    # 나중에 Ended가 올 때 수정할 수 있도록 메시지 객체 저장
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
