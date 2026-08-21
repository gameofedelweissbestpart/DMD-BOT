import discord
from discord.ext import commands, tasks
import json, os, re, asyncio, random
# เพิ่ม timezone ในการนำเข้าข้อมูล datetime
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

# --- 1. การจัดการข้อมูลแบบแยกไฟล์ (Multi-guild) ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_DIR = '/app/data/'
LONG_SEP = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

# ฟังก์ชันสร้าง Path ไฟล์แยกตาม ID เซิร์ฟเวอร์
def get_path(guild_id, suffix):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    return os.path.join(DATA_DIR, f"{guild_id}_{suffix}.json")

# ฟังก์ชันโหลดข้อมูลแยกตาม Guild
def load_data(guild_id, suffix, default=[]):
    path = get_path(guild_id, suffix)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return default
    return default

# ฟังก์ชันบันทึกข้อมูลแยกตาม Guild
def save_data(guild_id, suffix, data):
    path = get_path(guild_id, suffix)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# 🟢 [แก้ไขจุดที่ 1] เปลี่ยนการดึงเวลาให้อิงมาตรฐาน UTC+7 ป้องกันเวลา Server เพี้ยน
def get_thai_time():
    return datetime.now(timezone.utc) + timedelta(hours=7)

def validate_date(d_str):
    if not re.match(r"^\d{2}/\d{2}/\d{4}$", d_str):
        return False
    try:
        dt = datetime.strptime(d_str, "%d/%m/%Y")
        # กฎข้อที่ 1: บังคับ ค.ศ. (ปีต้องไม่เกิน 2100 เพื่อป้องกันการกรอก พ.ศ. 25xx)
        if dt.year > 2500:
            return False
        return True
    except:
        return False

# --- รายการประเภทการลา (ตัวแปรกลาง) ---
LEAVE_CATEGORIES = [
    "ลาพีคไทม์ (ลาทุกกิจกรรม)",
    "ลาแอร์ดรอป 21:00",
    "ลาอีเธอร์ยักษ์ 21:30",
    "ลาสกายฟอล 22:00",
    "ลาอีเธอร์ยักษ์ 22:30",
    "ลาสกายฟอล 23:00",
    "ลาแอร์ดรอป 00:00",
    "ลาซ้อม",
    "ลาอื่นๆ (ระบุในเหตุผล)"
]

# --- ฟังก์ชันแปลงและย่อชื่อประเภทการลา ---
def format_categories(cat_input):
    if isinstance(cat_input, str):
        cats = [c.strip() for c in cat_input.split(",") if c.strip()]
    elif isinstance(cat_input, list):
        cats = cat_input
    else:
        cats = ["ทั่วไป"]

    if not cats:
        return "ทั่วไป"

    if "ลาพีคไทม์ (ลาทุกกิจกรรม)" in cats:
        return "`ลาพีคไทม์ (ลาทุกกิจกรรม)`"

    short_map = {
        "ลาแอร์ดรอป 21:00": "แอร์ดรอป 21:00",
        "ลาอีเธอร์ยักษ์ 21:30": "อีเธอร์ 21:30",
        "ลาสกายฟอล 22:00": "สกายฟอล 22:00",
        "ลาอีเธอร์ยักษ์ 22:30": "อีเธอร์ 22:30",
        "ลาสกายฟอล 23:00": "สกายฟอล 23:00",
        "ลาแอร์ดรอป 00:00": "แอร์ดรอป 00:00",
        "ลาอื่นๆ (ระบุในเหตุผล)": "อื่นๆ (ระบุในเหตุผล)"
    }

    if len(cats) > 1:
        formatted = [f"`{short_map.get(c, c)}`" for c in cats]
        return ", ".join(formatted)
    else:
        return f"`{cats[0]}`"

# =====================================================================
# --- ⚔️ ฟังก์ชันระบบอัปเดตเลเวลอาวุธ (WEAPON SYSTEM HELPERS) ---
# =====================================================================

# 🟢 รายชื่อ Role ID ที่อนุญาตให้จัดการระบบอาวุธได้
WEAPON_ADMIN_ROLES = [1456220003195158568, 1469408762736676874, 1467435785945874443, 1515051953103568917]

# 🟢 ฟังก์ชันตัดตัวเลข/สัญลักษณ์ออกจากชื่อ เพื่อให้การจัดระเบียบบอร์ดสวยงาม
def clean_display_name(name: str) -> str:
    if not name: return ""
    cleaned = re.sub(r'^\d+[\.\s\-]*', '', name)
    return re.split(r'[\s\─\│]+[^\w\s]', cleaned)[0].strip() or name

# 🟢 ฟังก์ชันสร้างข้อความ Codeblock สำหรับบอร์ดอัปเดตอาวุธ
def build_weapon_board_text(guild: discord.Guild) -> str:
    gid = str(guild.id)
    default_slots = {str(i).zfill(2): {"user_id": None, "name": "", "knife": "ยังไม่มีมีด", "machete": "ยังไม่มีมาเชเต้", "pool_cue": "ยังไม่มีไม้พูล", "gun": "ยังไม่มีปืน"} for i in range(1, 31)}
    slots = load_data(gid, "weapon_slots", default_slots)

    # คำนวณสรุปจำนวนปืน
    gun_counts = {"+5": 0, "+4": 0, "+3": 0, "+2": 0, "+1": 0, "+0": 0, "ยังไม่มีปืน": 0}
    for slot_info in slots.values():
        if slot_info.get("user_id"):
            gun_val = slot_info.get("gun", "ยังไม่มีปืน")
            gun_counts[gun_val] = gun_counts.get(gun_val, 0) + 1

    summary = (
        "📊 **[ สรุปจำนวนปืนในแก๊ง ]**\n"
        f"• ปืน +5: {gun_counts['+5']} คน  │  ปืน +4: {gun_counts['+4']} คน  │  ปืน +3: {gun_counts['+3']} คน\n"
        f"• ปืน +2: {gun_counts['+2']} คน  │  ปืน +1: {gun_counts['+1']} คน  │  ปืน +0: {gun_counts['+0']} คน\n"
        "-------------------------------------------------------------\n\n"
    )

    lines = []
    for i in range(1, 31):
        slot_key = str(i).zfill(2)
        info = slots.get(slot_key, {})
        if info.get("user_id"):
            name = clean_display_name(info.get("name", ""))
            lines.append(f"{slot_key}. {name:<18} │ มีด {info.get('knife'):<12} │ มาเช {info.get('machete'):<12} │ ไม้ {info.get('pool_cue'):<12} │ ปืน {info.get('gun')}")
        else:
            lines.append(f"{slot_key}. ")

    now_str = get_thai_time().strftime('%d/%m/%Y เวลา %H:%M น.')
    return f"```text\n⚔️ __บอร์ดอัปเดตเลเวลอาวุธแก๊ง Dark Monday__\n\n{summary}" + "\n".join(lines) + f"\n\nUpdate {now_str}\n```"

# 🟢 ฟังก์ชันส่ง Log เมื่อมีแอดมินหรือสมาชิกทำรายการอาวุธ
async def send_weapon_audit_log(guild: discord.Guild, log_text: str):
    gid = str(guild.id)
    cfg = load_data(gid, "config", {})
    ch_id = cfg.get("weapon_log_ch")
    if ch_id:
        ch = guild.get_channel(int(ch_id))
        if ch:
            em = discord.Embed(title="📌 บันทึกระบบอาวุธ (Weapon Log)", description=f"{log_text}\n\n{LONG_SEP}", color=0xe67e22)
            em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M:%S')}")
            try: await ch.send(embed=em)
            except: pass

# 🟢 ฟังก์ชันอัปเดตข้อความบอร์ดอาวุธหลัก Real-time
async def update_weapon_board_msg(guild: discord.Guild):
    gid = str(guild.id)
    cfg = load_data(gid, "config", {})
    ch_id = cfg.get("weapon_board_ch")
    msg_id = cfg.get("weapon_board_msg")
    if ch_id and msg_id:
        ch = guild.get_channel(int(ch_id))
        if ch:
            try:
                msg = await ch.fetch_message(int(msg_id))
                await msg.edit(content=build_weapon_board_text(guild), view=WeaponBoardView())
            except: pass


# =====================================================================
# --- 🎰 ระบบสุ่มรายชื่อสมาชิก / จัดทีม (RANDOM SYSTEM MODULE) ---
# =====================================================================

class RandomSession:
    def __init__(self, mode: str, members: List[discord.Member], exempt_ids: List[int], target_channel_id: int, role_tag_id: Optional[int], author_id: int):
        self.mode = mode  # 'single' หรือ 'team'
        self.members = members
        self.exempt_ids = exempt_ids
        self.target_channel_id = target_channel_id
        self.role_tag_id = role_tag_id
        self.author_id = author_id
        self.count_num = 0
        self.round_count = 0
        self.history_logs: List[str] = []
        self.message_id: Optional[int] = None

ACTIVE_RANDOM_SESSIONS: Dict[int, RandomSession] = {}

def generate_random_result(session: RandomSession, new_exempt_ids: List[int], actor: discord.Member) -> discord.Embed:
    for eid in new_exempt_ids:
        if eid not in session.exempt_ids:
            session.exempt_ids.append(eid)

    available_members = [m for m in session.members if m.id not in session.exempt_ids]
    shuffled = available_members.copy()
    random.shuffle(shuffled)

    now_str = get_thai_time().strftime("%d/%m/%Y เวลา %H:%M น.")

    if session.round_count == 0:
        session.history_logs.append(f"ดำเนินการสุ่มโดย: `{actor.display_name}` | {now_str}")
    else:
        session.history_logs.append(f"🔄 สุ่มใหม่รอบที่ {session.round_count} โดย: `{actor.display_name}` | {now_str}")

    round_title_badge = f" [ 🔄 สุ่มใหม่รอบที่ {session.round_count} ]" if session.round_count > 0 else ""
    embed = discord.Embed(color=0x3498db)

    # 1. รายชื่อผู้ได้รับเลือก (ตัวเลขธรรมดา + ชื่อใส่กรอบเทา)
    if session.mode == "single":
        embed.title = f"🎲 ผลการสุ่มรายชื่อสมาชิก ({session.count_num} คน){round_title_badge}"
        selected = shuffled[:session.count_num]
        result_lines = [f"{idx}. `{m.display_name}`" for idx, m in enumerate(selected, 1)]
        main_content = "\n".join(result_lines) if result_lines else "*ไม่มีผู้ได้รับเลือก*"

    elif session.mode == "team":
        embed.title = f"🎲 ผลการสุ่มจัดทีม (ทีมละ {session.count_num} คน){round_title_badge}"
        teams = [shuffled[i:i + session.count_num] for i in range(0, len(shuffled), session.count_num)]
        
        description_parts = []
        team_icons = ["🔵", "🔴", "🟢", "🟡", "🟣", "🟠", "⚪", "🟤"]
        
        for idx, team in enumerate(teams, 1):
            if len(team) < session.count_num and idx == len(teams) and len(teams) > 1:
                icon = "🧩"
                team_name = f"{icon} **เศษ / คนสำรอง ({len(team)} คน):**"
            else:
                icon = team_icons[(idx - 1) % len(team_icons)]
                team_name = f"{icon} **ทีมที่ {idx} ({len(team)} คน):**"
            
            members_str = "\n".join([f"{t_idx}. `{m.display_name}`" for t_idx, m in enumerate(team, 1)])
            description_parts.append(f"{team_name}\n{members_str}")

        main_content = "\n\n".join(description_parts) if description_parts else "*ไม่มีสมาชิกเพียงพอ*"

    # 2. รายชื่อคนยกเว้น (ตัวเลขธรรมดา + ชื่อใส่กรอบเทา)
    exempt_members = [m for m in session.members if m.id in session.exempt_ids]
    if exempt_members:
        exempt_str = "\n".join([f"{idx}. `{m.display_name}`" for idx, m in enumerate(exempt_members, 1)])
    else:
        exempt_str = "*ไม่มี*"

    # 3. ประวัติการสุ่ม
    history_text = "\n".join(session.history_logs)

    # 🟢 รวมทุกอย่างไว้ใน description ตามรูปแบบที่คุณแก้ไขไว้เป๊ะๆ
    embed.description = (
        f"{main_content}\n\n"
        f"{LONG_SEP}\n\n"
        f"🚫 **รายชื่อที่ยกเว้นในรอบนี้ ({len(exempt_members)} คน):**\n"
        f"{exempt_str}\n\n"
        f"{LONG_SEP}\n\n"
        f"{history_text}"
    )

    return embed


# --- [แก้ไขจุดที่ 1: คลาส RerollConfirmModal] ---
class RerollConfirmModal(discord.ui.Modal):
    def __init__(self, session: RandomSession, selected_exempt_ids: List[int], parent_view: discord.ui.View, parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None):
        super().__init__(title="🔄 ยืนยันการสุ่มใหม่อีกรอบ")
        self.session = session
        self.selected_exempt_ids = selected_exempt_ids
        self.parent_view = parent_view
        self.parent_it = parent_it # 🟢 เพิ่มการรับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg # รับ Message ของเมนูตั้งค่าเดิมมาลบทิ้ง

        self.notice = discord.ui.InputText(
            label="⚠️ คำเตือนการบันทึกประวัติ",
            style=discord.InputTextStyle.paragraph,
            value="การกดสุ่มใหม่จะทำการบันทึกชื่อ Display Name ของคุณ รอบการสุ่ม และเวลาปัจจุบันลงในประกาศผลเพื่อความโปร่งใส",
            required=False
        )
        self.add_item(self.notice) # เพิ่มการใส่ Item ลงใน Modal ให้สมบูรณ์

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.session.round_count += 1
        new_embed = generate_random_result(self.session, self.selected_exempt_ids, interaction.user)
        
        # 🟢 สั่งปิดข้อความเมนูเลือกคนยกเว้นเดิม (Ephemeral) ออกทันที
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
        elif self.parent_msg:
            try: await self.parent_msg.delete()
            except: pass

        target_channel = interaction.guild.get_channel(self.session.target_channel_id) if interaction.guild else None
        if not target_channel and self.session.target_channel_id:
            target_channel = bot.get_channel(self.session.target_channel_id)

        if isinstance(target_channel, discord.TextChannel) and self.session.message_id:
            try:
                msg = await target_channel.fetch_message(self.session.message_id)
                role_mention = f"🔔 <@&{self.session.role_tag_id}>\n" if self.session.role_tag_id else ""
                await msg.edit(content=role_mention, embed=new_embed, view=RerollView(self.session))
                
                msg_ok = await interaction.followup.send("✅ **สุ่มใหม่และอัปเดตผลลัพธ์ในห้องประกาศเรียบร้อยแล้ว!**", ephemeral=True)
                await asyncio.sleep(3)
                try: await msg_ok.delete()
                except: pass
            except Exception as e:
                await interaction.followup.send(f"❌ **เกิดข้อผิดพลาดในการอัปเดตข้อความประกาศ:** {e}", ephemeral=True)
        else:
            await interaction.followup.send("❌ **ไม่พบห้องประกาศผล**", ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction)

