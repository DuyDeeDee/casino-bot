import asyncio
import json
import logging
import re
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from app.discord_bot.modules.economy import Economy

logger = logging.getLogger(__name__)


def parse_role_mention(text: str) -> Optional[int]:
    """Parses role mention or ID to get integer ID."""
    match = re.match(r"<@&?(\d+)>", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def parse_channel_mention(text: str) -> Optional[int]:
    """Parses channel mention or ID to get integer ID."""
    match = re.match(r"<#(\d+)>", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def parse_time(time_str: str) -> Optional[int]:
    """Parses a time string like '30m', '1h', '2d' and returns the duration in seconds."""
    match = re.match(r"^(\d+)([smhd])$", time_str.strip().lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 3600
    elif unit == 'd':
        return amount * 86400
    return None





class Giveaway(commands.Cog, name="Giveaway"):
    """Cog for managing Discord server giveaways."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.join_locks = {}
        self.pending_embed_updates = {}
        self.update_tasks = {}
        self.init_db()
        self.giveaway_check_loop.start()

    def cog_unload(self) -> None:
        self.giveaway_check_loop.cancel()
        for task in self.update_tasks.values():
            task.cancel()

    def init_db(self):
        """Initializes the SQLite database table for giveaways."""
        try:
            self.economy.cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    prize TEXT NOT NULL,
                    host_id INTEGER NOT NULL,
                    winner_count INTEGER NOT NULL DEFAULT 1,
                    ends_at INTEGER NOT NULL,
                    ended INTEGER NOT NULL DEFAULT 0, -- 0 = Active, 1 = Ended, 2 = Cancelled
                    required_roles TEXT,            -- JSON array of role IDs (Private mode)
                    participants TEXT NOT NULL,     -- JSON array of participant user IDs
                    winners TEXT NOT NULL           -- JSON array of winner user IDs
                )
            """)
            self.economy.conn.commit()

            # Check if bonus_roles column exists, if not, add it
            self.economy.cur.execute("PRAGMA table_info(giveaways)")
            columns = [col[1] for col in self.economy.cur.fetchall()]
            if 'bonus_roles' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN bonus_roles TEXT")
                self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to create giveaways table: {e}", exc_info=True)

    def save_giveaway(self, msg_id, guild_id, channel_id, prize, host_id, winner_count, ends_at, required_roles, bonus_roles):
        try:
            self.economy.cur.execute(
                """INSERT INTO giveaways (id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '{}', '[]')""",
                (msg_id, guild_id, channel_id, msg_id, prize, host_id, winner_count, ends_at, json.dumps(required_roles), json.dumps(bonus_roles))
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save giveaway: {e}", exc_info=True)

    def get_giveaway(self, msg_id):
        try:
            self.economy.cur.execute(
                """SELECT id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners 
                   FROM giveaways WHERE id = ?""", 
                (msg_id,)
            )
            row = self.economy.cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'guild_id': row[1],
                    'channel_id': row[2],
                    'message_id': row[3],
                    'prize': row[4],
                    'host_id': row[5],
                    'winner_count': row[6],
                    'ends_at': row[7],
                    'ended': row[8],
                    'required_roles': row[9],
                    'bonus_roles': row[10] or '{}',
                    'participants': row[11],
                    'winners': row[12]
                }
        except Exception as e:
            logger.error(f"Failed to get giveaway: {e}", exc_info=True)
        return None

    def update_participants(self, msg_id, participants):
        try:
            self.economy.cur.execute("UPDATE giveaways SET participants = ? WHERE id = ?", (json.dumps(participants), msg_id))
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update participants: {e}", exc_info=True)

    def update_winners(self, msg_id, winners):
        try:
            self.economy.cur.execute("UPDATE giveaways SET winners = ? WHERE id = ?", (json.dumps(winners), msg_id))
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update winners: {e}", exc_info=True)

    def mark_ended(self, msg_id, ended=1, winners=None):
        if winners is None:
            winners = []
        try:
            self.economy.cur.execute("UPDATE giveaways SET ended = ?, winners = ? WHERE id = ?", (ended, json.dumps(winners), msg_id))
            self.economy.conn.commit()
            self.join_locks.pop(msg_id, None)
        except Exception as e:
            logger.error(f"Failed to mark giveaway as ended: {e}", exc_info=True)

    def is_host_or_admin(self, ctx: commands.Context, giveaway) -> bool:
        if ctx.author.id == giveaway['host_id']:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        if ctx.author.id in self.bot.owner_ids:
            return True
        return False

    def get_env_bonus_roles(self) -> dict[int, int]:
        from app.config import config
        raw = config.bot.giveaway_bonus_roles
        if not raw:
            return {}
        
        bonus_map = {}
        parts = raw.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                subparts = part.split(":")
                try:
                    r_id = int(subparts[0].strip())
                    extra = int(subparts[1].strip())
                    bonus_map[r_id] = extra
                except ValueError:
                    pass
            else:
                try:
                    r_id = int(part)
                    bonus_map[r_id] = 1
                except ValueError:
                    pass
        return bonus_map

    def set_embed_host_thumbnail(self, embed: discord.Embed, host_id: int):
        host = self.bot.get_user(host_id)
        if not host:
            for guild in self.bot.guilds:
                member = guild.get_member(host_id)
                if member:
                    host = member
                    break
        if host and host.display_avatar:
            embed.set_thumbnail(url=host.display_avatar.url)

    def build_active_embed(self, giveaway, participants_count: int) -> discord.Embed:
        prize = giveaway['prize']
        host_id = giveaway['host_id']
        winner_count = giveaway['winner_count']
        ends_at = giveaway['ends_at']
        required_roles = json.loads(giveaway['required_roles'])
        bonus_roles_str = giveaway.get('bonus_roles', '{}')
        bonus_roles = json.loads(bonus_roles_str) if bonus_roles_str else {}

        embed = discord.Embed(title="<a:thanhgia:1526231085221023845> Giveaway Bắt Đầu <a:thanhgia:1526231085221023845>", color=discord.Color.purple())
        embed.description = f"## **{prize}**\n\n"
        embed.add_field(name="\u200b", value=f"<a:timden:1526230943478845450> *host:* <@{host_id}>  •  <:ss:1526230022787043348>*Win:* {winner_count}", inline=False)

        if required_roles:
            req_lines = [f"<@&{r_id}>" for r_id in required_roles]
            embed.add_field(name="<a:kcden:1526231212887380108> Giới hạn", value="\n".join(req_lines), inline=False)
        elif bonus_roles:
            bonus_lines = [f"<@&{r_id}>" for r_id in bonus_roles.keys()]
            embed.add_field(name="<a:kcden:1526231212887380108>*Boost Role*", value="\n".join(bonus_lines), inline=False)
        else:
            env_bonus = self.get_env_bonus_roles()
            if env_bonus:
                bonus_lines = [f"<@&{r_id}>" for r_id in env_bonus.keys()]
                embed.add_field(name="<a:kcden:1526231212887380108>*Boost Role*", value="\n".join(bonus_lines), inline=False)

        embed.add_field(name="\u200b", value=f"<:ss:1526230022787043348>*End:* <t:{ends_at}:R>", inline=False)
        embed.set_footer(text="Sylus Meow • Giveaway System")
        self.set_embed_host_thumbnail(embed, host_id)
        return embed

    async def update_giveaway_embed_msg(self, message: discord.Message, giveaway, participants_count: int):
        embed = self.build_active_embed(giveaway, participants_count)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Could not edit giveaway message {message.id}: {e}")

    def schedule_embed_update(self, message: discord.Message, giveaway, participants_count: int):
        message_id = message.id
        self.pending_embed_updates[message_id] = (message, giveaway, participants_count)
        if message_id in self.update_tasks:
            return
        
        loop = asyncio.get_running_loop()
        self.update_tasks[message_id] = loop.create_task(self.run_debounced_embed_update(message_id))

    async def run_debounced_embed_update(self, message_id: int):
        await asyncio.sleep(2.0)
        info = self.pending_embed_updates.pop(message_id, None)
        self.update_tasks.pop(message_id, None)
        if info:
            message, giveaway, count = info
            await self.update_giveaway_embed_msg(message, giveaway, count)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore if reaction added by the bot itself
        if payload.user_id == self.bot.user.id:
            return

        # Check if the emoji matches the custom emoji <:ghim:1526238405061640272>
        if not payload.emoji.is_custom_emoji() or payload.emoji.id != 1526238405061640272:
            return

        message_id = payload.message_id
        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = payload.member
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        # If member is a bot, ignore
        if member.bot:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.HTTPException:
            return

        # Lock per giveaway message ID to prevent race conditions during DB updates
        lock = self.join_locks.setdefault(message_id, asyncio.Lock())
        async with lock:
            # Re-fetch the giveaway within lock to get fresh DB state
            giveaway = self.get_giveaway(message_id)
            if not giveaway or giveaway['ended'] != 0:
                try:
                    await message.remove_reaction(payload.emoji, member)
                except discord.HTTPException:
                    pass
                return

            user_id = member.id
            try:
                participants = json.loads(giveaway['participants'])
            except Exception:
                participants = {}

            # Backward compatibility: Convert list to dict
            if isinstance(participants, list):
                participants = {str(uid): 1 for uid in participants}

            # Check if already joined (should be rare on reaction add unless cache desync)
            if str(user_id) in participants:
                return

            # Check required roles (Private mode)
            required_roles = json.loads(giveaway['required_roles'])
            if required_roles:
                has_role = False
                for r_id in required_roles:
                    if member.get_role(r_id) is not None:
                        has_role = True
                        break
                if not has_role:
                    try:
                        await message.remove_reaction(payload.emoji, member)
                    except discord.HTTPException:
                        pass
                    
                    roles_mentions = ", ".join(f"<@&{r_id}>" for r_id in required_roles)
                    try:
                        embed = discord.Embed(
                            title="❌ Tham gia Giveaway thất bại",
                            description=f"Bạn không thể tham gia giveaway **{giveaway['prize']}** vì không có role yêu cầu.\nVai trò yêu cầu: {roles_mentions}",
                            color=discord.Color.red()
                        )
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        pass
                    return

            # Calculate entries
            bonus_roles_str = giveaway.get('bonus_roles', '{}')
            bonus_roles = json.loads(bonus_roles_str) if bonus_roles_str else {}
            entries = 1
            if bonus_roles:
                for r_id_str, extra in bonus_roles.items():
                    r_id = int(r_id_str)
                    if member.get_role(r_id) is not None:
                        entries += extra
            else:
                env_bonus = self.get_env_bonus_roles()
                if env_bonus:
                    for r_id, extra in env_bonus.items():
                        if member.get_role(r_id) is not None:
                            entries += extra

            # Add user to participants dict
            participants[str(user_id)] = entries
            self.update_participants(message_id, participants)
            
            participants_count = len(participants)

        # Schedule the embed update (debounced, outside the lock!)
        self.schedule_embed_update(message, giveaway, participants_count)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        # Ignore if reaction removed by the bot itself
        if payload.user_id == self.bot.user.id:
            return

        # Check if the emoji matches the custom emoji <:ghim:1526238405061640272>
        if not payload.emoji.is_custom_emoji() or payload.emoji.id != 1526238405061640272:
            return

        message_id = payload.message_id
        giveaway = self.get_giveaway(message_id)
        if not giveaway or giveaway['ended'] != 0:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.HTTPException:
            return

        user_id = payload.user_id

        # Lock per giveaway message ID to prevent race conditions during DB updates
        lock = self.join_locks.setdefault(message_id, asyncio.Lock())
        async with lock:
            # Re-fetch giveaway
            giveaway = self.get_giveaway(message_id)
            if not giveaway or giveaway['ended'] != 0:
                return

            try:
                participants = json.loads(giveaway['participants'])
            except Exception:
                participants = {}

            if isinstance(participants, list):
                participants = {str(uid): 1 for uid in participants}

            if str(user_id) not in participants:
                return

            # Remove from dict
            participants.pop(str(user_id), None)
            self.update_participants(message_id, participants)
            
            participants_count = len(participants)

        # Schedule embed update
        self.schedule_embed_update(message, giveaway, participants_count)

    def parse_giveaway_args(self, args_str: str):
        """Parses arguments string to extract the prize description and flags."""
        flags = ["--role", "-role", "--bonus", "-bonus", "--channel", "-channel"]
        min_index = len(args_str)
        
        for flag in flags:
            idx = args_str.lower().find(flag)
            if idx != -1 and idx < min_index:
                min_index = idx
                
        prize = args_str[:min_index].strip()
        flags_part = args_str[min_index:].strip()
        
        required_roles = []
        bonus_roles = {}
        target_channel = None
        
        if flags_part:
            tokens = flags_part.split()
            i = 0
            while i < len(tokens):
                tok = tokens[i].lower()
                if tok in ["--role", "-role"]:
                    i += 1
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        role_id = parse_role_mention(tokens[i])
                        if role_id:
                            required_roles.append(role_id)
                        i += 1
                elif tok in ["--bonus", "-bonus"]:
                    i += 1
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        role_id = parse_role_mention(tokens[i])
                        if role_id:
                            if i + 1 < len(tokens) and tokens[i+1].isdigit():
                                bonus_roles[role_id] = int(tokens[i+1])
                                i += 2
                            else:
                                bonus_roles[role_id] = 1
                                i += 1
                        else:
                            i += 1
                elif tok in ["--channel", "-channel"]:
                    i += 1
                    if i < len(tokens):
                        target_channel = parse_channel_mention(tokens[i])
                        i += 1
                else:
                    i += 1
                    
        return prize, required_roles, bonus_roles, target_channel

    @commands.group(
        name="giveaway",
        aliases=["ga"],
        brief="Quản lý hệ thống giveaway",
        invoke_without_command=True
    )
    async def giveaway_group(
        self,
        ctx: commands.Context,
        time_str: str = None,
        winners_count: int = None,
        *,
        args_str: str = None
    ):
        if time_str is None or winners_count is None or args_str is None:
            await self.send_giveaway_help(ctx)
            return

        # Parse args_str
        prize, required_roles, bonus_roles, target_channel = self.parse_giveaway_args(args_str)

        # Delete command message immediately
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Check mutual exclusion of private mode and custom bonus roles
        if required_roles and bonus_roles:
            await ctx.send("❌ Bạn không thể cấu hình giới hạn role và cộng lượt cùng lúc trong một giveaway!", delete_after=10)
            return

        # Validate arguments
        duration_seconds = parse_time(time_str)
        if duration_seconds is None or duration_seconds <= 0:
            await ctx.send("❌ Định dạng thời gian không hợp lệ. Ví dụ: `30m`, `1h`, `2d`.", delete_after=10)
            return

        if winners_count <= 0:
            await ctx.send("❌ Số người thắng phải lớn hơn 0.", delete_after=10)
            return

        if not prize:
            await ctx.send("❌ Vui lòng nhập phần thưởng.", delete_after=10)
            return

        # Check target channel
        channel = ctx.channel
        if target_channel:
            channel = ctx.guild.get_channel(target_channel)
            if not channel:
                await ctx.send("❌ Không tìm thấy kênh được chỉ định.", delete_after=10)
                return

        # Calculate ends_at
        now = int(time.time())
        ends_at = now + duration_seconds

        # Create embed & view
        giveaway_temp = {
            'prize': prize,
            'host_id': ctx.author.id,
            'winner_count': winners_count,
            'ends_at': ends_at,
            'required_roles': json.dumps(required_roles),
            'bonus_roles': json.dumps(bonus_roles)
        }
        embed = self.build_active_embed(giveaway_temp, 0)

        try:
            msg = await channel.send(content="# <a:w1:1526231439425667093> Giveaway Illys Sylus <a:w2:1526231455422877798>", embed=embed)
            await msg.add_reaction("<:ghim:1526238405061640272>")
        except discord.Forbidden:
            await ctx.send(f"❌ Bot không có quyền gửi tin nhắn hoặc embed ở kênh {channel.mention}.", delete_after=10)
            return

        # Save to database
        self.save_giveaway(msg.id, ctx.guild.id, channel.id, prize, ctx.author.id, winners_count, ends_at, required_roles, bonus_roles)

    async def send_giveaway_help(self, ctx: commands.Context):
        prefix = ctx.prefix
        embed = discord.Embed(title="🎉 HƯỚNG DẪN SỬ DỤNG GIVEAWAY 🎉", color=discord.Color.purple())
        embed.description = (
            f"**1. Tạo giveaway:**\n"
            f"`{prefix}ga <thời_gian> <số_người_thắng> <phần_thưởng> [flags]`\n"
            f"👉 *Ví dụ:* `{prefix}ga 10m 1 100k` (Ga 10 phút, 1 người thắng, quà 100k)\n"
            f"👉 *Ví dụ (Giới hạn role):* `{prefix}ga 2h 2 Skin VIP --role @Donator @VIP`\n"
            f"👉 *Ví dụ (Chọn role cộng lượt):* `{prefix}ga 1d 1 Nitro --bonus @Booster 2 @VIP 1`\n"
            f"👉 *Ví dụ (Kênh khác):* `{prefix}ga 1d 1 Nitro --channel #giveaways`\n\n"
            f"**💡 Lưu ý:**\n"
            f"- Nếu không chỉ định `--bonus`, hệ thống sẽ tự động cộng thêm lượt tương ứng với vị trí của Role trong server cho giveaway công khai.\n"
            f"- Tự động xoá tin nhắn lệnh, chỉ giữ lại embed của bot.\n\n"
            f"**2. Quản lý giveaway:**\n"
            f"- Kết thúc sớm: `{prefix}ga ketthuc <id_tin_nhắn>`\n"
            f"- Reroll: `{prefix}ga quaylai <id_tin_nhắn> [số_lượng_quay_lại]`\n"
            f"- Huỷ: `{prefix}ga huy <id_tin_nhắn>`"
        )
        embed.set_footer(text="Sylus Meow • Giveaway System")
        await ctx.send(embed=embed)

    @giveaway_group.command(name="ketthuc", aliases=["end"], brief="Kết thúc sớm một giveaway đang chạy")
    async def giveaway_end(self, ctx: commands.Context, message_id: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
            return

        if giveaway['ended'] != 0:
            await ctx.send("❌ Giveaway này đã kết thúc hoặc đã bị huỷ trước đó.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền kết thúc giveaway này.", delete_after=10)
            return

        await self.end_giveaway(message_id)

    @giveaway_group.command(name="huy", aliases=["cancel"], brief="Huỷ một giveaway đang chạy")
    async def giveaway_cancel(self, ctx: commands.Context, message_id: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
            return

        if giveaway['ended'] != 0:
            await ctx.send("❌ Giveaway này đã kết thúc hoặc đã bị huỷ trước đó.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền huỷ giveaway này.", delete_after=10)
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            message = None

        self.mark_ended(message_id, ended=2) # 2 = Cancelled

        if message:
            embed = discord.Embed(title="🎉 GIVEAWAY ĐÃ BỊ HUỶ 🎉", color=discord.Color.purple())
            embed.description = f"### {giveaway['prize']}\n\n🛑 Giveaway này đã bị huỷ bởi Host."
            embed.add_field(name="Tổ chức bởi", value=f"<@{giveaway['host_id']}>", inline=True)
            embed.set_footer(text="Sylus Meow • Giveaway System")
            await message.edit(embed=embed, view=None)

        await channel.send(f"🛑 Giveaway giải **{giveaway['prize']}** đã bị huỷ bởi <@{ctx.author.id}>.")

    @giveaway_group.command(name="quaylai", aliases=["reroll"], brief="Quay lại người thắng mới cho giveaway đã kết thúc")
    async def giveaway_reroll(self, ctx: commands.Context, message_id: int, count: int = 1):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
            return

        if giveaway['ended'] != 1:
            await ctx.send("❌ Chỉ có thể quay lại (reroll) cho giveaway đã kết thúc thành công.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền quay lại giveaway này.", delete_after=10)
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("❌ Không tìm thấy tin nhắn giveaway gốc.", delete_after=10)
            return
        except Exception as e:
            await ctx.send(f"❌ Lỗi khi lấy tin nhắn: {e}", delete_after=10)
            return

        try:
            participants = json.loads(giveaway['participants'])
        except Exception:
            participants = {}

        # Backward compatibility: Convert list to dict
        if isinstance(participants, list):
            participants = {str(uid): 1 for uid in participants}

        old_winners = json.loads(giveaway['winners'])
        prize = giveaway['prize']
        host_id = giveaway['host_id']

        # Build ticket pool from weights stored in participants dict
        ticket_pool = []
        for user_id_str, entries in participants.items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if user_id in old_winners:
                continue
            for _ in range(entries):
                ticket_pool.append(user_id)

        import random
        random.shuffle(ticket_pool)

        # Draw new winners
        new_winners = []
        failed_users = set()
        while len(new_winners) < count and len(ticket_pool) > 0:
            candidate = ticket_pool.pop()
            if candidate in new_winners or candidate in failed_users:
                continue
            
            member = guild.get_member(candidate)
            if not member:
                try:
                    member = await guild.fetch_member(candidate)
                except discord.NotFound:
                    failed_users.add(candidate)
                    continue
                except Exception:
                    failed_users.add(candidate)
                    continue
            new_winners.append(candidate)

        if not new_winners:
            await ctx.send("❌ Không còn người tham gia hợp lệ nào khác để quay lại (reroll).", delete_after=10)
            return

        # Save to DB
        self.update_winners(message_id, new_winners)

        new_winners_mentions = ", ".join(f"<@{w_id}>" for w_id in new_winners)

        # Edit embed
        embed = discord.Embed(title="🎉 GIVEAWAY ĐÃ QUAY LẠI KẾT QUẢ 🎉", color=discord.Color.purple())
        embed.description = f"### {prize}\n\n"
        embed.add_field(name="\u200b", value=f"<a:timden:1526230943478845450> *host:* <@{host_id}>  •  <:ss:1526230022787043348>*Win:* {len(new_winners)}", inline=False)
        embed.add_field(name="<a:key:1526234974150459593>*Result:*", value=new_winners_mentions, inline=False)
        embed.set_footer(text="*Sylus Meow • Giveaway System*")
        self.set_embed_host_thumbnail(embed, host_id)
        await message.edit(embed=embed, view=None)

        # Send congrats
        await channel.send(f"🎉 **Reroll:** Chúc mừng {new_winners_mentions} đã thắng giải **{prize}**! Liên hệ <@{host_id}> để nhận thưởng.")

    async def end_giveaway(self, message_id: int):
        giveaway = self.get_giveaway(message_id)
        if not giveaway or giveaway['ended'] != 0:
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            self.mark_ended(message_id, ended=1)
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            self.mark_ended(message_id, ended=1)
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            self.mark_ended(message_id, ended=1)
            return
        except Exception:
            return

        try:
            participants = json.loads(giveaway['participants'])
        except Exception:
            participants = {}

        # Backward compatibility: Convert list to dict
        if isinstance(participants, list):
            participants = {str(uid): 1 for uid in participants}

        winner_count = giveaway['winner_count']
        prize = giveaway['prize']
        host_id = giveaway['host_id']
        required_roles = json.loads(giveaway['required_roles'])

        if not participants:
            # No one participated
            self.mark_ended(message_id, ended=1)
            embed = discord.Embed(title="# <a:thanhgia:1526231085221023845>**Giveaway Kết Thúc**<a:thanhgia:1526231085221023845>", color=discord.Color.purple())
            embed.description = f"### {prize}\n\n Không có ai tham gia giveaway này."
            embed.add_field(name="\u200b", value=f"<a:timden:1526230943478845450> *host:* <@{host_id}>", inline=False)
            embed.set_footer(text="*Sylus Meow • Giveaway System*")
            self.set_embed_host_thumbnail(embed, host_id)
            await message.edit(embed=embed, view=None)
            await channel.send(f" Không có ai tham gia giveaway **{prize}**.")
            return

        # Build the ticket pool
        ticket_pool = []
        for user_id_str, entries in participants.items():
            try:
                user_id = int(user_id_str)
                for _ in range(entries):
                    ticket_pool.append(user_id)
            except ValueError:
                continue

        import random
        random.shuffle(ticket_pool)

        # Draw winners and verify they are still in server
        winners = []
        failed_users = set()
        while len(winners) < winner_count and len(ticket_pool) > 0:
            candidate = ticket_pool.pop()
            if candidate in winners or candidate in failed_users:
                continue

            member = guild.get_member(candidate)
            if not member:
                try:
                    member = await guild.fetch_member(candidate)
                except discord.NotFound:
                    failed_users.add(candidate)
                    continue
                except Exception:
                    failed_users.add(candidate)
                    continue
            winners.append(candidate)

        if not winners:
            self.mark_ended(message_id, ended=1)
            embed = discord.Embed(title="# <a:thanhgia:1526231085221023845>**Giveaway Kết Thúc**<a:thanhgia:1526231085221023845>", color=discord.Color.purple())
            embed.description = f"### {prize}\n\n Không có người tham gia hợp lệ (người tham gia đã rời server)."
            embed.add_field(name="\u200b", value=f"<a:timden:1526230943478845450> *host:* <@{host_id}>", inline=False)
            embed.set_footer(text="*Sylus Meow • Giveaway System*")
            self.set_embed_host_thumbnail(embed, host_id)
            await message.edit(embed=embed, view=None)
            await channel.send(f" Không có ai thắng giveaway **{prize}** vì tất cả người tham gia đã rời server.")
            return

        # Save to DB
        self.mark_ended(message_id, ended=1, winners=winners)

        # Format winner mentions
        winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)

        # Edit embed
        embed = discord.Embed(title=" <a:thanhgia:1526231085221023845>**Giveaway Kết Thúc**<a:thanhgia:1526231085221023845>", color=discord.Color.purple())
        embed.description = f"### {prize}\n\n"
        embed.add_field(name="\u200b", value=f"<a:timden:1526230943478845450> *host:* <@{host_id}>  •  <:ss:1526230022787043348>*Win:* {winner_count}", inline=False)
        embed.add_field(name="<a:key:1526234974150459593>*Result:*", value=winners_mentions, inline=False)
        embed.set_footer(text="*Sylus Meow • Giveaway System*")
        self.set_embed_host_thumbnail(embed, host_id)
        await message.edit(embed=embed, view=None)

        # Send congratulation message
        await channel.send(f" <a:wing:1526230985987981393>*Chúc mừng {winners_mentions} đã thắng giải **{prize}**<a:key:1526234974150459593> Liên hệ <@{host_id}> để nhận thưởng.*")

    @commands.command(name="sync_giveaway", hidden=True)
    @commands.is_owner()
    async def sync_giveaway(self, ctx: commands.Context):
        """Owner-only command to sync command tree if needed."""
        await self.bot.tree.sync()
        await ctx.send("Synced giveaway slash/hybrid commands!")

    @tasks.loop(seconds=5)
    async def giveaway_check_loop(self):
        try:
            now = int(time.time())
            self.economy.cur.execute("SELECT id FROM giveaways WHERE ended = 0 AND ends_at <= ?", (now,))
            rows = self.economy.cur.fetchall()
            for row in rows:
                msg_id = row[0]
                await self.end_giveaway(msg_id)
        except Exception as e:
            logger.error(f"Error in giveaway_check_loop: {e}", exc_info=True)

    @giveaway_check_loop.before_loop
    async def before_giveaway_check_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
