import discord
from discord.ext import commands
import sqlite3
import re
import os

# 디스코드 인텐트 설정 (메시지 내용 읽기 필수)
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# SQLite 데이터베이스 연결 (파일 기반)
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

# 테이블 자동 생성 (최초 실행 시)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_channel (
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

# 1. 원본 감지 채널 등록 명령어 (관리자 전용)
@bot.command()
@commands.has_permissions(administrator=True)
async def 채널등록(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("DELETE FROM source_channel")
    cursor.execute("INSERT INTO source_channel (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 매크로 감지 원본 채널로 등록되었습니다!")

# 2. 비공개 서버 링크 등록 명령어 (누구나 사용 가능)
# 사용법: !링크등록 [로블록스닉네임] [비공개서버링크]
@bot.command()
async def 링크등록(ctx, roblox_name: str, url: str):
    discord_id = ctx.author.id
    
    # 이미 등록된 유저라면 정보 업데이트, 아니면 새로 추가
    cursor.execute("SELECT * FROM user_links WHERE discord_id = ?", (discord_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE user_links SET roblox_name = ?, server_url = ? WHERE discord_id = ?", (roblox_name, url, discord_id))
    else:
        cursor.execute("INSERT INTO user_links (discord_id, roblox_name, server_url) VALUES (?, ?, ?)", (discord_id, roblox_name, url))
    conn.commit()
    
    await ctx.send(f"✅ **{roblox_name}**님의 비공개 서버 링크가 성공적으로 등록되었습니다!")

# 3. 메시지 감지 및 바이옴 처리 이벤트
@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무한 루프 방지를 위해 무시
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    # 원본 채널 ID 조회
    cursor.execute("SELECT channel_id FROM source_channel LIMIT 1")
    row = cursor.fetchone()
    source_channel_id = int(row[0]) if row else None

    # 원본 채널일 경우 처리 (일반 메시지 & 임베드 통합 스캔)
    if source_channel_id and message.channel.id == source_channel_id:
        
        # 임베드 내용과 일반 텍스트(message.content)를 모두 합쳐서 분석 텍스트 생성
        embed_texts = []
        for embed in message.embeds:
            t = embed.title if embed.title else ""
            d = embed.description if embed.description else ""
            f = "".join([f"\n{field.name}: {field.value}" for field in embed.fields])
            embed_texts.append(f"{t}\n{d}\n{f}")
        
        full_text = f"{message.content}\n" + "\n".join(embed_texts)

        # Ended 알림은 완전히 무시하고, Started 알림만 허용
        if "Ended" in full_text or "Started" not in full_text:
            await bot.process_commands(message)
            return

        # 바이옴 이름 추출 ('Biome Started - [바이옴이름]')
        biome_name = "알 수 없는 바이옴"
        if "Biome Started -" in full_text:
            biome_name = full_text.split("Biome Started -")[-1].split("\n")[0].strip()

        # 계정 이름(로블록스 닉네임) 추출 ('Account: 닉네임')
        account_match = re.search(r"Account[:\s]+\*\*([^*]+)\*\*", full_text)
        if not account_match:
            account_match = re.search(r"Account[:\s]+([^\n]+)", full_text)
        
        roblox_username = account_match.group(1).strip() if account_match else None

        # 데이터베이스에서 해당 유저의 링크 조회 (없으면 기본 링크)
        user_private_url = "https://discord.gg/기본링크"
        if roblox_username:
            cursor.execute("SELECT server_url FROM user_links WHERE roblox_name = ?", (roblox_username,))
            result = cursor.fetchone()
            if result:
                user_private_url = result[0]

        # 새로운 임베드 생성 (Started 감지 시에만 작동)
        new_embed = discord.Embed(
            title=f"🌲 바이옴 시작: {biome_name}",
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

        # 감지된 채널에 결과 전송
        await message.channel.send(embed=new_embed, view=CustomJoinView())

    # 디스코드 명령어(!채널등록, !링크등록 등)가 정상 작동하도록 처리
    await bot.process_commands(message)

# 봇 실행 (레일웨이 환경변수에서 토큰 가져오기)
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