class RerollExemptSelectView(discord.ui.View):
    def __init__(self, session: RandomSession):
        super().__init__(timeout=180)
        self.session = session
        self.selected_exempt_ids: List[int] = []

        available_members = [m for m in session.members if m.id not in session.exempt_ids]
        chunk_size = 25
        max_chunks = 2

        for idx, i in enumerate(range(0, min(len(available_members), max_chunks * chunk_size), chunk_size)):
            chunk = available_members[i:i + chunk_size]
            options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in chunk]
            select = discord.ui.Select(
                placeholder=f"🚫 เลือกคนยกเว้นเพิ่ม (ลำดับที่ {i+1}-{i+len(chunk)})...",
                min_values=0,
                max_values=len(options),
                options=options,
                row=idx
            )
            select.callback = self.make_select_callback(select)
            self.add_item(select)

    def make_select_callback(self, select_obj: discord.ui.Select):
        async def select_callback(interaction: discord.Interaction):
            selected = [int(v) for v in select_obj.values]
            chunk_options = [int(opt.value) for opt in select_obj.options]
            self.selected_exempt_ids = [eid for eid in self.selected_exempt_ids if eid not in chunk_options] + selected
            await interaction.response.defer()
        return select_callback

    @discord.ui.button(label="✅ ยืนยันสุ่มใหม่", style=discord.ButtonStyle.success, row=2)
    async def confirm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 🟢 ส่ง interaction (parent_it) เข้า Modal เพื่อสั่งปิดข้อความ Ephemeral หลังสุ่มเสร็จ
        modal = RerollConfirmModal(self.session, self.selected_exempt_ids, self, parent_it=interaction, parent_msg=interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ ยกเลิก", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass


class RerollView(discord.ui.View):
    def __init__(self, session: RandomSession):
        super().__init__(timeout=86400)
        self.session = session

    @discord.ui.button(label="🔄 สุ่มใหม่อีกรอบ", style=discord.ButtonStyle.secondary, custom_id="btn_reroll_main")
    async def reroll_button(self, button: discord.ui.Button, interaction: discord.Interaction): # 👈 [แก้ไข] สลับลำดับให้ button อยู่ก่อน
        is_author = interaction.user.id == self.session.author_id
        is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

        if not (is_author or is_admin):
            await interaction.response.send_message(
                "⚠️ **ไม่สามารถใช้งานได้!**\nเฉพาะผู้ที่สั่งสุ่มรอบนี้ หรือแอดมินเท่านั้นที่สามารถกดสุ่มใหม่ได้ครับ",
                ephemeral=True
            )
            await asyncio.sleep(10)
            try: await interaction.delete_original_response()
            except: pass
            return

        view = RerollExemptSelectView(self.session)
        await interaction.response.send_message(
            "🔄 **ตั้งค่าการสุ่มใหม่อีกรอบ**\nกรุณาเลือกรายชื่อที่ต้องการยกเว้นเพิ่มเติม (หากมี) แล้วกดปุ่มยืนยัน",
            view=view,
            ephemeral=True
        )

    async def on_timeout(self):
        if self.session.message_id and self.session.target_channel_id:
            try:
                channel = bot.get_channel(self.session.target_channel_id)
                if channel:
                    msg = await channel.fetch_message(self.session.message_id)
                    await msg.edit(view=None)
            except:
                pass

class RandomNumberInputModal(discord.ui.Modal):
    def __init__(self, session: RandomSession, parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None):
        title_text = "ระบุจำนวนคน" if session.mode == "single" else "ระบุจำนวนคนต่อทีม"
        super().__init__(title=f"🎲 {title_text}")
        self.session = session
        self.parent_it = parent_it # 🟢 เพิ่มการรับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg # รับ Message เมนูขั้นตอนที่ 2 มาลบทิ้ง

        label_text = "พิมพ์จำนวนคนที่ต้องการสุ่ม:" if session.mode == "single" else "พิมพ์จำนวนคนต่อ 1 ทีม:"
        self.num_input = discord.ui.InputText(
            label=label_text,
            placeholder="เช่น 3 หรือ 5",
            required=True,
            max_length=3
        )
        self.add_item(self.num_input)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            val = int(self.num_input.value)
            if val <= 0: raise ValueError()
        except ValueError:
            return await interaction.followup.send("❌ กรุณากรอกตัวเลขจำนวนเต็มที่มากกว่า 0 เท่านั้น", ephemeral=True)

        available_count = len([m for m in self.session.members if m.id not in self.session.exempt_ids])
        
        if self.session.mode == "single" and val > available_count:
            return await interaction.followup.send(
                f"⚠️ **จำนวนคนไม่เพียงพอ!**\nมีสมาชิกพร้อมสุ่มทั้งหมด {available_count} คน (ไม่รวมคนยกเว้น) แต่คุณระบุ {val} คน",
                ephemeral=True
            )

        self.session.count_num = val

        # 🟢 สั่งปิดหน้าเมนูขั้นตอนที่ 2 (Ephemeral) ออกทันที
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
        elif self.parent_msg:
            try: await self.parent_msg.delete()
            except: pass

        embed = generate_random_result(self.session, [], interaction.user)
        
        target_channel = interaction.guild.get_channel(self.session.target_channel_id) if interaction.guild else None
        if not target_channel and self.session.target_channel_id:
            target_channel = bot.get_channel(self.session.target_channel_id)

        if not isinstance(target_channel, discord.TextChannel):
            followup_err = await interaction.followup.send("❌ ไม่พบห้องข้อความปลายทาง", ephemeral=True)
            await asyncio.sleep(6)
            try: await followup_err.delete()
            except: pass
            return

        role_mention = f"🔔 <@&{self.session.role_tag_id}>\n" if self.session.role_tag_id else ""
        reroll_view = RerollView(self.session)
        sent_msg = await target_channel.send(content=role_mention, embed=embed, view=reroll_view)
        
        self.session.message_id = sent_msg.id
        ACTIVE_RANDOM_SESSIONS[sent_msg.id] = self.session

        followup_msg = await interaction.followup.send(
            f"✅ **ดำเนินการสุ่มและประกาศผลเรียบร้อยแล้ว!**\n➔ คลิกเพื่อไปยังห้องประกาศ: {sent_msg.jump_url}",
            ephemeral=True
        )

        await asyncio.sleep(10)
        try: await followup_msg.delete()
        except: pass

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction)

# --- คลาส RandomStep2ConfigView (ตั้งค่าห้องส่งผลและยศ row=0 และ row=1, ปุ่มกด row=2 อยู่ด้านล่าง) ---
class RandomStep2ConfigView(discord.ui.View):
    def __init__(self, session: RandomSession, guild: Optional[discord.Guild] = None):
        super().__init__(timeout=300)
        self.session = session
        self.guild = guild

        if self.guild:
            if self.session.target_channel_id:
                ch = self.guild.get_channel(self.session.target_channel_id)
                if ch:
                    for item in self.children:
                        if getattr(item, "type", None) == discord.ComponentType.channel_select:
                            item.default_values = [ch]
            if self.session.role_tag_id:
                r = self.guild.get_role(self.session.role_tag_id)
                if r:
                    for item in self.children:
                        if getattr(item, "type", None) == discord.ComponentType.role_select:
                            item.default_values = [r]

    @discord.ui.select(select_type=discord.ComponentType.channel_select, channel_types=[discord.ChannelType.text], placeholder="📢 1. เลือกห้องส่งผลประกาศ (บังคับเลือก)...", row=0)
    async def channel_select(self, select: discord.ui.Select, interaction: discord.Interaction):
        self.session.target_channel_id = select.values[0].id
        await self.update_msg(interaction)

    @discord.ui.select(select_type=discord.ComponentType.role_select, placeholder="🔔 2. เลือกยศที่จะแท็กแจ้งเตือน (ไม่เลือกก็ได้)...", min_values=0, max_values=1, row=1)
    async def role_select(self, select: discord.ui.Select, interaction: discord.Interaction):
        if select.values:
            self.session.role_tag_id = select.values[0].id
        else:
            self.session.role_tag_id = None
        await self.update_msg(interaction)

    async def update_msg(self, interaction: discord.Interaction):
        ch_str = f"<#{self.session.target_channel_id}>" if self.session.target_channel_id else "`ยังไม่ได้เลือก`"
        role_str = f"<@&{self.session.role_tag_id}>" if self.session.role_tag_id else "`ไม่แท็กยศ`"
        
        exempt_m = [m for m in self.session.members if m.id in self.session.exempt_ids]
        exempt_str = "\n".join([f"• `{m.display_name}`" for m in exempt_m]) if exempt_m else "• *ไม่มี*"

        text = (
            "📢 **__ขั้นตอนที่ 2: ตั้งค่าการส่งผลประกาศสุ่ม__**\n"
            "1. **กรุณาเลือกห้องข้อความที่ต้องการประกาศผลลัพธ์จาก Dropdown (บังคับเลือก)**\n"
            "2. เลือกยศที่ต้องการให้ระบบแท็กแจ้งเตือนเมื่อประกาศผล (ไม่เลือก = ไม่แท็ก)\n"
            "3. กดปุ่ม **'🎲 ระบุตัวเลขและเริ่มสุ่ม'** เพื่อพิมพ์กรอกจำนวน\n\n"
            f"{LONG_SEP}\n"
            f"📍 **ห้องที่เลือกส่งผล:** {ch_str}\n"
            f"🔔 **ยศที่จะแท็กแจ้งเตือน:** {role_str}\n"
            f"🚫 **สรุปรายชื่อที่ยกเว้นในรอบนี้ ({len(exempt_m)} คน):**\n{exempt_str}\n"
            f"{LONG_SEP}"
        )
        await interaction.response.edit_message(content=text, view=self)

    @discord.ui.button(label="🎲 ระบุตัวเลขและเริ่มสุ่ม", style=discord.ButtonStyle.success, row=2)
    async def start_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.session.target_channel_id:
            await interaction.response.send_message("⚠️ กรุณาเลือกห้องสำหรับส่งผลประกาศก่อนครับ!", ephemeral=True)
            await asyncio.sleep(5)
            try: await interaction.delete_original_response()
            except: pass
            return

        # 🟢 ส่ง interaction (parent_it) เข้า Modal เพื่อให้สั่งปิดข้อความ Ephemeral หลังกรอกตัวเลข
        modal = RandomNumberInputModal(self.session, parent_it=interaction, parent_msg=interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔙 ย้อนกลับ", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not interaction.guild: return
        view = RandomStep1ExemptView(self.session, interaction.guild)
        role_txt = f"<@&{self.session.selected_role_id}>" if getattr(self.session, 'selected_role_id', None) else "`สมาชิกทุกคน`"
        text = (
            f"🎲 **__ขั้นตอนที่ 1: เลือกยศและคนที่ไม่ต้องการให้เข้าร่วมสุ่ม__**\n"
            f"📌 **ยศที่เลือกสุ่มขณะนี้:** {role_txt} (รวม {len(self.session.members)} คน)\n\n"
            f"1. เลือกยศที่ต้องการสุ่มจาก Dropdown แถบแรก (หากไม่เลือก = สุ่มทุกคน)\n"
            f"2. เลือกรายชื่อคนที่ไม่พร้อมสุ่มในรอบนี้ (ไม่บังคับ)\n"
            f"3. กดปุ่ม **➔ ถัดไป (เลือกห้องและยศ)** เพื่อทำรายการต่อ\n\n"
            f"{LONG_SEP}"
        )
        await interaction.response.edit_message(content=text, view=view)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

class RandomStep1ExemptView(discord.ui.View):
    def __init__(self, session: RandomSession, guild: discord.Guild):
        super().__init__(timeout=300)
        self.session = session
        self.guild = guild
        
        role_id = getattr(self.session, 'selected_role_id', None)
        if role_id and self.guild:
            r = self.guild.get_role(role_id) # 🔴 [แก้ไข] ใช้ guild.get_role แทน discord.Object เพื่อป้องกัน TypeError
            if r:
                for item in self.children:
                    if getattr(item, "type", None) == discord.ComponentType.role_select:
                        item.default_values = [r]

        self.render_member_selects()

    @discord.ui.select(
        select_type=discord.ComponentType.role_select,
        placeholder="🏷️ Filter เลือกยศที่ต้องการสุ่ม (ไม่เลือก = สุ่มทุกคน)...",
        min_values=0,
        max_values=1,
        row=0
    )
    async def role_filter_select(self, select: discord.ui.Select, interaction: discord.Interaction):
        if select.values:
            selected_role = select.values[0]
            self.session.members = [m for m in selected_role.members if not m.bot]
            self.session.selected_role_id = selected_role.id # type: ignore
            role_txt = selected_role.mention
        else:
            self.session.members = [m for m in self.guild.members if not m.bot]
            self.session.selected_role_id = None # type: ignore
            role_txt = "`สมาชิกทุกคน`"

        self.session.exempt_ids = []
        self.render_member_selects()

        await interaction.response.edit_message(
            content=(
                f"🎲 **__ขั้นตอนที่ 1: เลือกยศและคนที่ไม่ต้องการให้เข้าร่วมสุ่ม__**\n"
                f"📌 **ยศที่เลือกสุ่มขณะนี้:** {role_txt} (รวม {len(self.session.members)} คน)\n\n"
                f"1. เลือกยศที่ต้องการสุ่มจาก Dropdown แถบแรก (หากไม่เลือก = สุ่มทุกคน)\n"
                f"2. เลือกรายชื่อคนที่ไม่พร้อมสุ่มในรอบนี้ (ไม่บังคับ)\n"
                f"3. กดปุ่ม **➔ ถัดไป (เลือกห้องและยศ)** เพื่อทำรายการต่อ"
            ),
            view=self
        )

    def render_member_selects(self):
        for item in list(self.children):
            if isinstance(item, discord.ui.Select) and item.placeholder and "🚫" in item.placeholder:
                self.remove_item(item)

        members = self.session.members
        chunk_size = 25
        max_chunks = 2
        
        for idx, i in enumerate(range(0, min(len(members), max_chunks * chunk_size), chunk_size)):
            chunk = members[i:i + chunk_size]
            start_num = i + 1
            end_num = i + len(chunk)
            
            options = []
            for m in chunk:
                is_selected = m.id in self.session.exempt_ids
                options.append(discord.SelectOption(label=f"{m.display_name}", value=str(m.id), default=is_selected))

            select = discord.ui.Select(
                placeholder=f"🚫 เลือกคนยกเว้น (ลำดับที่ {start_num}-{end_num})...",
                min_values=0,
                max_values=len(options),
                options=options,
                row=idx + 1
            )
            select.callback = self.make_select_callback(select)
            self.add_item(select)

    def make_select_callback(self, select_obj: discord.ui.Select):
        async def select_callback(interaction: discord.Interaction):
            selected_ids = [int(v) for v in select_obj.values]
            chunk_options_ids = [int(opt.value) for opt in select_obj.options]
            self.session.exempt_ids = [eid for eid in self.session.exempt_ids if eid not in chunk_options_ids] + selected_ids
            await interaction.response.defer()
        return select_callback

    @discord.ui.button(label="➔ ถัดไป (เลือกห้องและยศ)", style=discord.ButtonStyle.primary, row=3)
    async def next_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = RandomStep2ConfigView(self.session, interaction.guild) # 🔴 [แก้ไข] ส่ง interaction.guild เข้าไปด้วย
        
        ch_str = f"<#{self.session.target_channel_id}>" if self.session.target_channel_id else "`ยังไม่ได้เลือก`"
        role_str = f"<@&{self.session.role_tag_id}>" if self.session.role_tag_id else "`ไม่แท็กยศ`"
        exempt_m = [m for m in self.session.members if m.id in self.session.exempt_ids]
        exempt_str = "\n".join([f"• `{m.display_name}`" for m in exempt_m]) if exempt_m else "• *ไม่มี*"

        text = (
            "📢 **__ขั้นตอนที่ 2: ตั้งค่าการส่งผลประกาศสุ่ม__**\n"
            "1. **กรุณาเลือกห้องข้อความที่ต้องการประกาศผลลัพธ์จาก Dropdown (บังคับเลือก)**\n"
            "2. เลือกยศที่ต้องการให้ระบบแท็กแจ้งเตือนเมื่อประกาศผล (ไม่เลือก = ไม่แท็ก)\n"
            "3. กดปุ่ม **'🎲 ระบุตัวเลขและเริ่มสุ่ม'** เพื่อพิมพ์กรอกจำนวน\n\n"
            f"{LONG_SEP}\n"
            f"👥 **จำนวนคนเข้าสุ่มรอบนี้:** `{len(self.session.members) - len(exempt_m)}` คน\n"
            f"📍 **ห้องที่เลือกส่งผล:** {ch_str}\n"
            f"🔔 **ยศที่จะแท็กแจ้งเตือน:** {role_str}\n"
            f"🚫 **สรุปรายชื่อที่ยกเว้นในรอบนี้ ({len(exempt_m)} คน):**\n{exempt_str}\n"
            f"{LONG_SEP}"
        )
        await interaction.response.edit_message(content=text, view=view)

    @discord.ui.button(label="🔙 ย้อนกลับ", style=discord.ButtonStyle.secondary, row=3)
    async def back_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        view = RandomModeView(author=interaction.user, members=self.session.members) # type: ignore
        text = (
            "🎲 **__เมนูเลือกรูปแบบการสุ่มรายชื่อ__**\n"
            "กรุณาเลือกรูปแบบการสุ่มที่ต้องการใช้งานด้านล่างครับ:"
        )
        await interaction.response.edit_message(content=text, view=view)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=3)
    async def cancel_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

