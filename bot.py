import os
import discord
from discord.ext import commands
import sqlite3

# 1. 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 2. 데이터베이스 설정 (유저 링크 + 감지할 원본 채널 ID 저장용 테이블 생성)
conn = sqlite3.connect("user_servers.db")
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_links (
        discord_id INTEGER PRIMARY KEY,
        server_url TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
''')
conn.commit()

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (봇이 정상 작동 중입니다)")

# 3. 사용자가 자신의 서버 링크를 등록하는 명령어 (예: !링크등록 https://discord.gg/...)
@bot.command(name="링크등록")
async def register_link(ctx, server_url: str):
    discord_id = ctx.author.id
    cursor.execute("REPLACE INTO user_links (discord_id, server_url) VALUES (?, ?)", (discord_id, server_url))
    conn.commit()
    await ctx.send(f"✅ 성공적으로 연동되었습니다, {ctx.author.mention}님! 이제 감지된 알림에 회원님의 서버 링크가 연결됩니다.")

# 4. [신규] 매크로 알림이 올라오는 방에서 치면 그 방이 자동으로 원본 채널로 등록되는 명령어
@bot.command(name="채널등록")
@commands.has_permissions(administrator=True) # 관리자만 사용 가능하게 설정
async def set_source_channel(ctx):
    channel_id = str(ctx.channel.id)
    cursor.execute("REPLACE INTO config (key, value) VALUES ('source_channel_id', ?)", (channel_id,))
    conn.commit()
    await ctx.send(f"✅ 이 채널({ctx.channel.mention})이 바이옴 매크로 감지 원본 채널로 자동 등록되었습니다!")

# 결과를 보낼 타겟 채널 ID
TARGET_CHANNEL_ID = 1573193709527375942  # 예쁘게 가공해서 보낼 최종 채널 ID

# 5. 메시지 감지 및 재가공 전송 로직
@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return

    # 데이터베이스에서 등록된 원본 채널 ID 가져오기
    cursor.execute("SELECT value FROM config WHERE key = 'source_channel_id'")
    row = cursor.fetchone()
    source_channel_id = int(row[0]) if row else None

    # 등록된 원본 채널이 존재하고, 그 채널에서 올라온 메시지이며, 임베드가 포함된 경우
    if source_channel_id and message.channel.id == source_channel_id and message.embeds:
        embed = message.embeds[0]
        
        # 원본 제목에서 바이옴 이름 추출
        original_title = embed.title if embed.title else ""
        if "-" in original_title:
            biome_name = original_title.split("-")[-1].strip()
        else:
            biome_name = original_title

        matched_user_id = message.author.id 
        
        # 데이터베이스에서 해당 유저가 등록한 프라이빗 서버 링크 조회
        cursor.execute("SELECT server_url FROM user_links WHERE discord_id = ?", (matched_user_id,))
        result = cursor.fetchone()
        
        user_private_url = result[0] if result else "https://discord.gg/기본링크"

        # 한국어로 변경된 새로운 임베드 생성
        new_embed = discord.Embed(
            title=f"🌲 바이옴: {biome_name}",
            color=discord.Color.from_rgb(0, 162, 255)
        )
        new_embed.add_field(name="서버 주인", value=f"<@{matched_user_id}>", inline=False)
        new_embed.add_field(name="바이옴 감지 시간", value="방금 전", inline=True)
        
        # 유저 고유의 Join 버튼 생성 클래스
        class CustomJoinView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(discord.ui.Button(
                    label="Join Server",
                    style=discord.ButtonStyle.link,
                    url=user_private_url
                ))

        # 최종 목적지 채널로 임베드와 버튼 전송
        target_channel = bot.get_channel(TARGET_CHANNEL_ID)
        if target_channel:
            # @가 포함된 올바른 역할 멘션 형식
            role_mention = "<@&1569903836867596419>" 
            
            await target_channel.send(
                content=role_mention, 
                embed=new_embed, 
                view=CustomJoinView()
            )

    # 💡 on_message 함수 내부에 알맞게 들여쓰기된 명령어 프로세서
    await bot.process_commands(message)

# 6. 봇 실행 토큰 입력 (환경 변수 사용으로 보안 경고 해결)
bot.run(os.environ.get("DISCORD_TOKEN"))
