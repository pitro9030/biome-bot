import discord
from discord.ext import commands
import sqlite3
import re
import os

# 디스코드 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# SQLite 데이터베이스 연결
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

# 테이블 자동 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_channels (
        channel_id TEXT UNIQUE
    )
""")
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

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (ID: {bot.user.id})")
    print("----------------------------------------")

# 1. 감지할 원본 채널들 등록 (1r, 2r, 3r 등 여러 개 가능)
@bot.command()
@commands.has_permissions(administrator=True)
async def 채널등록(ctx):
    channel_id = str(ctx.channel.id)
    try:
        cursor.execute("INSERT INTO source_channels (channel_id) VALUES (?)", (channel_id,))
        conn.commit()
        await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **매크로 감지 채널**로 추가되었습니다!")
    except sqlite3.IntegrityError:
        await ctx.send(f"⚠️ 이미 감지 채널로 등록되어 있는 방입니다!")

# 2. 최종 출력방 등록 (단 하나의 방)
@bot.command()
@commands.has_permissions(administrator=True)
async def 출력방등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM output_channel")
    cursor.execute("INSERT INTO output_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 **최종 매크로 알림 출력방**으로 설정되었습니다!")

# 3. 비공개 서버 링크 등록
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

# 4. 실시간 메시지 자동 감지 및 정확한 바이옴 추출 이벤트
@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무한 루프 방지를 위해 무시
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    # 등록된 감지 채널 목록 불러오기
    cursor.execute("SELECT channel_id FROM source_channels")
    source_rows = cursor.fetchall()
    source_channel_ids = [row[0] for row in source_rows]

    # 등록된 소스 채널 중 한 곳에서 메시지가 올라온 경우
    if source_channel_ids and str(message.channel.id) in source_channel_ids:
        
        # 메시지 내용, 임베드 타이틀, 설명, 필드, URL을 전부 텍스트로 결합하여 분석 준비
        embed_texts = []
        for embed in message.embeds:
            t = embed.title if embed.title else ""
            d = embed.description if embed.description else ""
            f = "".join([f"\n{field.name}: {field.value}" for field in embed.fields])
            u = embed.url if embed.url else ""
            embed_texts.append(f"{t}\n{d}\n{f}\n{u}")
        
        full_text = f"{message.content}\n" + "\n".join(embed_texts)

        # Ended 알림은 무조건 차단, 'Started' 키워드가 없으면 무시
        if "Ended" in full_text or "Started" not in full_text:
            await bot.process_commands(message)
            return

        # 🔍 [핵심 수정] 'Biome Started - [바이옴명]' 문구 뒤의 실제 바이옴 이름만 정확하게 정규식으로 추출
        biome_name = None
        match = re.search(r"Biome\s+Started\s*-\s*([^\n\r]+)", full_text, re.IGNORECASE)
        if match:
            biome_name = match.group(1).strip()
        else:
            # 예비 분할 방식
            if "Biome Started -" in full_text:
                parts = full_text.split("Biome Started -")
                if len(parts) > 1:
                    biome_name = parts[1].split("\n")[0].strip()

        if not biome_name:
            biome_name = "Unknown"

        # 계정 이름(로블록스 닉네임) 추출 ('Account: 닉네임')
        account_match = re.search(r"Account[:\s]+\*\*([^*]+)\*\*", full_text)
        if not account_match:
            account_match = re.search(r"Account[:\s]+([^\n\r]+)", full_text)
        
        roblox_username = account_match.group(1).strip() if account_match else None

        # 데이터베이스에서 해당 유저의 비공개 서버 링크 조회 (없으면 기본 안내 링크)
        user_private_url = "https://discord.gg/기본링크"
        if roblox_username:
            cursor.execute("SELECT server_url FROM user_links WHERE roblox_name = ?", (roblox_username,))
            result = cursor.fetchone()
            if result:
                user_private_url = result[0]

        # 🌲 원하시는 대로 정확히 "Biome Started - [바이옴이름]" 형태로 타이틀 생성
        new_embed = discord.Embed(
            title=f"Biome Started - {biome_name}",
            color=discord.Color.from_rgb(0, 162, 255)
        )
        new_embed.add_field(name="서버 주인", value=f"**{roblox_username if roblox_username else '알 수 없음'}**", inline=False)
        new_embed.add_field(name="바이옴 감지 시간", value="방금 전", inline=True)

        # 유저 고유의 Join 버튼 클래스
        class CustomJoinView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(discord.ui.Button(
                    label="Join Server",
                    url=user_private_url,
                    style=discord.ButtonStyle.link
                ))

        # 설정된 단 하나의 출력방(test)으로 자동 전송
        cursor.execute("SELECT channel_id FROM output_channel LIMIT 1")
        output_row = cursor.fetchone()
        
        if output_row:
            output_channel_id = int(output_row[0])
            output_channel = bot.get_channel(output_channel_id)
            if output_channel:
                await output_channel.send(embed=new_embed, view=CustomJoinView())

    # 명령어 처리 기능 유지
    await bot.process_commands(message)

# 봇 실행
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