class RandomModeView(discord.ui.View):
    def __init__(self, author: discord.Member, members: List[discord.Member]):
        super().__init__(timeout=300)
        self.author = author
        self.members = members

    async def start_step1(self, interaction: discord.Interaction, mode: str):
        if not interaction.guild: return
        members = [m for m in interaction.guild.members if not m.bot]
        if not members:
            try:
                fetched = [m async for m in interaction.guild.fetch_members(limit=None)]
                members = [m for m in fetched if not m.bot]
            except:
                members = self.members

        session = RandomSession(
            mode=mode,
            members=members,
            exempt_ids=[],
            target_channel_id=0,
            role_tag_id=None,
            author_id=interaction.user.id
        )
        
        view = RandomStep1ExemptView(session, interaction.guild)
        text = (
            "🎲 **__ขั้นตอนที่ 1: เลือกยศและคนที่ไม่ต้องการให้เข้าร่วมสุ่ม__**\n"
            "📌 **ยศที่เลือกสุ่มขณะนี้:** `สมาชิกทุกคน`\n\n"
            "1. เลือกยศที่ต้องการสุ่มจาก Dropdown แถบแรก (หากไม่เลือก = สุ่มทุกคน)\n"
            "2. ติ๊กเลือกคนที่ไม่พร้อมสุ่มในรอบนี้\n"
            "3. กดปุ่ม **'➔ ถัดไป (เลือกห้องและยศ)'** เพื่อทำรายการต่อ\n\n"
            f"{LONG_SEP}"
        )
        await interaction.response.edit_message(content=text, view=view)

    @discord.ui.button(label="👤 สุ่มรายคน (ระบุจำนวนคน)", style=discord.ButtonStyle.primary, custom_id="random_single_mode_btn")
    async def single_mode(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.start_step1(interaction, "single")

    @discord.ui.button(label="👥 สุ่มจัดทีม (ระบุทีมละกี่คน)", style=discord.ButtonStyle.success, custom_id="random_team_mode_btn")
    async def team_mode(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.start_step1(interaction, "team")

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, custom_id="random_close_mode_btn")
    async def cancel_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

# --- 2. ระบบตาราง Real-time (แก้ไขให้แยก Guild) ---
async def update_summary_board(guild):
    gid = str(guild.id)
    cfg = load_data(gid, "config", {})
    ch_id = cfg.get("realtime_ch")
    if not ch_id: return
    channel = guild.get_channel(int(ch_id))
    if not channel: return
    
    data = load_data(gid, "leaves", [])
    now = get_thai_time().date()
    upcoming_limit = now + timedelta(days=7) # กำหนดเกณฑ์ล่วงหน้า 7 วัน
    
    grouped_leaves = {} # คนลาปัจจุบัน
    upcoming_leaves = [] # คนลาล่วงหน้า
    
    for e in data:
        try:
            start_dt = datetime.strptime(e['start_date'], "%d/%m/%Y").date()
            end_dt = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
            
            # 1. Logic สำหรับคนลาปัจจุบัน
            if start_dt <= now <= end_dt:
                tid = e['target_id']
                if tid not in grouped_leaves: grouped_leaves[tid] = []
                grouped_leaves[tid].append(e)
            
            # 2. Logic สำหรับคนลาล่วงหน้า (เริ่มลาหลังวันนี้แต่ไม่เกิน 7 วัน)
            elif now < start_dt <= upcoming_limit:
                upcoming_leaves.append(e)
        except: continue

    desc = f"# 📋 รายชื่อสมาชิกที่แจ้งลา (Real-time)\n{LONG_SEP}\n\n"
    
    # --- ส่วนที่ 1: รายชื่อคนลาปัจจุบัน (คำเดิม 100%) ---
    if not grouped_leaves:
        desc += "> 🍃 **ขณะนี้ยังไม่มีสมาชิกแจ้งลาในระบบ**\n\n"
    else:
        for tid, leaves in grouped_leaves.items():
            member = guild.get_member(int(tid))
            display_name = member.display_name if member else (leaves[0].get('name') or "ไม่ทราบชื่อ")
            desc += f" **👤 {display_name}**\n"
            for leaf in leaves:
                dr = leaf['start_date'] if leaf['start_date'] == leaf['end_date'] else f"{leaf['start_date']} - {leaf['end_date']}"
                cat_str = format_categories(leaf.get('leave_category', 'ทั่วไป'))
                
                if leaf['user_id'] != leaf['target_id']:                
                    executor = guild.get_member(int(leaf['user_id']))
                    ex_name = executor.display_name if executor else f"<@{leaf['user_id']}>"
                    on_behalf = f" **(ผู้แจ้งแทน: {ex_name})**" 
                else:
                    on_behalf = ""

                # 🟢 ปรับเฉพาะจุดนี้: เอาเฉพาะคำว่า วันที่: และช่วงวัน ออกจากกล่องเทา ส่วน (รวม X วัน) ใส่กล่องเทาไว้ตามสั่ง
                desc += f" ⠀• **วันที่:** {dr} `(รวม {leaf.get('total_days', 1)} วัน)`\n"
                desc += f" ⠀⠀⤷ **ประเภท:** {cat_str}\n"
                desc += f" ⠀⠀⤷ **เหตุผล:** {leaf.get('reason', '-')}{on_behalf}\n"
            
            # 🟢 เว้นระยะห่างก่อนขึ้นชื่อคนถัดไป
            desc += "\n"

    # --- ส่วนที่ 2: รายชื่อแจ้งลาล่วงหน้า (ย้ายมาไว้ล่างเส้นคั่น) ---[cite: 4]
    desc += f"{LONG_SEP}\n" 
    if upcoming_leaves:
        desc += f"**📅 __รายชื่อแจ้งลาล่วงหน้า (เร็วๆ นี้)__**\n\n"
        upcoming_leaves.sort(key=lambda x: datetime.strptime(x['start_date'], "%d/%m/%Y")) # เรียงจากใกล้ไปไกล[cite: 4]
        for u in upcoming_leaves:
            u_member = guild.get_member(int(u['target_id']))
            u_name = u_member.display_name if u_member else u.get('name', 'Unknown')
            u_dr = u['start_date'] if u['start_date'] == u['end_date'] else f"{u['start_date']} - {u['end_date']}"
            desc += f"👤 **{u_name}** \n \u17b5 \u17b5 \u17b5 \u17b5 \u17b5 \u17b5 \u17b5 \u17b5 \u17b5 ⤷ วันที่: {u_dr} `({u.get('leave_category','ทั่วไป')})`\n"
        desc += "\n"

    # --- ส่วนที่ 3: สรุปจำนวน (เพิ่มเส้นคั่นด้านบนตามสั่ง) ---[cite: 4]
    desc += f"{LONG_SEP}\n" 
    desc += f"**📊 สรุปจำนวนคนลาวันนี้: {len(grouped_leaves)} คน**\n"
    desc += f"**📅 อัปเดตล่าสุด: วันที่ {get_thai_time().strftime('%d/%m/%Y เวลา %H:%M น.')}**"
    
    em = discord.Embed(description=desc, color=0x2B2D31)
    target = None
    async for m in channel.history(limit=50):
        if m.author == bot.user and m.embeds and "รายชื่อสมาชิกที่แจ้งลา (Real-time)" in m.embeds[0].description:
            target = m
            break
    
    if target: await target.edit(embed=em, view=RealtimeRefreshView())
    else: await channel.send(embed=em, view=RealtimeRefreshView())

#refresh รีเฟรช
class RealtimeRefreshView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 กดอัปเดตข้อมูลล่าสุด", style=discord.ButtonStyle.success, custom_id="refresh_realtime_board")
    async def refresh_board(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("🔄 กำลังอัปเดต...", ephemeral=True)
        await update_summary_board(interaction.guild)
        await interaction.edit_original_response(content="✅ อัปเดตข้อมูลล่าสุดเรียบร้อยแล้ว!")
        await asyncio.sleep(3)
        try:
            await interaction.delete_original_response()
        except:
            pass

# --- 3. ระบบแจ้งลาและ Log (บังคับ ค.ศ. / ลาไม่เกิน 15 วัน / แยกสี Log) ---
class LeaveModal(discord.ui.Modal):
    def __init__(self, title, s_v, e_v, cat_val, t_id=None, is_f=False, old_re="", parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None):
        super().__init__(title=title)
        self.t_id, self.is_f, self.cat_val = t_id, is_f, cat_val
        self.s_v, self.e_v = s_v, e_v
        self.parent_it = parent_it # 🟢 รับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg # รับ Message ของเมนูเลือกประเภทการลามาลบทิ้ง
        
        if not is_f:
            self.s_i = discord.ui.InputText(
                label='เริ่มลาวันที่ (วว/ดด/ปปปป) *ใช้ ค.ศ. เท่านั้น', 
                placeholder='ตัวอย่าง: 25/04/2026', 
                value=s_v if s_v else None, 
                required=True
            )
            self.e_i = discord.ui.InputText(
                label='สิ้นสุดวันที่ (วว/ดด/ปปปป) *ใช้ ค.ศ. เท่านั้น', 
                placeholder='ตัวอย่าง: 30/04/2026', 
                value=e_v if e_v else None, 
                required=True
            )
            self.add_item(self.s_i)
            self.add_item(self.e_i)
        
        self.re = discord.ui.InputText(
            label='เหตุผลการลา', 
            placeholder='ระบุรายละเอียดเพิ่มเติม...', 
            style=discord.InputTextStyle.paragraph, 
            value=old_re if old_re else None, 
            required=True
        )
        self.add_item(self.re)
    
    async def callback(self, it: discord.Interaction):
        try:
            await it.response.defer(ephemeral=True)
            
            # 🟢 ปิดเมนูเลือกประเภทการลาเดิม (Ephemeral) ออกจากหน้าจอ
            if self.parent_it:
                try: await self.parent_it.delete_original_response()
                except: pass
            elif self.parent_msg:
                try: await self.parent_msg.delete()
                except: pass

            gid = str(it.guild.id) if it.guild else "0"
            
            s = self.s_v if self.is_f else (self.s_i.value.strip() if self.s_i.value else "")
            e = self.e_v if self.is_f else (self.e_i.value.strip() if self.e_i.value else "")
            re_val = self.re.value.strip() if self.re.value else "-"
            
            if not validate_date(s) or not validate_date(e):
                err_msg = f"**⚠️ รูปแบบวันที่ไม่ถูกต้อง หรือไม่ใช่ปี ค.ศ.!**\n\nท่านกรอกมาว่า: เริ่ม `{s}`, สิ้นสุด `{e}`\n(ตัวอย่าง ค.ศ. ที่ถูกต้อง: 28/04/2026) ❌"
                return await it.followup.send(content=err_msg, view=RetryView(self.title, "", "", self.cat_val, self.t_id, self.is_f, re_val), ephemeral=True)
            
            today = get_thai_time().date()
            s_dt = datetime.strptime(s, "%d/%m/%Y").date()
            e_dt = datetime.strptime(e, "%d/%m/%Y").date()

            if s_dt < today:
                return await it.followup.send(content="❌ **ไม่สามารถลาย้อนหลังได้**", view=RetryView(self.title, "", "", self.cat_val, self.t_id, self.is_f, re_val), ephemeral=True)
            if e_dt < s_dt:
                return await it.followup.send(content="❌ **วันที่สิ้นสุดต้องไม่มาก่อนวันที่เริ่มต้น!**", view=RetryView(self.title, s, "", self.cat_val, self.t_id, self.is_f, re_val), ephemeral=True)

            days = (e_dt - s_dt).days + 1
            if days > 15:
                return await it.followup.send(content=f"❌ **ไม่สามารถแจ้งลาเกิน 15 วันได้ (ท่านลา {days} วัน)**", view=RetryView(self.title, s, e, self.cat_val, self.t_id, self.is_f, re_val), ephemeral=True)

            target_uid = self.t_id if self.t_id else str(it.user.id)
            
            d = load_data(gid, "leaves", [])
            d.append({
                "user_id": str(it.user.id),
                "target_id": target_uid,
                "name": it.user.display_name,
                "leave_category": self.cat_val,
                "start_date": s,
                "end_date": e,
                "total_days": days,
                "reason": re_val
            })
            save_data(gid, "leaves", d)
            
            if it.guild:
                try: await update_summary_board(it.guild) 
                except Exception as board_err: print(f"⚠️ Warning: update_summary_board failed: {board_err}")

            cfg = load_data(gid, "config", {})
            log_ch_id = cfg.get("log_ch")
            
            if log_ch_id:
                try:
                    log_ch = bot.get_channel(int(log_ch_id))
                    if log_ch and it.guild:
                        target_m = it.guild.get_member(int(target_uid))
                        target_name = target_m.display_name if target_m else f"ID: {target_uid}"
                        executor_name = it.user.display_name

                        is_on_behalf = True if self.t_id and self.t_id != str(it.user.id) else False
                        log_title = "📌 บันทึกการแจ้งลาแทนเพื่อน" if is_on_behalf else "📌 บันทึกการแจ้งลาใหม่"
                        log_color = 0x3498db if is_on_behalf else 0x2ecc71
                        
                        log_em = discord.Embed(title=log_title, color=log_color)
                        on_behalf_txt = f"\n**👮 ผู้แจ้งลาแทน:** {executor_name}" if is_on_behalf else ""
                        dr = s if s == e else f"{s} - {e}"
                        
                        cat_display = format_categories(self.cat_val)
                        log_em.description = (
                            f"**👤 สมาชิกที่ลา:** {target_name}{on_behalf_txt}\n\n"
                            f"**📝 ประเภท:** {cat_display}\n"
                            f"**📅 วันที่ลา:** {dr} `(รวม {days} วัน)`\n"
                            f"**💬 เหตุผล:** {re_val}\n\n"
                            f"{LONG_SEP}"
                        )
                        log_em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M')} น.")
                        await log_ch.send(embed=log_em)
                except Exception as log_err:
                    print(f"⚠️ Warning: log_ch send failed: {log_err}")
            
            success_msg = await it.followup.send(content='✅ ระบบบันทึกใบลาของคุณเรียบร้อยแล้ว!', ephemeral=True)
            await asyncio.sleep(3)
            try: await success_msg.delete()
            except: pass

        except Exception as e:
            print(f"❌ Error in LeaveModal callback: {e}")
            try: await it.followup.send(content=f"❌ **เกิดข้อผิดพลาดในการบันทึกข้อมูล:** `{e}`", ephemeral=True)
            except: pass

    async def on_submit(self, it: discord.Interaction):
        await self.callback(it)

class RetryView(discord.ui.View):
    def __init__(self, title, s, e, cat, t_id, is_f, re_val):
        super().__init__(timeout=120)
        self.title, self.s, self.e, self.cat, self.t_id, self.is_f, self.re_val = title, s, e, cat, t_id, is_f, re_val

    @discord.ui.button(label="📝 แก้ไขข้อมูลอีกครั้ง", style=discord.ButtonStyle.primary)
    async def retry(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ลบข้อความแจ้งเตือนสีแดง/เหลืองเดิมทิ้งทันที เพื่อไม่ให้รกหน้าจอ
        try:
            await interaction.message.delete()
        except:
            pass
        await interaction.response.send_modal(LeaveModal(self.title, self.s, self.e, self.cat, self.t_id, self.is_f, self.re_val))

# --- 4. ส่วน Admin (ปรับหัวข้อหน้าหลักตามสั่ง + หมายเหตุใหม่) ---
# --- 1. วางทับคลาส ConfirmClearView ---
class ConfirmClearView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label="⚠️ ยืนยันล้างข้อมูลเก่า (ย้อนหลัง 4 เดือน / 120 วัน)", style=discord.ButtonStyle.success, custom_id="admin_confirm_cleanup_v1") 
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction): # 👈 [แก้ไข] สลับให้ button ขึ้นก่อน interaction
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild.id)
        path_leaves = get_path(gid, "leaves")
        path_config = get_path(gid, "config")
        
        try:
            f_send = []
            if os.path.exists(path_leaves): f_send.append(discord.File(path_leaves))
            if os.path.exists(path_config): f_send.append(discord.File(path_config))
            await interaction.user.send("📦 **Backup ก่อน Cleanup:** ท่านได้ดำเนินการล้างข้อมูลเก่า\nนี่คือไฟล์สำรองข้อมูลส่วนตัวของท่านครับ:", files=f_send)
        except discord.Forbidden:
            return await interaction.followup.send("❌ ไม่สามารถส่งไฟล์สำรองได้ โปรดเปิด DM แล้วลองใหม่อีกครั้ง", ephemeral=True)

        d = load_data(gid, "leaves", [])
        now = get_thai_time().date()
        threshold_date = now - timedelta(days=120) 
        filtered_data = []
        removed_count = 0
        
        for entry in d:
            try:
                end_dt = datetime.strptime(entry['end_date'], "%d/%m/%Y").date()
                if end_dt >= threshold_date: filtered_data.append(entry)
                else: removed_count += 1
            except: removed_count += 1

        save_data(gid, "leaves", filtered_data)
        cfg = load_data(gid, "config", {})
        log_ch_id = cfg.get("log_ch")
        if log_ch_id:
            log_ch = bot.get_channel(int(log_ch_id))
            if log_ch:
                l_em = discord.Embed(title="⚠️ ประกาศ: Cleanup ข้อมูลใบลาประจำเดือน", color=0xf39c12)
                l_em.description = (
                    f"**👮 ผู้ดำเนินการ:** {interaction.user.display_name}\n"
                    f"**🧹 ลบข้อมูลที่เก่ากว่า:** {threshold_date.strftime('%d/%m/%Y')} *(120 วัน)*\n"
                    f"**📊 จำนวนที่ลบออก:** `{removed_count}` รายการ\n"
                    f"**📦 ข้อมูลคงเหลือ:** `{len(filtered_data)}` รายการ\n\n"
                    f"{LONG_SEP}"
                )
                l_em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M:%S')}")
                await log_ch.send(embed=l_em)
            
        await interaction.edit_original_response(
            content=f"✅ Cleanup สำเร็จ! ลบข้อมูลเก่าที่เกิน 120 วัน ออกไป `{removed_count}` รายการเรียบร้อยแล้ว (ไฟล์ส่งเข้า DM ท่านแล้ว)", 
            view=None
        )
        await asyncio.sleep(3)
        try: await interaction.delete_original_response()
        except: pass

    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.danger, custom_id="admin_close_cleanup_panel")
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction): # 👈 [แก้ไข] สลับให้ button อยู่ก่อน interaction
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except: pass


# --- คลาส AdminSubChannelSelect (ดรอปดาวน์เลือกห้องแอดมิน ให้อยู่ row=0) ---
class AdminSubChannelSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            select_type=discord.ComponentType.channel_select,
            placeholder="🔍 ค้นหาห้องที่ต้องการ...",
            channel_types=[discord.ChannelType.text],
            row=0  # บังคับให้อยู่แถวบน
        )
    async def callback(self, it: discord.Interaction):
        self.view.temp_ch = self.values[0].id
        await it.response.edit_message(content=f"📍 เลือกห้อง: {self.values[0].mention}\n👉 **กรุณากดยืนยันด้านล่างเพื่อบันทึกครับ**")

# --- คลาส AdminSubMenuView (ปุ่มยืนยันตั้งค่า อยู่ row=1 อยู่ใต้ดรอปดาวน์) ---
class AdminSubMenuView(discord.ui.View):
    def __init__(self, cat):
        super().__init__(timeout=None)
        self.cat = cat
        self.temp_ch = None
        self.add_item(AdminSubChannelSelect())

    @discord.ui.button(label="ยืนยันตั้งค่า", style=discord.ButtonStyle.success, custom_id="admin_save_room_config", row=1)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.temp_ch:
            return await interaction.response.send_message("❌ กรุณาเลือกห้องก่อน!", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild.id) 
        cfg = load_data(gid, "config", {}) 
        cfg[self.cat] = str(self.temp_ch)
        save_data(gid, "config", cfg) 
        
        if self.cat == "leave_ch":
            em = discord.Embed(
                title=None, 
                description=(
                    "# __📋 ระบบการแจ้งลาแก๊ง Dark Monday__\n"
                    "กรุณากดปุ่มด้านล่างเพื่อทำรายการที่ท่านต้องการได้เลยครับ\n\n"
                    "### ⚠️ __หมายเหตุสำคัญ__ ⚠️\n"
                    "- การระบุวันที่ในระบบให้ใช้ปี **ค.ศ.** เท่านั้น (เช่น 28/04/2026)\n"
                    "- สมาชิกสามารถแจ้งลาได้สูงสุดไม่เกิน **15 วัน** ต่อการแจ้ง 1 ครั้ง\n"
                    "- ระบุเหตุผลการลาให้ชัดเจน (เช่น ติด OC, ธุระทางบ้าน, ลาป่วย)\n"
                    "- ระบบไม่อนุญาตให้ลาย้อนหลัง หากมีเหตุฉุกเฉินให้แจ้งแอดมินโดยตรง\n"
                    "- โปรดตรวจสอบข้อมูลให้ถูกต้อง การแจ้งลาเท็จจะมีบทลงโทษตามกฎแก๊ง\n\n"
                    "### 🆘 __รายละเอียดค่าปรับ__ 🆘\n"
                    "- แจ้งลาก่อน 21:00 น. → ไม่มีค่าปรับ\n"
                    "- แจ้งลาหลัง 21:00 น. → ค่าปรับ 500K\n"
                    "- ไม่แจ้งลา / หาย → ค่าปรับ 1M"
                ), 
                color=0x2B2D31
            )
            await bot.get_channel(int(self.temp_ch)).send(embed=em, view=LeaveMainView())
        elif self.cat == "realtime_ch":
            await update_summary_board(interaction.guild)
        
        await interaction.edit_original_response(content=f"✅ ตั้งค่าห้องสำหรับ **{self.cat}** สำเร็จ!", view=None)
        await asyncio.sleep(3)
        try: await interaction.delete_original_response()
        except: pass

class AdminCatSelect(discord.ui.Select):
    def __init__(self, opts):
        super().__init__(placeholder="เลือกหัวข้อที่จะตั้งค่า...", options=opts)
    async def callback(self, it):
        cat_final = self.values[0]
        await it.response.edit_message(content=f"🎯 กำลังตั้งค่า: **{cat_final}**", view=AdminSubMenuView(cat_final))


# --- ส่วนที่ 1: หน้าเลือกเลือกระบบ (ลา หรือ ปรับเงิน) ---
class CategorySelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 ระบบแจ้งลา", style=discord.ButtonStyle.primary, custom_id="setup_leave_system")
    async def leave_system_setup(self, button: discord.ui.Button, interaction: discord.Interaction):
        opts = [
            discord.SelectOption(label="📝 ห้องปุ่มแจ้งลา", value="leave_ch"),
            discord.SelectOption(label="📋 ตาราง Real-time", value="realtime_ch"),
            discord.SelectOption(label="📌 Log แจ้งลา", value="log_ch"),
            discord.SelectOption(label="📊 ประวัติรายวัน", value="daily_ch"),
            discord.SelectOption(label="📊 สรุปประวัติรายสัปดาห์", value="weekly_ch"),
        ]
        await interaction.response.edit_message(content="🛠 **ระบบแจ้งลา:** เลือกหัวข้อที่ต้องการตั้งค่า:", view=SubMenuView(interaction, AdminCatSelect(opts)))

    @discord.ui.button(label="💰 ระบบแจ้งปรับเงิน", style=discord.ButtonStyle.primary, custom_id="setup_fine_system")
    async def fine_system_setup(self, button: discord.ui.Button, interaction: discord.Interaction):
        opts = [
            discord.SelectOption(label="📋 แจ้งค่าปรับ Real-time", value="fine_realtime_ch"),
            discord.SelectOption(label="📌 Log การปรับเงิน", value="fine_log_ch"),
            discord.SelectOption(label="✅ อนุมัติการชำระเงิน", value="fine_approve_ch"),
        ]
        await interaction.response.edit_message(content="🛠 **ระบบแจ้งปรับเงิน:** เลือกหัวข้อที่ต้องการตั้งค่า:", view=SubMenuView(interaction, AdminCatSelect(opts)))

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, custom_id="admin_close_setup_category")
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except:
            pass

class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📍 ตั้งค่าห้องต่างๆ", style=discord.ButtonStyle.primary, custom_id="admin_panel_set_l_btn")
    async def set_l(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("📂 **เลือกหมวดหมู่ที่ต้องการจัดการ:**", view=CategorySelectionView(), ephemeral=True)

    @discord.ui.button(label="📋 ระบบลา", style=discord.ButtonStyle.primary, custom_id="admin_panel_leave_sys_btn")
    async def leave_system(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            content="📑 **เมนูจัดการระบบลา:** เลือกการดำเนินการที่ต้องการ", 
            view=AdminLeaveManagementView(), 
            ephemeral=True
        )

    @discord.ui.button(label="🎲 ระบบสุ่มรายชื่อ", style=discord.ButtonStyle.primary, custom_id="admin_panel_random_sys_btn")
    async def random_system(self, button: discord.ui.Button, interaction: discord.Interaction):
        members = [m for m in interaction.guild.members if not m.bot]
        if not members:
            await interaction.response.send_message("❌ ไม่พบสมาชิกในเซิร์ฟเวอร์", ephemeral=True)
            return

        view = RandomModeView(author=interaction.user, members=members)
        text = (
            "🎲 **__เมนูเลือกรูปแบบการสุ่มรายชื่อ__**\n"
            "กรุณาเลือกรูปแบบการสุ่มที่ต้องการใช้งานด้านล่างครับ:"
        )
        await interaction.response.send_message(content=text, view=view, ephemeral=True)

    # 🟢 เพิ่มปุ่มระบบอาวุธใน Admin Panel
    @discord.ui.button(label="⚔️ จัดการระบบอาวุธ", style=discord.ButtonStyle.success, custom_id="admin_panel_weapon_sys_btn")
    async def weapon_system(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            content="⚙️ **ระบบจัดการสล็อตและตั้งค่าบอร์ดอาวุธ**",
            view=AdminWeaponManageView(),
            ephemeral=True
        )


# =====================================================================
# --- ระบบสรุปประวัติการลาแบบรายเดือน (Monthly Report) ข้อมูลย้อนหลัง 3 เดือน ---
# =====================================================================
import calendar
THAI_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

# 🟢 1. ปุ่มเลือกเดือนใหม่ (กำหนดให้อยู่ row=4)
class ReselectMonthButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📅 เลือกเดือนใหม่", style=discord.ButtonStyle.primary, row=4)

    async def callback(self, it: discord.Interaction):
        await send_month_selection(it)

# 🟢 2. อัปเดตคลาส MonthlyDetailView (เพิ่มปุ่มปิดเมนูเรียงต่อด้านขวา)
class MonthlyDetailView(discord.ui.View):
    def __init__(self, guild, year, month):
        super().__init__(timeout=600)
        self.guild = guild
        self.year = year
        self.month = month

    @discord.ui.button(label="🔙 ย้อนกลับหน้าภาพรวม", style=discord.ButtonStyle.secondary)
    async def back_to_overview(self, button: discord.ui.Button, interaction: discord.Interaction):
        await generate_and_send_monthly_overview(interaction, self.guild, self.year, self.month)

    @discord.ui.button(label="📅 เลือกเดือนใหม่", style=discord.ButtonStyle.primary)
    async def reselect_month(self, button: discord.ui.Button, interaction: discord.Interaction):
        await send_month_selection(interaction)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger)
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

class MonthlyOverviewView(discord.ui.View):
    def __init__(self, guild, year, month):
        super().__init__(timeout=600)
        self.guild = guild
        self.year = year
        self.month = month

    @discord.ui.button(label="📅 เลือกเดือนใหม่", style=discord.ButtonStyle.primary, row=4)
    async def reselect_month(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ส่ง interaction (ตัวแปรที่ 2) ไปใช้งาน ไม่ใช่ button
        await send_month_selection(interaction)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=4)
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ใช้ interaction (ตัวแปรที่ 2) สั่ง defer และปิดเมนู
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except:
            pass

class MonthlyUserSelect(discord.ui.Select):
    def __init__(self, guild, year, month, opts, placeholder_str="🔍 เลือกสมาชิกที่ต้องการดูประวัติเจาะลึก..."):
        super().__init__(placeholder=placeholder_str, options=opts)
        self.guild_obj = guild
        self.year = year
        self.month = month

    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        target_member_id = self.values[0]
        target_member = self.guild_obj.get_member(int(target_member_id))
        target_name = target_member.display_name if target_member else f"ID: {target_member_id}"

        gid = str(it.guild.id)
        leaves = load_data(gid, "leaves", [])
        
        m_start = datetime(self.year, self.month, 1).date()
        m_end = datetime(self.year, self.month, calendar.monthrange(self.year, self.month)[1]).date()

        user_leaves = []
        total_days = 0
        cat_counts = {}

        for e in leaves:
            if e['target_id'] == target_member_id:
                try:
                    s_dt = datetime.strptime(e['start_date'], "%d/%m/%Y").date()
                    e_dt = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
                    if s_dt <= m_end and e_dt >= m_start:
                        overlap_s = max(s_dt, m_start)
                        overlap_e = min(e_dt, m_end)
                        days = (overlap_e - overlap_s).days + 1
                        
                        total_days += days
                        
                        # 🟢 รองรับการนับสถิติประเภททั้งแบบข้อความเดี่ยว (str) และหลายประเภท (list)
                        raw_cat = e.get('leave_category', 'ทั่วไป')
                        if isinstance(raw_cat, list):
                            for c in raw_cat:
                                cat_counts[c] = cat_counts.get(c, 0) + 1
                        else:
                            cat_counts[raw_cat] = cat_counts.get(raw_cat, 0) + 1
                        
                        user_leaves.append({
                            "data": e,
                            "calc_days": days,
                            "dr": f"{e['start_date']}" if e['start_date'] == e['end_date'] else f"{e['start_date']} - {e['end_date']}"
                        })
                except:
                    continue

        month_name = f"{THAI_MONTHS[self.month-1]} {self.year}"
        em = discord.Embed(title=f"👤 ประวัติการลา: {target_name}", description=f"📅 **ประจำเดือน {month_name}**\n{LONG_SEP}", color=0x3498db)
        
        if not user_leaves:
            em.description += "\n\n🍃 **สมาชิกท่านนี้ไม่มีประวัติการแจ้งลาในเดือนที่เลือก**"
        else:
            # ปรับการแสดงผลแยกประเภทให้เรียงลงมาทีละบรรทัดด้วย Bullet Dot (•)
            cat_summary = "\n".join([f"• {k}: `{v}` ครั้ง" for k, v in cat_counts.items()])
            
            em.description += f"\n📊 **รวมการลาในเดือนนี้:** `{len(user_leaves)}` ครั้ง | รวม `{total_days}` วัน\n"
            em.description += f"📌 **แยกตามประเภท:**\n{cat_summary}\n{LONG_SEP}\n\n"
            
            for idx, item in enumerate(user_leaves, 1):
                leaf = item["data"]
                calc_days = item["calc_days"]
                total_days = leaf.get('total_days', calc_days)
                
                if total_days > calc_days:
                    day_txt = f"(นับเฉพาะในเดือนนี้ {calc_days} วัน / รวมทั้งสิ้น {total_days} วัน)"
                else:
                    day_txt = f"(นับเฉพาะในเดือนนี้ {calc_days} วัน)"

                on_behalf = ""
                if leaf['user_id'] != leaf['target_id']:
                    ex_m = it.guild.get_member(int(leaf['user_id']))
                    ex_name = ex_m.display_name if ex_m else f"<@{leaf['user_id']}>"
                    on_behalf = f" *(ผู้แจ้งแทน: {ex_name})*"

                # ใส่ \. หลัง {idx} เพื่อบล็อกไม่ให้ Discord ทำเป็น Markdown List Block
                # 🟢 แปลงประเภทการลาเป็นย่อสีเทาผ่าน format_categories
                cat_disp_item = format_categories(leaf.get('leave_category', 'ทั่วไป'))
                em.description += (
                    rf"**{idx}\. [{cat_disp_item}]**\n"
                    f"┗ 📅 วันที่ลา: {item['dr']} `{day_txt}`\n"
                    f"┗ 💬 เหตุผล: {leaf.get('reason', '-')}{on_behalf}\n\n"
                )

        if len(em.description) > 4000:
            em.description = em.description[:3990] + "\n..."
        
        await it.edit_original_response(embed=em, view=MonthlyDetailView(self.guild_obj, self.year, self.month))



# 🟢 3. ฟังก์ชันสร้างหน้าสรุป (เพิ่ม Dropdown ให้ครบก่อน แล้วค่อยใส่ปุ่มต่อท้าย)
async def generate_and_send_monthly_overview(it: discord.Interaction, guild, year, month):
    gid = str(guild.id)
    leaves = load_data(gid, "leaves", [])
    
    now_dt = get_thai_time()
    now_date = now_dt.date()
    
    m_start = datetime(year, month, 1).date()
    last_day = calendar.monthrange(year, month)[1]
    m_end = datetime(year, month, last_day).date()

    if year == now_date.year and month == now_date.month:
        date_range_txt = f"01/{month:02d}/{year} - {now_date.strftime('%d/%m/%Y')}"
        info_label = "📌 **ข้อมูล ณ วันที่:**"
    else:
        date_range_txt = f"01/{month:02d}/{year} - {last_day:02d}/{month:02d}/{year}"
        info_label = "📌 **ข้อมูลทั้งเดือน:**"
        
    update_time_txt = f"🕒 **อัปเดตล่าสุด:** {now_dt.strftime('%d/%m/%Y เวลา %H:%M น.')}"

    target_role_id = 1456228588968739028
    exclude_role_id = 1498319593939144755
    gang_members = [m for m in guild.members if any(r.id == target_role_id for r in m.roles) and not any(r.id == exclude_role_id for r in m.roles)]
    if not gang_members:
        gang_members = [m for m in guild.members if not m.bot]

    stats = {}
    for m in gang_members:
        stats[str(m.id)] = {"member": m, "days": 0, "count": 0}

    for e in leaves:
        try:
            s_dt = datetime.strptime(e['start_date'], "%d/%m/%Y").date()
            e_dt = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
            if s_dt <= m_end and e_dt >= m_start:
                tid = e['target_id']
                if tid in stats:
                    overlap_s = max(s_dt, m_start)
                    overlap_e = min(e_dt, m_end)
                    days = (overlap_e - overlap_s).days + 1
                    stats[tid]["count"] += 1
                    stats[tid]["days"] += days
        except:
            continue

    leaved_list = []
    active_list = []
    for uid, data in stats.items():
        m = data["member"]
        if data["count"] > 0:
            leaved_list.append((uid, m.display_name, data["days"], data["count"]))
        else:
            active_list.append(m.display_name)

    leaved_list.sort(key=lambda x: (x[2], x[3]), reverse=True)

    month_name = f"{THAI_MONTHS[month-1]} {year}"
    
    desc = (
        f"## 📊 ประวัติการลาประจำเดือน {month_name}\n"
        f"{info_label} {date_range_txt}\n"
        f"{update_time_txt}\n"
        f"{LONG_SEP}\n\n"
    )

    if leaved_list:
        desc += "**❎ สมาชิกที่มีประวัติการลา:**\n"
        for idx, item in enumerate(leaved_list, 1):
            desc += f"`{idx}.` **{item[1]}** — รวม `{item[2]}` วัน (`{item[3]}` ครั้ง)\n"
        desc += "\n"
    else:
        desc += "🍃 **ไม่มีสมาชิกแจ้งลาในเดือนนี้**\n\n"

    if active_list:
        desc += f"{LONG_SEP}\n**✅ สมาชิกที่ไม่เคยแจ้งลาเลย:**\n"
        for idx, name in enumerate(active_list, 1):
            desc += f"`{idx}.` **{name}**\n"
        desc += "\n"

    desc += f"{LONG_SEP}\n*👉 เลือกรายชื่อสมาชิกจาก Dropdown ด้านล่างเพื่อดูประวัติเจาะลึก*"
    
    if len(desc) > 4000:
        desc = desc[:3990] + "\n..."

    em = discord.Embed(description=desc, color=0x2B2D31)
    view = MonthlyOverviewView(guild, year, month)
    
    all_user_opts = []
    for uid, name, days, count in leaved_list:
        all_user_opts.append(discord.SelectOption(label=f"{name} | ลา {days} วัน ({count} ครั้ง)", value=uid, emoji="❎"))
    for uid, data in stats.items():
        if data["count"] == 0:
            all_user_opts.append(discord.SelectOption(label=f"{data['member'].display_name} | (ไม่เคยลา)", value=uid, emoji="✅"))
    
    # ใส่ Dropdown สมาชิกทั้งหมดลงใน View ก่อน
    if all_user_opts:
        for start in range(0, len(all_user_opts), 25):
            end = start + 25
            chunk = all_user_opts[start:end]
            placeholder_text = f"🔍 เลือกสมาชิก (ลำดับที่ {start+1}-{min(end, len(all_user_opts))})..."
            view.add_item(MonthlyUserSelect(guild, year, month, chunk, placeholder_text))

    if not it.response.is_done():
        await it.response.edit_message(content=None, embed=em, view=view)
    else:
        await it.edit_original_response(content=None, embed=em, view=view)

# --- คลาส MonthSelect (กำหนด row=0 ให้อยู่แถวบนสุด) ---
class MonthSelect(discord.ui.Select):
    def __init__(self, opts):
        super().__init__(placeholder="📅 เลือกเดือนที่ต้องการดูสรุป...", options=opts, row=0)
    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        year, month = map(int, self.values[0].split('-'))
        await generate_and_send_monthly_overview(it, it.guild, year, month)

# --- คลาส MonthSelectView (สลับพารามิเตอร์ปุ่มเป็น button, interaction และกำหนด row=1 ให้อยู่ด้านล่าง) ---
class MonthSelectView(discord.ui.View):
    def __init__(self, opts):
        super().__init__(timeout=600)  # ขยายเวลาเป็น 10 นาที (600 วินาที)
        self.add_item(MonthSelect(opts))

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=1)
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

async def send_month_selection(it: discord.Interaction):
    now = get_thai_time().date()
    opts = []
    for i in range(3):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        opts.append(discord.SelectOption(label=f"{THAI_MONTHS[m-1]} {y}", value=f"{y}-{m:02d}", emoji="📅"))
    
    txt = "📅 **กรุณาเลือกเดือนที่ต้องการดูสรุปประวัติการลา:**"
    if not it.response.is_done():
        await it.response.edit_message(content=txt, embed=None, view=MonthSelectView(opts))
    else:
        await it.edit_original_response(content=txt, embed=None, view=MonthSelectView(opts))
# =====================================================================

# --- 4. ส่วน Admin (คงคำพูดเดิม / แก้ Logic แยกไฟล์) ---
class AdminLeaveManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚙️ จัดการใบลาทั้งหมด", style=discord.ButtonStyle.primary, custom_id="admin_manage_all_leaves_v2")
    async def manage_all(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        d = load_data(gid, "leaves", [])
        now_date = get_thai_time().date()
        limit_back_date = now_date - timedelta(days=14)
        all_opts = []
        
        for i, e in enumerate(d):
            try:
                target_end_date = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
                if target_end_date < limit_back_date: 
                    continue
            except: continue
            
            target_m = interaction.guild.get_member(int(e['target_id']))
            tn = target_m.display_name if target_m else e['name']
            dr = e['start_date'] if e['start_date'] == e['end_date'] else f"{e['start_date']} - {e['end_date']}"
            
            all_opts.append(discord.SelectOption(
                label=f"{tn} | {dr}",
                description=f"โดย: {interaction.guild.get_member(int(e['user_id'])).display_name if interaction.guild.get_member(int(e['user_id'])) else 'ระบบ'}",
                value=str(i)
            ))
            
        if not all_opts: 
            return await interaction.response.send_message("🍃 **ขณะนี้ไม่มีรายการใบลาที่กำลังดำเนินการอยู่**", ephemeral=True)

        view = discord.ui.View(timeout=300)
        for start in range(0, len(all_opts), 25):
            end = start + 25
            chunk = all_opts[start:end]
            placeholder_text = f"🔍 เลือกใบลา (รายการที่ {start+1}-{min(end, len(all_opts))})..."
            view.add_item(AdminActionSelect(chunk, placeholder_text))
            
        close_btn = discord.ui.Button(label="ปิดเมนู", style=discord.ButtonStyle.danger)
        async def close_callback(btn_it: discord.Interaction):
            await btn_it.response.defer()
            try: await btn_it.delete_original_response()
            except: pass
            
        close_btn.callback = close_callback
        view.add_item(close_btn)
            
        await interaction.response.edit_message(
            content="🛠 **แอดมินจัดการใบลา:** เลือกรายการที่ต้องการจัดการ:", 
            view=view
        )

    @discord.ui.button(label="📊 สรุปประวัติการลา (รายเดือน)", style=discord.ButtonStyle.primary, custom_id="admin_monthly_history_btn")
    async def history_monthly(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await send_month_selection(interaction)

    @discord.ui.button(label="🗑️ ล้างข้อมูลใบลา (120 วัน)", style=discord.ButtonStyle.primary, custom_id="admin_cleanup_trigger_v2")
    async def cleanup(self, button: discord.ui.Button, interaction: discord.Interaction):
        txt = "⚠️ **คุณยืนยันที่จะ Cleanup ข้อมูลใบลาที่เก่ากว่า 4 เดือน (120 วัน) ใช่หรือไม่?**\nระบบจะส่งไฟล์ Backup ให้คุณก่อนดำเนินการ"
        await interaction.response.send_message(content=txt, view=ConfirmClearView(), ephemeral=True)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, custom_id="admin_close_leave_system_v2")
    async def close_menu(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            await interaction.delete_original_response()
        except: pass

class AdminActionSelect(discord.ui.Select):
    # ปรับปรุงให้รับ placeholder_str เพื่อรองรับการแบ่งหน้า
    def __init__(self, opts, placeholder_str="🔍 เลือกใบลาที่ต้องการจัดการ..."):
        super().__init__(placeholder=placeholder_str, options=opts)
    
    async def callback(self, it: discord.Interaction):
        # --- เริ่มการแก้ไข Logic แยกไฟล์ตาม Guild ---
        gid = str(it.guild.id)
        
        idx = int(self.values[0])
        # โหลดข้อมูลใบลาเฉพาะของ Guild นี้
        d = load_data(gid, "leaves", []) 
        
        if 0 <= idx < len(d):
            od = d[idx]
            # คงคำพูดและรูปแบบเดิมของคุณไว้ทั้งหมด
            em = discord.Embed(title="⚙️ เมนูจัดการสำหรับผู้ดูแล", color=0xe67e22)
            em.description = (f"**👤 สมาชิก:** <@{od['target_id']}>\n"
                              f"**📅 วันที่:** {od['start_date']} - {od['end_date']}\n"
                              f"**📝 ประเภท:** {od.get('leave_category','ทั่วไป')}\n"
                              f"**💬 เหตุผล:** {od['reason']}")
            
            # ส่งเมนูทางเลือกถัดไป (แก้ไข/ยกเลิก)
            await it.response.edit_message(content="❓ **ท่านต้องการดำเนินการอย่างไรกับใบลานี้?**", 
                                           embed=em, view=AdminFinalActionView(idx, od))

class AdminFinalActionView(discord.ui.View):
    def __init__(self, idx, od):
        super().__init__(timeout=None)
        self.idx, self.od = idx, od

    @discord.ui.button(label="📝 แก้ไขข้อมูลใบลา", style=discord.ButtonStyle.secondary, custom_id="admin_edit_master_btn")
    async def edit_details(self, button: discord.ui.Button, interaction: discord.Interaction):
        opts = [discord.SelectOption(label=cat, value=cat, emoji="📝") for cat in LEAVE_CATEGORIES]
            
        await interaction.response.edit_message(
            content="🎯 **ขั้นตอนที่ 1:** เลือกประเภทการลาที่ต้องการ (เลือกได้หลายอัน)", 
            embed=None, 
            view=AdminEditCategoryView(self.idx, self.od, opts)
        )

    @discord.ui.button(label="🛑 ยกเลิกใบลานี้", style=discord.ButtonStyle.danger, custom_id="admin_cancel_leave_btn")
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(CancelReasonModal(self.idx, self.od, is_admin_request=True))

    @discord.ui.button(label="🔙 ย้อนกลับ", style=discord.ButtonStyle.secondary, custom_id="admin_back_to_select_leave_btn", row=1)
    async def back(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="🛠 **แอดมินจัดการใบลา:** เลือกรายการที่ต้องการจัดการอีกครั้ง:", 
            embed=None, 
            view=AdminLeaveManagementView()
        )


# --- [จุดที่ 1: กำหนด row=0 ให้ดรอปดาวน์อยู่บนปุ่มย้อนกลับ และคง # เดิมไว้ครบถ้วน] ---
class AdminEditCategoryView(discord.ui.View):
    def __init__(self, idx, od, opts):
        super().__init__(timeout=300)
        self.idx, self.od = idx, od
        self.add_item(AdminEditCategorySelect(idx, od, opts))

    @discord.ui.button(label="🔙 ย้อนกลับ", style=discord.ButtonStyle.secondary, row=1, custom_id="admin_edit_back_to_final")
    async def back(self, button: discord.ui.Button, interaction: discord.Interaction):
        em = discord.Embed(title="⚙️ เมนูจัดการสำหรับผู้ดูแล", color=0xe67e22)
        em.description = (f"**👤 สมาชิก:** <@{self.od['target_id']}>\n"
                          f"**📅 วันที่:** {self.od['start_date']} - {self.od['end_date']}\n"
                          f"**📝 ประเภท:** {self.od.get('leave_category','ทั่วไป')}\n"
                          f"**💬 เหตุผล:** {self.od['reason']}")
        await interaction.response.edit_message(content="❓ **ท่านต้องการดำเนินการอย่างไรกับใบลานี้?**", embed=em, view=AdminFinalActionView(self.idx, self.od))

class AdminEditCategorySelect(discord.ui.Select):
    def __init__(self, idx, od, opts):
        super().__init__(
            placeholder="🔍 เลือกประเภทการลาใหม่ (เลือกได้หลายอัน)...", 
            min_values=1,
            max_values=len(opts),
            options=opts, 
            custom_id="admin_category_select_dropdown",
            row=0  # 🟢 [แก้ไข] บังคับให้อยู่ row=0 เพื่อให้อยู่ด้านบนปุ่มย้อนกลับเสมอ
        )
        self.idx, self.od = idx, od
    
    async def callback(self, it: discord.Interaction):
        selected_cats = self.values
        if "ลาพีคไทม์ (ลาทุกกิจกรรม)" in selected_cats:
            final_cat = ["ลาพีคไทม์ (ลาทุกกิจกรรม)"]
        else:
            final_cat = selected_cats
        
        # 🟢 ส่ง it (parent_it) เข้า Modal เพื่อปิดข้อความเลือกหมวดหมู่ทันทีหลังบันทึกสำเร็จ
        await it.response.send_modal(AdminEditDetailsModal(self.idx, self.od, final_cat, parent_it=it, parent_msg=it.message))

# --- แก้ไข Logic ใน AdminEditDetailsModal (คำเดิม 100% + เพิ่มเงื่อนไข (คงเดิม)) ---
class AdminEditDetailsModal(discord.ui.Modal):
    def __init__(self, idx, od, selected_cat, parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None):
        super().__init__(title="แก้ไขใบลาแบบละเอียด (Admin)")
        self.idx, self.od, self.selected_cat = idx, od, selected_cat
        self.parent_it = parent_it # 🟢 เพิ่มการรับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg
        
        self.s_i = discord.ui.InputText(label="วันเริ่มลา (วว/ดด/ปปปป) *ค.ศ.*", value=od['start_date'], required=True)
        self.e_i = discord.ui.InputText(label="วันสิ้นสุด (วว/ดด/ปปปป) *ค.ศ.*", value=od['end_date'], required=True)
        self.re = discord.ui.InputText(label="เหตุผลการลา", style=discord.InputTextStyle.paragraph, value=od['reason'], required=True)
        self.admin_re = discord.ui.InputText(label="หมายเหตุจากแอดมิน (ทำไมถึงแก้?)", placeholder="ระบุเหตุผลเพื่อบันทึกใน Log...", required=True)
        
        self.add_item(self.s_i)
        self.add_item(self.e_i)
        self.add_item(self.re)
        self.add_item(self.admin_re)

    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        # 🟢 สั่งปิดข้อความเลือกหมวดหมู่ฝั่งแอดมิน (Ephemeral) ออกทันที
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
        elif self.parent_msg:
            try: await self.parent_msg.delete()
            except: pass

        gid = str(it.guild.id)
        new_s = self.s_i.value.strip()
        new_e = self.e_i.value.strip()
        new_reason = self.re.value.strip()
        admin_note = self.admin_re.value.strip()
        
        if not validate_date(new_s) or not validate_date(new_e):
            return await it.followup.send("❌ รูปแบบวันที่ไม่ถูกต้อง! (วว/ดด/ปปปป)", ephemeral=True)

        d = load_data(gid, "leaves", []) 
        if 0 <= self.idx < len(d):
            entry = d[self.idx]
            old_s, old_e = entry['start_date'], entry['end_date']
            old_cat = entry.get('leave_category', 'ทั่วไป')
            old_days = entry.get('total_days', 1)
            old_reason = entry.get('reason', '-')
            
            try:
                s_dt = datetime.strptime(new_s, "%d/%m/%Y").date()
                e_dt = datetime.strptime(new_e, "%d/%m/%Y").date()
                if e_dt < s_dt:
                    return await it.followup.send("❌ วันสิ้นสุดต้องไม่มาก่อนวันเริ่ม!", ephemeral=True)
                new_days = (e_dt - s_dt).days + 1
            except:
                return await it.followup.send("❌ เกิดข้อผิดพลาดในการคำนวณวันที่!", ephemeral=True)

            if old_s == new_s and old_e == new_e:
                date_txt = f"`{old_s}-{old_e}` (คงเดิม)"
            else:
                date_txt = f"`{old_s}-{old_e}` ➔ **`{new_s}-{new_e}`**"

            old_cat_str = format_categories(old_cat)
            new_cat_str = format_categories(self.selected_cat)
            cat_txt = f"{old_cat_str} (คงเดิม)" if old_cat == self.selected_cat else f"{old_cat_str} ➔ **{new_cat_str}**"
            
            days_txt = f"`{old_days}` วัน (คงเดิม)" if old_days == new_days else f"`{old_days}` ➔ **`{new_days}` วัน**"
            reason_txt = f"`{old_reason}` (คงเดิม)" if old_reason == new_reason else f"`{old_reason}` ➔ **`{new_reason}`**"

            entry.update({
                "start_date": new_s, 
                "end_date": new_e,
                "total_days": new_days,
                "leave_category": self.selected_cat,
                "reason": new_reason
            })
            
            save_data(gid, "leaves", d) 
            await update_summary_board(it.guild)
            
            # --- [จุดที่ 2: เปลี่ยนชื่อตัวแปรที่ส่งใน log_ch.send เป็น em] ---
            cfg = load_data(gid, "config", {}) 
            log_ch_id = cfg.get("log_ch")
            if log_ch_id:
                log_ch = bot.get_channel(int(log_ch_id))
                if log_ch:
                    target_m = it.guild.get_member(int(self.od['target_id']))
                    tn = target_m.display_name if target_m else self.od['name']
                    
                    em = discord.Embed(title="📌 บันทึกการจัดการโดยผู้ดูแล (แก้ไขใบลา)", color=0xe67e22)
                    em.description = (
                        f"**👤 สมาชิกที่ลา:** {tn}\n"
                        f"**👮 ผู้ดำเนินการ:** {it.user.display_name} (Admin)\n\n"
                        f"**🔄 รายละเอียดการเปลี่ยนแปลง:**\n"
                        f"• **วันที่ลา:** {date_txt}\n"
                        f"• **ประเภท:** {cat_txt}\n"
                        f"• **จำนวนวัน:** {days_txt}\n"
                        f"• **เหตุผล:** {reason_txt}\n\n"
                        f"**🛑 หมายเหตุจากแอดมิน:** {admin_note}\n\n"
                        f"{LONG_SEP}"
                    )
                    em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M:%S')}")
                    # 🟢 [แก้ไข] เปลี่ยนจาก embed=log_em เป็น embed=em เพื่อป้องกัน NameError
                    await log_ch.send(embed=em)

            msg_edited = await it.followup.send(content="✅ อัปเดตข้อมูลใบลาเรียบร้อยแล้ว!", ephemeral=True)       
            await asyncio.sleep(3) 
            try: await msg_edited.delete()
            except: pass

    async def on_submit(self, it: discord.Interaction):
        await self.callback(it)

# --- 5. งานรายวัน (ฉบับแก้ไข Syntax + นับจำนวนคนแบบ Unique) ---
# --- ฟังก์ชันสรุปรายวัน (คงคำพูดเดิม 100% / แก้ Logic แยกไฟล์ตาม Guild) ---
# --- 5. งานรายวัน (ฉบับแก้ไขเวลา 00:05 น. สรุปของเมื่อวาน + ป้องกันข้อความยาวเกิน) ---
# --- 5. งานรายวัน (ฉบับแก้ไขนับสถิติจำนวนคน และแยกนับทุกประเภทการลา 100%) ---
@tasks.loop(minutes=1)
async def daily_report_task():
    n = get_thai_time()
    
    # ส่งรายงานเวลา 00:05 น. ของทุกวัน (ดึงข้อมูลสรุปของเมื่อวาน)
    if n.hour == 0 and n.minute == 5:
        for guild in bot.guilds:
            gid = str(guild.id)
            cfg = load_data(gid, "config", {})
            ch_id = cfg.get("daily_ch", 0)
            
            if ch_id:
                ch = bot.get_channel(int(ch_id))
                if ch:
                    data = load_data(gid, "leaves", [])
                    cancelled_data = load_data(gid, "cancelled_leaves", [])
                    target_date = (n - timedelta(days=1)).date()
                    target_date_str = target_date.strftime('%d/%m/%Y')
                    
                    daily_grouped = {}
                    cat_counts = {}

                    # 1. กรองคนลาปกติ
                    for e in data:
                        try:
                            start_dt = datetime.strptime(e['start_date'], "%d/%m/%Y").date()
                            end_dt = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
                            if start_dt <= target_date <= end_dt:
                                tid = e['target_id']
                                if tid not in daily_grouped:
                                    daily_grouped[tid] = []
                                daily_grouped[tid].append(e)
                                
                                # 🟢 แก้ไข Logic การดึงและแยกนับประเภทการลา (แตกนับได้ทั้ง List และ String)
                                raw_cat = e.get('leave_category', 'ทั่วไป')
                                if isinstance(raw_cat, list):
                                    cats = raw_cat
                                elif isinstance(raw_cat, str):
                                    cats = [c.strip() for c in raw_cat.split(",") if c.strip()]
                                else:
                                    cats = ["ทั่วไป"]

                                for c in cats:
                                    cat_counts[c] = cat_counts.get(c, 0) + 1
                        except:
                            continue

                    # 2. กรองคนที่กดยกเลิกใบลาในวันดังกล่าว
                    cancelled_today = []
                    for c in cancelled_data:
                        try:
                            c_dt = datetime.strptime(c['cancelled_at'].split()[0], "%d/%m/%Y").date()
                            if c_dt == target_date:
                                cancelled_today.append(c)
                        except:
                            continue

                    separator = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
                    # 🟢 ใส่หัวข้อใหญ่ไว้บรรทัดแรกสุดของ desc_content ได้เลย
                    desc_content = f"## 📋 __รายงานสรุปการลาประจำวัน__\n### 📅 ของวันที่ {target_date_str}\n{separator}\n\n"

                    # แสดงส่วนที่ 1: รายชื่อคนลาปกติ
                    if not daily_grouped:
                        desc_content += "🍃 **เมื่อวานนี้ไม่มีสมาชิกแจ้งลาในระบบ**\n\n"
                    else:
                        for tid, leaves in daily_grouped.items():
                            member = guild.get_member(int(tid))
                            target_name = member.display_name if member else tid
                            desc_content += f"👤 **{target_name}**\n"
                            for leaf in leaves:
                                c_disp = format_categories(leaf.get('leave_category', 'ทั่วไป'))
                                desc_content += f" ⠀⠀⠀⠀⤷ **ประเภท:** {c_disp}\n"
                                desc_content += f" ⠀⠀⠀⠀⤷ **เหตุผล:** {leaf['reason']}\n"
                            desc_content += "\n"

                    # แสดงส่วนที่ 2: รายชื่อคนที่กดยกเลิกใบลาในวันนั้น
                    desc_content += f"{separator}\n"
                    if cancelled_today:
                        desc_content += "**🚫 รายการใบลาที่ถูกยกเลิกในวันนี้:**\n\n"
                        for c in cancelled_today:
                            target_m = guild.get_member(int(c['target_id']))
                            t_name = target_m.display_name if target_m else c.get('name', 'Unknown')
                            c_time = c['cancelled_at'].split()[1][:5]
                            
                            admin_tag = " (Admin)" if c.get('is_admin_cancel') else ""
                            by_txt = f" (ผู้ยกเลิก: {c.get('cancelled_by_name', '-')}{admin_tag})" if c['cancelled_by'] != c['target_id'] else ""

                            c_cat = format_categories(c.get('leave_category', 'ทั่วไป'))
                            desc_content += f"👤 **{t_name}** `[ยกเลิกเมื่อ {c_time} น.]{by_txt}`\n"
                            desc_content += f" ⠀⠀• `เดิมลาวันที่:` {c['start_date']} - {c['end_date']}\n"
                            desc_content += f" ⠀⠀⠀⠀⤷ **ประเภท:** {c_cat}\n"
                            desc_content += f" ⠀⠀⠀⠀⤷ **เหตุผลยกเลิก:** {c.get('cancel_reason', '-')}\n\n"
                    else:
                        desc_content += "🍃 **ไม่มีรายการยกเลิกใบลาในวันนี้**\n\n"

                    if len(desc_content) > 4000:
                        desc_content = desc_content[:3990] + "\n... (รายการส่วนที่เหลือถูกตัดเนื่องจากยาวเกินไป)"

                    em = discord.Embed(
                        description=desc_content,
                        color=0x2B2D31
                    )
                    
                    summary_msg = f"{separator}\n"
                    summary_msg += f"📊 **สรุปจำนวนคนลาวันนี้: `{len(daily_grouped)}` คน** | **ยกเลิก: `{len(cancelled_today)}` รายการ**\n\n"
                    for cat_name, count in cat_counts.items():
                        summary_msg += f"• {cat_name}: `{count}` ครั้ง\n"
                    
                    em.add_field(name="\u200b", value=summary_msg, inline=False)
                    em.set_footer(text=f"ระบบรายงานอัตโนมัติ: {n.strftime('%d/%m/%Y เวลา %H:%M น.')}")
                    await ch.send(embed=em)

# เพิ่มตัวช่วยให้ Loop ทำงานเสถียร ไม่ค้าง
@daily_report_task.before_loop
async def before_daily_report():
    await bot.wait_until_ready()

@daily_report_task.error
async def daily_report_error(error):
    print(f"เกิดข้อผิดพลาดใน Daily Task: {error}")
    if not daily_report_task.is_running():
        daily_report_task.restart()


# --- 6. ระบบยกเลิกใบลา (ฉบับปรับปรุง: เพิ่มการเก็บบันทึกข้อมูลยกเลิกใบลาลงไฟล์ (cancelled_leaves.json) ---
# โดยเพิ่มคำสั่งบันทึกรายการที่ถูกยกเลิก พร้อมลงเวลา cancelled_at เพื่อดึงมาแสดงผล
class CancelReasonModal(discord.ui.Modal):
    def __init__(self, target_idx, od, is_admin_request=False, parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None): 
        super().__init__(title="ระบุเหตุผลการยกเลิก")
        self.target_idx, self.od = target_idx, od
        self.is_admin_request = is_admin_request 
        self.parent_it = parent_it # 🟢 เพิ่มการรับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg # รับ Message เมนูยืนยันมาลบทิ้ง
        self.reason = discord.ui.InputText(label='เหตุผลที่ยกเลิก', placeholder='ระบุเหตุผลที่นี่...', style=discord.InputTextStyle.paragraph, required=True)
        self.add_item(self.reason)
    
    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        
        # 🟢 สั่งปิดข้อความสอบถามยืนยันการยกเลิก (Ephemeral) ทิ้งทันที
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
        elif self.parent_msg:
            try: await self.parent_msg.delete()
            except: pass

        gid = str(it.guild.id)
        d = load_data(gid, "leaves", []) 
        if 0 <= self.target_idx < len(d):
            old_data = d.pop(self.target_idx)
            save_data(gid, "leaves", d)
            
            cancelled_data = load_data(gid, "cancelled_leaves", [])
            cancelled_entry = old_data.copy()
            cancelled_entry.update({
                "cancelled_by": str(it.user.id),
                "cancelled_by_name": it.user.display_name,
                "cancel_reason": self.reason.value,
                "cancelled_at": get_thai_time().strftime("%d/%m/%Y %H:%M:%S"),
                "is_admin_cancel": self.is_admin_request
            })
            cancelled_data.append(cancelled_entry)
            save_data(gid, "cancelled_leaves", cancelled_data)

            await update_summary_board(it.guild)
            
            cfg = load_data(gid, "config", {})
            log_ch_id = cfg.get("log_ch")
            if log_ch_id:
                log_ch = bot.get_channel(int(log_ch_id))
                if log_ch:
                    u_id = str(it.user.id)
                    target_uid = old_data['target_id']
                    executor_name = it.user.display_name
                    
                    if self.is_admin_request:
                        executor_txt = f"**👮 ผู้ดำเนินการ:** {executor_name} (Admin)\n\n"
                    elif u_id != target_uid:
                        executor_txt = f"**👤 ผู้ดำเนินการ (ยกเลิกแทน):** {executor_name}\n\n"
                    else:
                        executor_txt = ""

                    log_title = "📌 บันทึกการจัดการโดยผู้ดูแล (ยกเลิกใบลา)" if self.is_admin_request else "📌 บันทึกยกเลิกการแจ้งลา"
                    log_color = 0xe67e22 if self.is_admin_request else 0xe74c3c 
                    note_label = "หมายเหตุจากแอดมิน" if self.is_admin_request else "หมายเหตุ"
                    
                    target_member = it.guild.get_member(int(old_data['target_id']))
                    tn = target_member.display_name if target_member else old_data['name']
                    dr = old_data['start_date'] if old_data['start_date'] == old_data['end_date'] else f"{old_data['start_date']} - {old_data['end_date']}"
                    cat_disp_log = format_categories(old_data.get('leave_category', 'ทั่วไป'))

                    log_em = discord.Embed(title=log_title, color=log_color)
                    log_em.description = (
                        f"**👤 สมาชิกที่ลา:** {tn}\n\n"
                        f"{executor_txt}"
                        f" • **วันที่ลา:** {dr} `({old_data.get('total_days', 1)} วัน)`\n"
                        f" • **ประเภท:** {cat_disp_log}\n"
                        f" • **เหตุผลเดิม:** {old_data.get('reason', '-')}\n\n"
                        f"**🛑 {note_label}:** {self.reason.value}\n\n"
                        f"{LONG_SEP}"
                    )
                    log_em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M:%S')}")
                    await log_ch.send(embed=log_em)
            
            msg_cancelled = await it.followup.send(content="❌ ยกเลิกรายการแจ้งลาเรียบร้อยแล้ว!", ephemeral=True)
            await asyncio.sleep(3)
            try: await msg_cancelled.delete()
            except: pass

    async def on_submit(self, it: discord.Interaction):
        await self.callback(it)

class ConfirmCancelView(discord.ui.View):
    def __init__(self, target_idx, od):
        super().__init__(timeout=300)
        self.target_idx, self.od = target_idx, od

    @discord.ui.button(label="✅ ยืนยันการยกเลิก", style=discord.ButtonStyle.success)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 🟢 ส่ง interaction (parent_it) เข้า Modal เพื่อปิดข้อความยืนยันเมื่อทำการยกเลิกสำเร็จ
        await interaction.response.send_modal(CancelReasonModal(self.target_idx, self.od, is_admin_request=False, parent_it=interaction, parent_msg=interaction.message))

    @discord.ui.button(label="❌ ไม่ยกเลิกแล้ว", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass


class CancelSelect(discord.ui.Select):
    def __init__(self, opts):
        super().__init__(placeholder="📋 เลือกรายการที่จะยกเลิก...", options=opts)
    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        gid = str(it.guild.id)
        idx = int(self.values[0])
        d = load_data(gid, "leaves", [])
        if 0 <= idx < len(d):
            od = d[idx]
            dr = od['start_date'] if od['start_date'] == od['end_date'] else f"{od['start_date']} - {od['end_date']}"
            # ครอบ format_categories เพื่อแก้ไขวงเล็บ List ['...']
            cat_display = format_categories(od.get('leave_category', 'ทั่วไป'))
            txt = f"⚠️ **แน่ใจหรือไม่ที่จะยกเลิกการลานี้?**\n👤 **คนลา:** <@{od['target_id']}>\n📝 **ประเภท:** {cat_display}\n📅 **วันที่:** {dr} `({od.get('total_days', 1)} วัน)`"
            await it.edit_original_response(content=txt, view=ConfirmCancelView(idx, od))

# --- 7. ระบบแก้ไขวันสิ้นสุด (ปรับตามสั่ง: ตัดพิมพ์เอง / หัวข้อใหม่ / อีโมจิปฏิทิน / Modal เหตุผล) ---
async def process_edit_leave(it, idx, od, new_end_str, edit_reason="-"):
    gid = str(it.guild.id) # ระบุ ID เซิร์ฟเวอร์
    d = load_data(gid, "leaves", []) # โหลดข้อมูลของ Guild นี้
    old_e = od['end_date']
    
    if 0 <= idx < len(d):
        old_days = (datetime.strptime(old_e, "%d/%m/%Y") - datetime.strptime(od['start_date'], "%d/%m/%Y")).days + 1
        new_days = (datetime.strptime(new_end_str, "%d/%m/%Y") - datetime.strptime(od['start_date'], "%d/%m/%Y")).days + 1
        diff = new_days - old_days
        diff_txt = f"เพิ่มขึ้น {diff} วัน" if diff > 0 else f"ลดลง {abs(diff)} วัน" if diff < 0 else "เท่าเดิม"

        d[idx]['end_date'] = new_end_str
        d[idx]['total_days'] = new_days
        save_data(gid, "leaves", d) # บันทึกแยกไฟล์ตาม Guild ID
        await update_summary_board(it.guild)
        
        cfg = load_data(gid, "config", {}) # โหลด Config ของ Guild นี้
        log_ch_id = cfg.get("log_ch")
        if log_ch_id:
            log_ch = bot.get_channel(int(log_ch_id))
            if log_ch:
                u_id = str(it.user.id)
                has_admin_role = any(r.name in ["Admin", "ผู้ดูแล"] for r in it.user.roles)
                is_involved = u_id == od['target_id'] or u_id == od['user_id']
                is_admin_action = has_admin_role and not is_involved
                
                log_title = "📌 บันทึกการจัดการโดยผู้ดูแล" if is_admin_action else "📌 บันทึกการแก้ไขวันสิ้นสุดการลา"
                log_color = 0xe67e22 if is_admin_action else 0x95a5a6
                
                target_member = it.guild.get_member(int(od['target_id']))
                target_name = target_member.display_name if target_member else od['name']
                executor_name = it.user.display_name
                
                log_em = discord.Embed(title=log_title, color=log_color)
                on_behalf = f"\n**👮 ผู้แจ้งแก้ไขแทน:** {executor_name} (Admin)" if is_admin_action else f"\n**👤 ผู้แจ้งแก้ไขแทน:** {executor_name}" if u_id != od['target_id'] else ""
                
                log_em.description = (
                    f"**👤 สมาชิกที่ลา:** {target_name}{on_behalf}\n\n"
                    f"**📝 ประเภท:** {od.get('leave_category', 'ทั่วไป')}\n"
                    f"**📅 วันที่ลาเดิม:** {od['start_date']} - {old_e} `({old_days} วัน)`\n"
                    f"**📅 วันที่ลาใหม่:** {od['start_date']} - {new_end_str} `({new_days} วัน)`\n"
                    f"**📈 การเปลี่ยนแปลง:** `{diff_txt}`\n"
                    f"**💬 เหตุผลเดิมที่แจ้ง:** {od.get('reason', '-')}\n"
                    f"**🛑 เหตุผลที่ขอแก้ไข:** {edit_reason}\n\n"
                    f"{LONG_SEP}"
                )
                log_em.set_footer(text=f"บันทึกเมื่อ: {get_thai_time().strftime('%d/%m/%Y %H:%M')} น.")
                await log_ch.send(embed=log_em) 
        
        # 3. จัดการปิดข้อความลับ (เพิ่มการ Delete เพื่อให้หายไปเอง)
        try:
            await it.edit_original_response(content=f"✅ แก้ไขวันสิ้นสุดเป็นวันที่ `{new_end_str}` เรียบร้อยแล้ว!", embed=None, view=None)
            await asyncio.sleep(3)
            await it.delete_original_response()
        except:
            pass

class EditReasonModal(discord.ui.Modal):
    def __init__(self, idx, od, new_end, parent_it: Optional[discord.Interaction] = None, parent_msg: Optional[discord.Message] = None):
        super().__init__(title="ระบุเหตุผลการแก้ไขวันลา")
        self.idx, self.od, self.new_end = idx, od, new_end
        self.parent_it = parent_it # 🟢 เพิ่มการรับ parent_it เพื่อสั่งปิดข้อความ Ephemeral
        self.parent_msg = parent_msg # รับ Message เมนูก่อนหน้ามาลบทิ้ง
        self.reason = discord.ui.InputText(label='เหตุผลที่ขอแก้ไข', placeholder='ระบุรายละเอียด...', style=discord.InputTextStyle.paragraph, required=True)
        self.add_item(self.reason)

    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        # 🟢 สั่งปิดข้อความยืนยันการแก้ไขวันลา (Ephemeral) ออกทันที
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
        elif self.parent_msg:
            try: await self.parent_msg.delete()
            except: pass
        await process_edit_leave(it, self.idx, self.od, self.new_end, self.reason.value)

    async def on_submit(self, it: discord.Interaction):
        await self.callback(it)

class EditRetryView(discord.ui.View):
    def __init__(self, idx, od, p_it):
        super().__init__(timeout=300)
        self.idx, self.od, self.p_it = idx, od, p_it

    @discord.ui.button(label="📝 แก้ไขวันที่อีกครั้ง", style=discord.ButtonStyle.primary)
    async def retry(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="📅 **เลือกวันที่สิ้นสุดใหม่อีกครั้ง:**", 
            embed=None, 
            view=SubMenuView(interaction, EditDateSelect(self.idx, self.od, interaction))
        )
        try: await interaction.delete_original_response()
        except: pass

class EditDateModal(discord.ui.Modal):
    def __init__(self, idx, od, parent_it=None):
        super().__init__(title="ระบุวันที่กลับมาจริง")
        self.idx, self.od, self.parent_it = idx, od, parent_it
        self.new_e = discord.ui.InputText(label='วันที่กลับมาจริง (วว/ดด/ปปปป) *ใช้ ค.ศ. เท่านั้น', placeholder='ตัวอย่าง: 28/04/2026', required=True)
        self.add_item(self.new_e)

    # เปลี่ยนชื่อเป็น callback
    async def callback(self, it: discord.Interaction):
        val = self.new_e.value.strip()
        
        if not validate_date(val):
            return await it.response.send_message("❌ รูปแบบวันที่ไม่ถูกต้อง หรือไม่ใช่ปี ค.ศ.!", view=EditRetryView(self.idx, self.od, self.parent_it), ephemeral=True)
        
        s_dt = datetime.strptime(self.od['start_date'], "%d/%m/%Y")
        e_dt = datetime.strptime(val, "%d/%m/%Y")
        
        if e_dt < s_dt:
            return await it.response.send_message("❌ วันที่กลับมาจริงต้องไม่มาก่อนวันที่เริ่มลา!", view=EditRetryView(self.idx, self.od, self.parent_it), ephemeral=True)
        
        new_days = (e_dt - s_dt).days + 1
        if new_days > 15:
            return await it.response.send_message(content=f"❌ **ไม่สามารถลาเกิน 15 วันได้ (ยอดใหม่คือ {new_days} วัน)**\nโปรดติดต่อแอดมินเพื่อแก้ไขรายการนี้", view=EditRetryView(self.idx, self.od, self.parent_it), ephemeral=True)
        
        if self.parent_it:
            try: await self.parent_it.delete_original_response()
            except: pass
            
        old_days = (datetime.strptime(self.od['end_date'], "%d/%m/%Y") - s_dt).days + 1
        diff = new_days - old_days
        diff_txt = f"เพิ่มขึ้น {diff} วัน" if diff > 0 else f"ลดลง {abs(diff)} วัน" if diff < 0 else "จำนวนวันเท่าเดิม"
        
        em = discord.Embed(title="ตรวจสอบความถูกต้องก่อนยืนยัน", color=0xffffff)
        em.description = (
            f"**👤 สมาชิก:** <@{self.od['target_id']}>\n"
            f"**📅 วันที่ลาเดิม:** {self.od['start_date']} - {self.od['end_date']} `({old_days} วัน)`\n"
            f"**📅 วันที่ลาใหม่:** {self.od['start_date']} - {val} `({new_days} วัน)`\n"
            f"**📊 การเปลี่ยนแปลง:** `{diff_txt}`\n\n"
            f"**ยืนยันการแก้ไขข้อมูลหรือไม่?**"
        )
        await it.response.send_message(embed=em, view=ConfirmEditView(self.idx, self.od, val), ephemeral=True)

    async def on_submit(self, it: discord.Interaction):
        await self.callback(it)

class ConfirmEditView(discord.ui.View):
    def __init__(self, idx, od, new_end):
        super().__init__(timeout=300)
        self.idx, self.od, self.new_end = idx, od, new_end

    @discord.ui.button(label="✅ ยืนยันการแก้ไข", style=discord.ButtonStyle.success)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 🟢 ส่ง interaction (parent_it) เข้า Modal
        await interaction.response.send_modal(EditReasonModal(self.idx, self.od, self.new_end, parent_it=interaction, parent_msg=interaction.message))

    @discord.ui.button(label="📅 เลือกวันใหม่", style=discord.ButtonStyle.primary)
    async def reselect(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content="📅 **กรุณาเลือกวันที่สิ้นสุดใหม่อีกครั้ง:**", embed=None, view=SubMenuView(interaction, EditDateSelect(self.idx, self.od, interaction)))

    @discord.ui.button(label="❌ ยกเลิก", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass


class EditDateSelect(discord.ui.Select):
    def __init__(self, idx, od, parent_it=None):
        self.idx, self.od, self.parent_it = idx, od, parent_it
        s_dt = datetime.strptime(od['start_date'], "%d/%m/%Y")
        opts = []
        for i in range(15):
            d_str = (s_dt + timedelta(days=i)).strftime("%d/%m/%Y")
            opts.append(discord.SelectOption(label=d_str, value=d_str))
        super().__init__(placeholder="📅 เลือกวันที่กลับมาจริง...", options=opts)
    async def callback(self, it: discord.Interaction):
        val = self.values[0]
        s_dt = datetime.strptime(self.od['start_date'], "%d/%m/%Y")
        e_dt = datetime.strptime(val, "%d/%m/%Y")
        new_days = (e_dt - s_dt).days + 1
        old_days = (datetime.strptime(self.od['end_date'], "%d/%m/%Y") - s_dt).days + 1
        diff = new_days - old_days
        diff_txt = f"เพิ่มขึ้น {diff} วัน" if diff > 0 else f"ลดลง {abs(diff)} วัน" if diff < 0 else "จำนวนวันเท่าเดิม"

        em = discord.Embed(title="ตรวจสอบความถูกต้องก่อนยืนยัน", color=0xffffff)
        em.description = (
            f"**👤 สมาชิก:** <@{self.od['target_id']}>\n"
            f"**📅 วันที่ลาเดิม:** {self.od['start_date']} - {self.od['end_date']} `({old_days} วัน)`\n"
            f"**📅 วันที่ลาใหม่:** {self.od['start_date']} - {val} `({new_days} วัน)`\n"
            f"**📊 การเปลี่ยนแปลง:** `{diff_txt}`\n\n"
            f"**ยืนยันการแก้ไขข้อมูลหรือไม่?**"
        )
        await it.response.edit_message(content=None, embed=em, view=ConfirmEditView(self.idx, self.od, val))

class EditLeaveSelect(discord.ui.Select):
    def __init__(self, opts, parent_it=None):
        super().__init__(placeholder="✏️ เลือกใบลาที่ต้องการแก้...", options=opts)
        self.parent_it = parent_it
    async def callback(self, it: discord.Interaction):
        await it.response.defer(ephemeral=True)
        gid = str(it.guild.id) # เพิ่ม Logic ระบุ Guild
        idx = int(self.values[0])
        d = load_data(gid, "leaves", []) # เปลี่ยนมาใช้ load_data
        if 0 <= idx < len(d):
            await it.edit_original_response(content="📅 **เลือกวันที่สิ้นสุดใหม่:**", view=SubMenuView(it, EditDateSelect(idx, d[idx], it)))

class LeaveMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="📝 แจ้งลา", style=discord.ButtonStyle.success, custom_id="v_l_final_vMaster_DMD_master_1")
    async def l_me(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("🤔 **ลาช่วงไหน:**", view=DateSelectView(), ephemeral=True)

    @discord.ui.button(label="👥 ลาแทนเพื่อน", style=discord.ButtonStyle.primary, custom_id="v_l_final_vMaster_DMD_master_2")
    async def l_fr(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("👤 เลือกเพื่อน:", view=SubMenuView(interaction, FriendSelect()), ephemeral=True)   
    
    @discord.ui.button(label="❌ ยกเลิกการลา", style=discord.ButtonStyle.danger, custom_id="v_l_final_vMaster_DMD_master_3")
    async def l_cn(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        d = load_data(gid, "leaves", [])
        u_id = str(interaction.user.id)
        now_date = get_thai_time().date()
        opts = []
        has_blocked_leave = False
        
        for i, e in enumerate(d):
            if e['user_id'] == u_id or e['target_id'] == u_id:
                try:
                    s_date = datetime.strptime(e['start_date'], "%d/%m/%Y").date()
                    e_date = datetime.strptime(e['end_date'], "%d/%m/%Y").date()
                    if e_date < now_date: continue
                    is_multi_day = e['start_date'] != e['end_date']
                    is_past_first_day = s_date < now_date
                    if is_multi_day and is_past_first_day:
                        has_blocked_leave = True
                        continue
                except: continue
                
                target_member = interaction.guild.get_member(int(e['target_id']))
                tn = target_member.display_name if target_member else e['name']
                dr = e['start_date'] if e['start_date'] == e['end_date'] else f"{e['start_date']} - {e['end_date']}"
                cat_txt = format_categories(e.get('leave_category', 'ทั่วไป'))
                opts.append(discord.SelectOption(
                    label=f"{tn} | {dr} ({e.get('total_days', 1)} วัน)",
                    description=f"ประเภท: {cat_txt[:20]} | เหตุผล: {e.get('reason','-')[:15]}",
                    value=str(i)
                ))
        
        if not opts: 
            if has_blocked_leave:
                msg = (
                    "❌ **ไม่พบรายการที่คุณสามารถยกเลิกได้**\n\n"
                    "⚠️ *หมายเหตุ: รายการที่ผ่านวันเริ่มลาไปแล้ว ไม่สามารถยกเลิกทั้งใบได้ "
                    "หากคุณกลับมาก่อนกำหนด กรุณาใช้ปุ่ม **'✏️ แก้ไขวันลา'** เพื่อปรับวันสิ้นสุดแทน*"
                )
                # 🟢 [แก้ไขจุดที่ 1.1] ส่งข้อความและสั่งตั้งเวลาปิดอัตโนมัติภายใน 5 วินาที
                await interaction.response.send_message(msg, ephemeral=True)
                await asyncio.sleep(5)
                try: await interaction.delete_original_response()
                except: pass
                return
            else:
                # 🟢 [แก้ไขจุดที่ 1.2] ส่งข้อความและสั่งตั้งเวลาปิดอัตโนมัติภายใน 5 วินาที
                await interaction.response.send_message("❌ ไม่พบรายการที่คุณสามารถยกเลิกได้", ephemeral=True)
                await asyncio.sleep(5)
                try: await interaction.delete_original_response()
                except: pass
                return
            
        await interaction.response.send_message("📋 เลือกใบลาของคุณที่จะยกเลิก:", view=SubMenuView(interaction, CancelSelect(opts[:25])), ephemeral=True)
  
    @discord.ui.button(label="✏️ แก้ไขวันลา", style=discord.ButtonStyle.danger, custom_id="v_l_final_vMaster_DMD_master_4")
    async def l_ed(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        d = load_data(gid, "leaves", [])
        u_id, now_date, opts = str(interaction.user.id), get_thai_time().date(), []

        for i, e in enumerate(d):
            if (e['user_id'] == u_id or e['target_id'] == u_id) and e['start_date'] != e['end_date']:
                try:
                    if datetime.strptime(e['end_date'], "%d/%m/%Y").date() < now_date: continue
                except: continue
                
                target_member = interaction.guild.get_member(int(e['target_id']))
                tn = target_member.display_name if target_member else e['name']
                dr = e['start_date'] if e['start_date'] == e['end_date'] else f"{e['start_date']} - {e['end_date']}"
                cat_txt = format_categories(e.get('leave_category', 'ทั่วไป'))
                opts.append(discord.SelectOption(
                    label=f"{tn} | {dr} ({e.get('total_days', 1)} วัน)",
                    description=f"ประเภท: {cat_txt[:20]} | เหตุผล: {e.get('reason','-')[:15]}",
                    value=str(i)
                ))
        
        if not opts: 
            # 🟢 [แก้ไขจุดที่ 2] ส่งข้อความและสั่งตั้งเวลาปิดอัตโนมัติภายใน 5 วินาที
            await interaction.response.send_message("❌ ไม่พบรายการที่คุณสามารถแก้ไขได้", ephemeral=True)
            await asyncio.sleep(5)
            try: await interaction.delete_original_response()
            except: pass
            return
            
        await interaction.response.send_message("✏️ เลือกใบลาของคุณที่จะแก้ไข:", view=SubMenuView(interaction, EditLeaveSelect(opts[:25], interaction)), ephemeral=True)


class FriendSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            select_type=discord.ComponentType.user_select,
            placeholder="👤 เลือกเพื่อน...",
            min_values=1,
            max_values=1
        )
    async def callback(self, it: discord.Interaction):
        t_id = str(self.values[0].id)
        await it.response.edit_message(
            content=f"🎯 **ลาแทนคุณ:** {self.values[0].mention}\n👉 **กรุณาเลือกวันที่ลาด้านล่าง:**", 
            view=DateSelectView(t_id=t_id)
        )

# 🟢 คลาสจัดการเมนูเลือกวัน (ตั้ง timeout 300 วิ + มีปุ่มย้อนกลับไปเลือกเพื่อนใหม่)
# 🟢 คลาสจัดการหน้าเลือกวัน (มีปุ่มย้อนกลับไปเลือกเพื่อนใหม่ ถ้าเป็นการลาแทนเพื่อน)
# --- คลาส DateSelectView (ปุ่มเลือกเพื่อนใหม่/ปิดเมนู อยู่ row=1 อยู่ใต้ดรอปดาวน์) ---
class DateSelectView(discord.ui.View):
    def __init__(self, t_id=None):
        super().__init__(timeout=300)
        self.t_id = t_id
        self.add_item(DateSelect(t_id=t_id))
        
        if self.t_id:
            back_btn = discord.ui.Button(label="🔙 เลือกเพื่อนใหม่", style=discord.ButtonStyle.secondary, row=1)
            async def back_to_friend(it: discord.Interaction):
                await it.response.edit_message(content="👤 **เลือกเพื่อน:**", view=SubMenuView(it, FriendSelect()))
            back_btn.callback = back_to_friend
            self.add_item(back_btn)
            
        close_btn = discord.ui.Button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=1)
        async def close_menu(it: discord.Interaction):
            await it.response.defer()
            try: await it.delete_original_response()
            except: pass
        close_btn.callback = close_menu
        self.add_item(close_btn)

class SubMenuView(discord.ui.View):
    def __init__(self, o_it, item=None):
        super().__init__(timeout=60)
        self.o_it = o_it
        if item: self.add_item(item)

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=3)
    async def cls(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

# --- คลาส DateSelect (ดรอปดาวน์เลือกวันที่ลา อยู่ row=0) ---
class DateSelect(discord.ui.Select):
    def __init__(self, t_id=None):
        self.t_id = t_id
        opts = [discord.SelectOption(label="ลาวันนี้", value="t"), discord.SelectOption(label="ลาพรุ่งนี้", value="tm"), discord.SelectOption(label="ลาแบบระบุวันเอง", value="m")]
        super().__init__(placeholder="📅 เลือกวันที่ลา...", options=opts, row=0) # บังคับ row=0
    async def callback(self, it):
        now = get_thai_time()
        val = self.values[0]
        if val == "t": title, s, e, is_fixed = "ลาวันนี้", now.strftime("%d/%m/%Y"), now.strftime("%d/%m/%Y"), True
        elif val == "tm": title, s, e, is_fixed = "ลาพรุ่งนี้", (now + timedelta(days=1)).strftime("%d/%m/%Y"), (now + timedelta(days=1)).strftime("%d/%m/%Y"), True
        else: title, s, e, is_fixed = "ลาแบบระบุวันเอง", "", "", False

        prefix = f"✅ **ลาแทนคุณ:** <@{self.t_id}>\n" if self.t_id else ""
        content_text = (
            f"{prefix}"
            f"✅ **วันที่ลา:** {title}\n"
            f"👉 **เลือกประเภทการลา (เลือกได้มากกว่า 1 ประเภท)**"
        )
        await it.response.edit_message(content=content_text, view=LeaveCategoryView(title, s, e, self.t_id, is_f=is_fixed))

# --- คลาส LeaveCategorySelect (ดรอปดาวน์เลือกประเภทการลา ให้อยู่แถวแรก row=0) ---
class LeaveCategorySelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=x, emoji="📝") for x in LEAVE_CATEGORIES]
        super().__init__(
            placeholder="📝 เลือกประเภทการลา (เลือกได้หลายอัน)...", 
            min_values=1, 
            max_values=len(opts), 
            options=opts,
            row=0  # บังคับให้อยู่แถวบนสุด
        )
        
    async def callback(self, it: discord.Interaction):
        # บันทึกค่าที่เลือกเก็บไว้ใน View เพื่อรอปุ่มกด
        self.view.selected_cats = self.values
        await it.response.defer()

# --- คลาส LeaveCategoryView (ปุ่มยืนยัน/ย้อนกลับ อยู่แถวที่ row=1 จะได้อยู่ใต้ดรอปดาวน์) ---
class LeaveCategoryView(discord.ui.View):
    def __init__(self, m_title, s_v, e_v, t_id=None, is_f=False):
        super().__init__(timeout=300)
        self.m_title, self.s_v, self.e_v, self.t_id, self.is_f = m_title, s_v, e_v, t_id, is_f
        self.selected_cats = []
        self.add_item(LeaveCategorySelect())

    @discord.ui.button(label="✅ ยืนยันประเภทการลาที่เลือก", style=discord.ButtonStyle.success, row=1)
    async def confirm_category(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_cats:
            return await interaction.response.send_message("❌ **กรุณาคลิกเลือกประเภทการลาในกล่องด้านบนก่อนกดปุ่มยืนยันครับ!**", ephemeral=True)

        if "ลาพีคไทม์ (ลาทุกกิจกรรม)" in self.selected_cats:
            final_cat = ["ลาพีคไทม์ (ลาทุกกิจกรรม)"]
        else:
            final_cat = self.selected_cats

        # 🟢 ส่ง interaction (parent_it) เข้า Modal เพื่อปิดข้อความส่วนตัวเมื่อส่งใบลาสำเร็จ
        await interaction.response.send_modal(LeaveModal(self.m_title, self.s_v, self.e_v, final_cat, self.t_id, self.is_f, parent_it=interaction, parent_msg=interaction.message))

    @discord.ui.button(label="🔙 ย้อนกลับไปเลือกวัน", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_date(self, button: discord.ui.Button, interaction: discord.Interaction):
        prefix = f"🎯 **ลาแทนคุณ:** <@{self.t_id}>\n" if self.t_id else ""
        txt = f"{prefix}👉 **กรุณาเลือกวันที่ลาด้านล่าง:**"
        await interaction.response.edit_message(content=txt, view=DateSelectView(t_id=self.t_id))

    @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=1)
    async def cls(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try: await interaction.delete_original_response()
        except: pass

# 🟢 [แก้ไข] ใส่ # คอมเมนต์ปิดปุ่มชุดล่างไว้ (ไม่ลบโค้ดออก)
#   @discord.ui.button(label="🔙 ย้อนกลับไปเลือกวัน", style=discord.ButtonStyle.secondary, row=1)
#   async def back_to_date(self, button: discord.ui.Button, interaction: discord.Interaction):
#       prefix = f"🎯 **ลาแทนคุณ:** <@{self.t_id}>\n" if self.t_id else ""
#       txt = f"{prefix}👉 **กรุณาเลือกวันที่ลาด้านล่าง:**"
#       await interaction.response.edit_message(content=txt, view=DateSelectView(t_id=self.t_id))

#   @discord.ui.button(label="ปิดเมนู", style=discord.ButtonStyle.danger, row=1)
#   async def cls(self, button: discord.ui.Button, interaction: discord.Interaction):
#       await interaction.response.defer()
#       try: await interaction.delete_original_response()
#       except: pass


@bot.command()
@commands.has_any_role("Admin", "ผู้ดูแล")
async def admin(ctx):
    await ctx.send(embed=discord.Embed(title="🕹 Dark Monday Admin Panel"), view=AdminPanelView())

# =====================================================================
# --- ⚔️ UI & INTERFACE MODULE SYSTEM (WEAPON SYSTEM) ---
# =====================================================================

# 🟢 Modal สำหรับให้สมาชิกอัปเดตเหตุผล/หมายเหตุอาวุธ
class MemberWeaponUpdateView(discord.ui.View):
    def __init__(self, user_slot_key: str):
        super().__init__(timeout=300)
        self.user_slot_key = user_slot_key

    @discord.ui.select(placeholder="🗡️ เลือกเลเวลมีด...", options=[
        discord.SelectOption(label="ยังไม่มีมีด", value="ยังไม่มีมีด"),
        discord.SelectOption(label="+0", value="+0"), discord.SelectOption(label="+1", value="+1"),
        discord.SelectOption(label="+2", value="+2"), discord.SelectOption(label="+3", value="+3"),
        discord.SelectOption(label="+4", value="+4"), discord.SelectOption(label="+5", value="+5")
    ], row=0)
    async def select_knife(self, select: discord.ui.Select, interaction: discord.Interaction):
        self.knife_val = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="🔫 เลือกเลเวลปืน...", options=[
        discord.SelectOption(label="ยังไม่มีปืน", value="ยังไม่มีปืน"),
        discord.SelectOption(label="+0", value="+0"), discord.SelectOption(label="+1", value="+1"),
        discord.SelectOption(label="+2", value="+2"), discord.SelectOption(label="+3", value="+3"),
        discord.SelectOption(label="+4", value="+4"), discord.SelectOption(label="+5", value="+5")
    ], row=1)
    async def select_gun(self, select: discord.ui.Select, interaction: discord.Interaction):
        self.gun_val = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="✅ ยืนยันการอัปเดต", style=discord.ButtonStyle.success, row=2)
    async def confirm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        slots = load_data(gid, "weapon_slots", {})

        if self.user_slot_key not in slots:
            return await interaction.response.send_message("❌ ไม่พบสล็อตของคุณในระบบ", ephemeral=True)

        log_changes = []
        if hasattr(self, 'knife_val'):
            old_val = slots[self.user_slot_key].get("knife", "ยังไม่มีมีด")
            slots[self.user_slot_key]["knife"] = self.knife_val
            log_changes.append(f"มีด: `{old_val}` ➔ `{self.knife_val}`")
        if hasattr(self, 'gun_val'):
            old_val = slots[self.user_slot_key].get("gun", "ยังไม่มีปืน")
            slots[self.user_slot_key]["gun"] = self.gun_val
            log_changes.append(f"ปืน: `{old_val}` ➔ `{self.gun_val}`")

        save_data(gid, "weapon_slots", slots)

        await interaction.response.send_message("✅ อัปเดตข้อมูลอาวุธของคุณเรียบร้อยแล้ว!", ephemeral=True)
        if log_changes:
            await send_weapon_audit_log(interaction.guild, f"🔄 **{interaction.user.display_name}** (สล็อต {self.user_slot_key}) อัปเดตอาวุธ:\n• " + "\n• ".join(log_changes))
            await update_weapon_board_msg(interaction.guild)

# 🟢 Modal เพิ่มรายชื่อเข้าสล็อต (Admin)
class AdminSlotAssignModal(discord.ui.Modal):
    def __init__(self, target_member: discord.Member):
        super().__init__(title="⚙️ เพิ่มรายชื่อสมาชิกเข้าสล็อต")
        self.target_member = target_member
        self.slot_num = discord.ui.InputText(label="🔢 หมายเลขสล็อต (1-30)", placeholder="เช่น 4 หรือ 12", max_length=2, required=True)
        self.add_item(self.slot_num)

    async def callback(self, interaction: discord.Interaction):
        try:
            slot_int = int(self.slot_num.value)
            if not (1 <= slot_int <= 30): raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ กรุณากรอกหมายเลขสล็อตเป็นตัวเลข 1-30 เท่านั้น", ephemeral=True)

        slot_key = str(slot_int).zfill(2)
        gid = str(interaction.guild.id)
        default_slots = {str(i).zfill(2): {"user_id": None, "name": "", "knife": "ยังไม่มีมีด", "machete": "ยังไม่มีมาเชเต้", "pool_cue": "ยังไม่มีไม้พูล", "gun": "ยังไม่มีปืน"} for i in range(1, 31)}
        slots = load_data(gid, "weapon_slots", default_slots)

        slots[slot_key]["user_id"] = self.target_member.id
        slots[slot_key]["name"] = self.target_member.display_name
        save_data(gid, "weapon_slots", slots)

        await interaction.response.send_message(f"✅ เพิ่ม {self.target_member.display_name} เข้าสล็อต **{slot_key}** เรียบร้อย!", ephemeral=True)
        await send_weapon_audit_log(interaction.guild, f"🛠️ **{interaction.user.display_name}** เพิ่ม **{self.target_member.display_name}** เข้าสล็อต **{slot_key}**")
        await update_weapon_board_msg(interaction.guild)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction)

# 🟢 View จัดการสล็อตและตั้งค่าบอร์ด (Admin Panel)
class AdminWeaponManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.user_select(placeholder="👤 เลือกสมาชิกที่ต้องการใส่เข้าสล็อต...", row=0)
    async def select_user(self, select: discord.ui.Select, interaction: discord.Interaction):
        member = select.values[0]
        await interaction.response.send_modal(AdminSlotAssignModal(member))

    @discord.ui.button(label="📌 ตั้งค่าห้องบอร์ดอาวุธ", style=discord.ButtonStyle.primary, row=1)
    async def setup_board_ch(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("📍 **เลือกห้องที่ต้องการใช้แสดงบอร์ดอาวุธ:**", view=WeaponChannelSetupView("board"), ephemeral=True)

    @discord.ui.button(label="📌 ตั้งค่าห้อง Log อาวุธ", style=discord.ButtonStyle.primary, row=1)
    async def setup_log_ch(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("📍 **เลือกห้องที่ต้องการใช้บันทึก Weapon Log:**", view=WeaponChannelSetupView("log"), ephemeral=True)

# 🟢 View เลือกห้องตั้งค่าสำหรับระบบอาวุธ
class WeaponChannelSetupView(discord.ui.View):
    def __init__(self, mode: str):
        super().__init__(timeout=180)
        self.mode = mode

    @discord.ui.channel_select(channel_types=[discord.ChannelType.text], placeholder="📢 เลือกห้องข้อความ...", row=0)
    async def select_channel(self, select: discord.ui.Select, interaction: discord.Interaction):
        ch = select.values[0]
        gid = str(interaction.guild.id)
        cfg = load_data(gid, "config", {})

        if self.mode == "board":
            cfg["weapon_board_ch"] = str(ch.id)
            board_text = build_weapon_board_text(interaction.guild)
            msg = await ch.send(content=board_text, view=WeaponBoardView())
            cfg["weapon_board_msg"] = str(msg.id)
            save_data(gid, "config", cfg)
            await interaction.response.send_message(f"✅ บันทึกและสร้างบอร์ดอัปเดตอาวุธในห้อง {ch.mention} เรียบร้อย!", ephemeral=True)

        elif self.mode == "log":
            cfg["weapon_log_ch"] = str(ch.id)
            save_data(gid, "config", cfg)
            await interaction.response.send_message(f"✅ บันทึกห้อง Weapon Log เป็น {ch.mention} เรียบร้อย!", ephemeral=True)

# 🟢 Persistent View บอร์ดอัปเดตอาวุธหลัก (ปุ่มถาวร)
class WeaponBoardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 อัปเดตอาวุธของฉัน", style=discord.ButtonStyle.primary, custom_id="persistent_weapon_update_btn")
    async def update_weapon_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        slots = load_data(gid, "weapon_slots", {})

        user_slot_key = next((k for k, v in slots.items() if v.get("user_id") == interaction.user.id), None)

        if not user_slot_key:
            return await interaction.response.send_message("❌ คุณยังไม่มีชื่ออยู่ในสล็อตแก๊ง กรุณาติดต่อแอดมินเพื่อลงทะเบียนเข้าสล็อตก่อนครับ", ephemeral=True)

        await interaction.response.send_message(
            content=f"🔄 **อัปเดตเลเวลอาวุธสำหรับสล็อต {user_slot_key} ({interaction.user.display_name})**",
            view=MemberWeaponUpdateView(user_slot_key),
            ephemeral=True
        )

    @discord.ui.button(label="⚙️ จัดการสล็อต/รายชื่อ", style=discord.ButtonStyle.secondary, custom_id="persistent_weapon_admin_btn")
    async def admin_manage_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        user_role_ids = [role.id for role in interaction.user.roles]
        if not any(r_id in WEAPON_ADMIN_ROLES for r_id in user_role_ids):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้งานเมนูนี้ครับ", ephemeral=True)

        await interaction.response.send_message(
            content="⚙️ **ระบบจัดการสล็อตและตั้งค่าบอร์ดอาวุธ (สำหรับแอดมิน)**",
            view=AdminWeaponManageView(),
            ephemeral=True
        )


# --- 9. ระบบ Backup (แก้ไขให้ส่งเฉพาะคนกด และแยกไฟล์ตาม Guild) ---
@bot.command()
@commands.has_any_role("Admin", "ผู้ดูแล")
async def backup(ctx):
    # แก้ไข Logic: ระบุ Path ไฟล์ของเซิร์ฟเวอร์ปัจจุบัน
    gid = str(ctx.guild.id)
    path_leaves = get_path(gid, "leaves")
    path_config = get_path(gid, "config")
    
    # แก้ไข Logic: ส่ง DM เฉพาะหา ctx.author (คนพิมพ์คำสั่ง) เท่านั้น
    try:
        f_send = []
        if os.path.exists(path_leaves): f_send.append(discord.File(path_leaves))
        if os.path.exists(path_config): f_send.append(discord.File(path_config))
        
        if not f_send:
            return await ctx.send("❌ **ไม่พบไฟล์ข้อมูลในเซิร์ฟเวอร์นี้เพื่อทำ Backup**")
            
        await ctx.author.send(f"📦 นี่คือไฟล์ Backup ข้อมูลและการตั้งค่าของเซิร์ฟเวอร์ **{ctx.guild.name}** ครับ:", files=f_send)
        await ctx.send(f"✅ ส่งไฟล์ Backup เข้า DM ของท่าน (@{ctx.author.display_name}) เรียบร้อยแล้ว")
    except discord.Forbidden:
        await ctx.send("❌ **ไม่สามารถส่งไฟล์ได้!** โปรดเปิดการรับข้อความจาก DM (Private Message) ก่อนครับ")

# 🟢 เพิ่ม Slash Command /random สำหรับเปิดเมนูสุ่มได้โดยตรงทุกๆ คน
# 🟢 แก้ไขให้ใช้ @bot.slash_command สำหรับ Pycord
@bot.slash_command(name="random", description="🎲 เปิดเมนูสุ่มรายชื่อสมาชิก / จัดทีม (ใช้งานได้ทุกคน)")
async def random_slash_cmd(ctx: discord.ApplicationContext):
    if not ctx.guild:
        await ctx.respond("❌ คำสั่งนี้สามารถใช้งานได้ในเซิร์ฟเวอร์เท่านั้น", ephemeral=True)
        return

    members = [m for m in ctx.guild.members if not m.bot]
    if not members:
        try:
            fetched_members = [m async for m in ctx.guild.fetch_members(limit=None)]
            members = [m for m in fetched_members if not m.bot]
        except:
            pass

    if not members:
        await ctx.respond("❌ ไม่พบสมาชิกในเซิร์ฟเวอร์", ephemeral=True)
        return

    view = RandomModeView(author=ctx.user, members=members)
    text = (
        "🎲 **__เมนูเลือกรูปแบบการสุ่มรายชื่อ__**\n"
        "กรุณาเลือกรูปแบบการสุ่มที่ต้องการใช้งานด้านล่างครับ:"
    )
    await ctx.respond(content=text, view=view, ephemeral=True)


# --- ย้าย on_ready มาไว้ท้ายสุด และใส่ add_view ให้ครบ ---
@bot.event
async def on_ready():
       
    # ลงทะเบียน View ทั้งหมดเพื่อให้ปุ่มทำงานได้ตลอดกาล (Persistent Views)
    bot.add_view(LeaveMainView())              # หน้าหลักแจ้งลา
    bot.add_view(RealtimeRefreshView())        # ปุ่มรีเฟรชบอร์ด
    bot.add_view(AdminPanelView())             # หน้าหลัก !admin
    bot.add_view(CategorySelectionView())      # หน้าเลือกหมวดหมู่ (แจ้งลา/แจ้งปรับเงิน)
    bot.add_view(AdminLeaveManagementView())   # ระบบลา/จัดการใบลา
    bot.add_view(ConfirmClearView())           # หน้ากดยืนยัน Cleanup 120 วัน
    bot.add_view(WeaponBoardView())            # ⚔️ บอร์ดอัปเดตอาวุธถาวร
    
    print(f'✅ {bot.user.name} ออนไลน์เรียบร้อย | ระบบปี 2026 พร้อมใช้งาน')
    if not daily_report_task.is_running(): daily_report_task.start()
    # if not weekly_report_task.is_running(): weekly_report_task.start()

# ตรวจสอบ TOKEN และห่อรันบอทด้วย Main Guard เพื่อความปลอดภัย
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ ไม่พบ DISCORD_TOKEN ใน Environment Variables กรุณาตั้งค่าก่อนรันบอท")
    bot.run(TOKEN)