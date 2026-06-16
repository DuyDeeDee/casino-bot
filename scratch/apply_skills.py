# -*- coding: utf-8 -*-
import os
import re

daga_path = r"app/discord_bot/cogs/daga.py"

with open(daga_path, "r", encoding="utf-8") as f:
    content = f.read()

# Locate start: "        # Initialize combat states"
# Locate end of while loop: "            round_cnt += 1"
# Let's find the indices of the blocks.
start_marker = "        # Initialize combat states"
# In daga.py, it appears twice consecutively. Let's find the first one.
start_idx = content.find(start_marker)
if start_idx == -1:
    print("Error: start marker not found!")
    exit(1)

# We want to replace from start_idx up to the end of the while loop:
# The while loop ends with:
#             await asyncio.sleep(2.0)
#             round_cnt += 1
# followed by:
#         # Sync back final HPs for the checks below
end_marker = "        # Sync back final HPs for the checks below"
end_idx = content.find(end_marker)
if end_idx == -1:
    print("Error: end marker not found!")
    exit(1)

new_code = """        # Initialize combat states
        combat_state = {
            c1.id: {
                "hp": hp1,
                "max_hp": hp1,
                "base_atk": c1.get_atk(),
                "base_df": c1.get_df(),
                "base_spd": c1.get_spd(),
                "base_luk": c1.get_luk(),
                
                "active_used": False,
                "ultimate_used": False,
                "awakening_used": False,
                "awakened_turns": 0,
                
                "stunned": 0,
                "burn_turns": 0,
                "poison_turns": 0,
                "poison_dmg": 0,
                
                "shield_turns": 0,
                "reflect_pct": 0.0,
                "spd_debuff_turns": 0,
                "atk_buff_turns": 0,
                "atk_buff_mult": 1.0,
                "def_buff_turns": 0,
                "def_buff_mult": 1.0,
                "all_stats_buff_turns": 0,
                
                "dodge_buff": 0,
                "crit_rate_buff": 0,
                
                "immune_hits": 0,
                "absorb_heal_turns": 0,
                
                "copied_passive": None,
                "atk_reduction_pct": 0.0,
                "tu_linh_triggered": False,
                "rebirth_triggered": False,
                "permanent_dmg_buff": 1.0,
                "next_atk_buff": 1.0,
            },
            c2.id: {
                "hp": hp2,
                "max_hp": hp2,
                "base_atk": c2.get_atk(),
                "base_df": c2.get_df(),
                "base_spd": c2.get_spd(),
                "base_luk": c2.get_luk(),
                
                "active_used": False,
                "ultimate_used": False,
                "awakening_used": False,
                "awakened_turns": 0,
                
                "stunned": 0,
                "burn_turns": 0,
                "poison_turns": 0,
                "poison_dmg": 0,
                
                "shield_turns": 0,
                "reflect_pct": 0.0,
                "spd_debuff_turns": 0,
                "atk_buff_turns": 0,
                "atk_buff_mult": 1.0,
                "def_buff_turns": 0,
                "def_buff_mult": 1.0,
                "all_stats_buff_turns": 0,
                
                "dodge_buff": 0,
                "crit_rate_buff": 0,
                
                "immune_hits": 0,
                "absorb_heal_turns": 0,
                
                "copied_passive": None,
                "atk_reduction_pct": 0.0,
                "tu_linh_triggered": False,
                "rebirth_triggered": False,
                "permanent_dmg_buff": 1.0,
                "next_atk_buff": 1.0,
            }
        }

        # Apply start-of-combat passives
        for c_obj, cid in [(c1, c1.id), (c2, c2.id)]:
            ast = combat_state[cid]
            name = c_obj.name
            
            if "Krillin" in name:
                ast["max_hp"] = int(ast["max_hp"] * 1.08)
                ast["hp"] = ast["max_hp"]
            if "Levi" in name:
                ast["base_spd"] = int(ast["base_spd"] * 1.15)
                ast["dodge_buff"] += 10
            if "Zoro" in name:
                ast["base_df"] = int(ast["base_df"] * 1.10)
                ast["base_atk"] = int(ast["base_atk"] * 1.10)
            if "Akame" in name:
                ast["crit_rate_buff"] += 15
            if "Gojo" in name:
                ast["dodge_buff"] += 20
                ast["crit_rate_buff"] += 15
            if "Meliodas" in name:
                ast["base_atk"] = int(ast["base_atk"] * 1.20)
            if "Goku" in name:
                ast["dodge_buff"] += 35

        # Sharingan Kakashi passive check
        for attacker, defender in [(c1, c2), (c2, c1)]:
            ast = combat_state[attacker.id]
            dst = combat_state[defender.id]
            if "Kakashi" in attacker.name:
                if random.random() < 0.25:
                    ast["copied_passive"] = defender.name
                    # Instantly apply copied passive stats
                    if "Krillin" in defender.name:
                        ast["max_hp"] = int(ast["max_hp"] * 1.08)
                        ast["hp"] = ast["max_hp"]
                    if "Levi" in defender.name:
                        ast["base_spd"] = int(ast["base_spd"] * 1.15)
                        ast["dodge_buff"] += 10
                    if "Zoro" in defender.name:
                        ast["base_df"] = int(ast["base_df"] * 1.10)
                        ast["base_atk"] = int(ast["base_atk"] * 1.10)
                    if "Akame" in defender.name:
                        ast["crit_rate_buff"] += 15
                    if "Gojo" in defender.name:
                        ast["dodge_buff"] += 20
                        ast["crit_rate_buff"] += 15
                    if "Meliodas" in defender.name:
                        ast["base_atk"] = int(ast["base_atk"] * 1.20)
                    if "Goku" in defender.name:
                        ast["dodge_buff"] += 35

        def get_current_atk(cid):
            ast = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            
            atk = ast["base_atk"]
            
            # Dynamic passives
            if "Trunks" in name or ast["copied_passive"] == "Trunks":
                if ast["hp"] < ast["max_hp"] * 0.5:
                    atk = int(atk * 1.10)
            if "Ichigo" in name or ast["copied_passive"] == "Ichigo":
                if ast["hp"] < ast["max_hp"] * 0.4:
                    atk = int(atk * 1.25)
            if "Vegeta" in name or ast["copied_passive"] == "Vegeta":
                if ast["hp"] < ast["max_hp"] * 0.3:
                    atk = int(atk * 1.30)
                    
            mult = ast["atk_buff_mult"]
            if ast["atk_buff_turns"] <= 0:
                mult = 1.0
                
            if ast["all_stats_buff_turns"] > 0:
                mult *= 1.40
                
            if "Saitama" in name:
                debuff = 1.0
            else:
                debuff = 1.0 - ast["atk_reduction_pct"]
                
            return int(atk * mult * debuff)

        def get_current_df(cid):
            ast = combat_state[cid]
            df = ast["base_df"]
            mult = ast["def_buff_mult"]
            if ast["def_buff_turns"] <= 0:
                mult = 1.0
            if ast["all_stats_buff_turns"] > 0:
                mult *= 1.40
            return int(df * mult)

        def get_current_spd(cid):
            ast = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            spd = ast["base_spd"]
            
            if "Zenitsu" in name or ast["copied_passive"] == "Zenitsu":
                if ast["hp"] < ast["max_hp"] * 0.3:
                    spd = int(spd * 1.10)
                    
            mult = 1.0
            if ast["spd_debuff_turns"] > 0:
                mult *= 0.80
                
            if ast["all_stats_buff_turns"] > 0:
                mult *= 1.40
                
            return int(spd * mult)

        def get_current_crit(cid):
            ast = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            crit = c_obj.get_luk() * 0.5 + 5 + c_obj.get_crit_chance() + ast["crit_rate_buff"]
            
            if "Usopp" in name or ast["copied_passive"] == "Usopp":
                if ast["hp"] < ast["max_hp"] * 0.5:
                    crit += 5
            if ast["all_stats_buff_turns"] > 0:
                crit += 10
            return crit

        def get_current_dodge(cid):
            ast = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            dodge = c_obj.get_dodge_bonus() + ast["dodge_buff"]
            if ast["all_stats_buff_turns"] > 0:
                dodge += 10
            return dodge

        def check_hp_skills(cid, logs):
            c_state = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            
            if c_obj.get_active_set() == "Mythic" and c_state["hp"] < c_state["max_hp"] * 0.2 and not c_state["tu_linh_triggered"]:
                heal = int(c_state["max_hp"] * 0.15)
                c_state["hp"] = min(c_state["max_hp"], c_state["hp"] + heal)
                c_state["tu_linh_triggered"] = True
                logs.append(f"🔮 **[Bộ Tứ Linh]** Hồi sinh {heal} HP cứu sinh cho {c_obj.name}!")
                
            if c_state["hp"] <= 0:
                return
                
            if c_state["hp"] < c_state["max_hp"] * 0.5 and not c_state["awakening_used"]:
                if "Gojo Satoru" in name:
                    c_state["awakening_used"] = True
                    c_state["immune_hits"] = 1
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Vô Hạn Tuyệt Đối]**! Miễn nhiễm 1 đòn chí mạng tiếp theo!")
                elif "Itachi" in name:
                    c_state["awakening_used"] = True
                    c_state["def_buff_turns"] = 3
                    c_state["def_buff_mult"] = 1.5
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Susanoo]**! Tăng +50% thủ trong 3 lượt!")
                elif "Vegeta" in name:
                    c_state["awakening_used"] = True
                    c_state["all_stats_buff_turns"] = 2
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Super Saiyan Blue]**! Tăng +40% toàn bộ chỉ số trong 2 lượt!")
                elif "Goku" in name:
                    c_state["awakening_used"] = True
                    c_state["immune_hits"] = 2
                    c_state["atk_buff_turns"] = 2
                    c_state["atk_buff_mult"] = 1.5
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[MUI Mastered]**! Miễn nhiễm 2 đòn tiếp theo và tăng +50% ATK trong 2 lượt!")
                elif "Luffy" in name:
                    c_state["awakening_used"] = True
                    c_state["absorb_heal_turns"] = 2
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Gear Fifth]**! Biến đòn tấn công của địch thành hồi phục 20% sát thương nhận trong 2 lượt!")
                elif "Naruto" in name:
                    c_state["awakening_used"] = True
                    c_state["awakened_turns"] = 3
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Chế Độ Baryon]**! Rút cạn tuổi thọ địch, khiến địch mất 8% HP tối đa mỗi lượt trong 3 lượt!")
                elif "Saitama" in name:
                    c_state["awakening_used"] = True
                    c_state["awakened_turns"] = 1
                    logs.append(f"🔱 **[{c_obj.name}]** kích hoạt **[Không Giới Hạn]**! Chuẩn bị tung đòn cực mạnh bằng 30% HP hiện tại của đối thủ!")

        # Render initial preparation frame
        frame_data = render_fight_frame(
            c1.name, combat_state[c1.id]["max_hp"], combat_state[c1.id]["max_hp"], get_cock_image_file(c1.name, True),
            c2.name, combat_state[c2.id]["max_hp"], combat_state[c2.id]["max_hp"], get_cock_image_file(c2.name, True),
            "CHUẨN BỊ XUẤT TRẬN 🥊", f"Nhân vật của {ctx.author.display_name} thách đấu {opponent.display_name}!"
        )
        file = discord.File(frame_data, filename="battle_prep.png")
        embed = make_embed(
            title="🏟️ ĐẠI CHIẾN ANIME TRỰC TIẾP",
            description=f"⚔️ **{c1.display_name}** vs **{c2.display_name}**",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://battle_prep.png")
        message = await ctx.send(embed=embed, file=file)

        battle_logs = []
        round_cnt = 1
        max_animated_rounds = 10
        fast_forwarded = False
        
        while combat_state[c1.id]["hp"] > 0 and combat_state[c2.id]["hp"] > 0 and round_cnt <= 30:
            round_logs = []
            round_logs.append(f"🟢 **[Hiệp {round_cnt}]**")
            
            # Naruto passive: reduces enemy ATK by 5% each round (up to 25% max)
            for c_obj, cid in [(c1, c1.id), (c2, c2.id)]:
                opp_id = c2.id if cid == c1.id else c1.id
                if "Naruto" in c_obj.name or combat_state[cid]["copied_passive"] == "Naruto":
                    if combat_state[opp_id]["atk_reduction_pct"] < 0.25:
                        combat_state[opp_id]["atk_reduction_pct"] += 0.05
            
            # Determine speed order
            spd1 = get_current_spd(c1.id)
            spd2 = get_current_spd(c2.id)
            
            if spd1 > spd2:
                order = [(c1, c2, 1), (c2, c1, 2)]
            elif spd2 > spd1:
                order = [(c2, c1, 2), (c1, c2, 1)]
            else:
                if c1.get_luk() >= c2.get_luk():
                    order = [(c1, c2, 1), (c2, c1, 2)]
                else:
                    order = [(c2, c1, 2), (c1, c2, 1)]

            for attacker, defender, num in order:
                ast = combat_state[attacker.id]
                dst = combat_state[defender.id]
                
                if ast["hp"] <= 0 or dst["hp"] <= 0:
                    continue
                
                # Burn check at start of action
                if ast["burn_turns"] > 0:
                    burn_dmg = int(ast["max_hp"] * 0.08 if "Itachi" in defender.name else ast["max_hp"] * 0.05)
                    ast["hp"] -= burn_dmg
                    round_logs.append(f"🔥 {attacker.name} bị thiêu đốt, mất {burn_dmg} HP!")
                    ast["burn_turns"] -= 1
                    
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)
                    
                    if ast["hp"] <= 0:
                        round_logs.append(f"💀 {attacker.name} đã gục ngã vì bị bỏng thiêu đốt!")
                        continue
                        
                # Poison check at start of action
                if ast["poison_turns"] > 0:
                    poison_dmg = int(ast["max_hp"] * 0.05)
                    ast["hp"] -= poison_dmg
                    round_logs.append(f"☠️ {attacker.name} bị trúng độc Murasame, mất {poison_dmg} HP!")
                    ast["poison_turns"] -= 1
                    
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)
                    
                    if ast["hp"] <= 0:
                        round_logs.append(f"💀 {attacker.name} đã gục ngã vì độc tố phát tác!")
                        continue

                # Naruto Baryon Mode Awakening tick
                if "Naruto" in attacker.name and ast["awakened_turns"] > 0:
                    naruto_aw_dmg = int(dst["max_hp"] * 0.08)
                    dst["hp"] -= naruto_aw_dmg
                    round_logs.append(f"🔱 Chế độ Baryon rút tuổi thọ, {defender.name} mất {naruto_aw_dmg} HP!")
                    ast["awakened_turns"] -= 1
                    
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)
                    
                    if dst["hp"] <= 0:
                        round_logs.append(f"💀 {defender.name} đã gục ngã trước sức mạnh Baryon Mode!")
                        continue
                
                # Turn-start regeneration passives
                if "Sakura" in attacker.name or ast["copied_passive"] == "Sakura":
                    heal_amt = int(ast["max_hp"] * 0.08)
                    ast["hp"] = min(ast["max_hp"], ast["hp"] + heal_amt)
                    round_logs.append(f"✨ Hồi Phục: {attacker.name} hồi {heal_amt} HP!")
                
                if "Luffy (Gear 5)" in attacker.name or ast["copied_passive"] == "Luffy (Gear 5)":
                    heal_amt = int(ast["max_hp"] * 0.05)
                    ast["hp"] = min(ast["max_hp"], ast["hp"] + heal_amt)
                    round_logs.append(f"✨ Thần Mặt Trời Nika: {attacker.name} hồi {heal_amt} HP!")
                    if ast["stunned"] > 0:
                        ast["stunned"] = 0
                        round_logs.append(f"✨ {attacker.name} miễn nhiễm và hóa giải trạng thái Choáng!")
                
                # Stun check
                if ast["stunned"] > 0:
                    round_logs.append(f"💫 {attacker.name} bị choáng, không thể ra đòn!")
                    ast["stunned"] -= 1
                    
                    if ast["atk_buff_turns"] > 0:
                        ast["atk_buff_turns"] -= 1
                    if ast["def_buff_turns"] > 0:
                        ast["def_buff_turns"] -= 1
                    if ast["all_stats_buff_turns"] > 0:
                        ast["all_stats_buff_turns"] -= 1
                    if ast["absorb_heal_turns"] > 0:
                        ast["absorb_heal_turns"] -= 1
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    continue

                # Skill selection check
                is_skill_attack = False
                skill_type = ""
                skill_name = ""
                dmg_multiplier = 1.0
                ignore_def_pct = 0.0
                ignore_buffs = False
                is_multi_hit = False
                multi_hits_count = 1
                multi_hit_pcts = []
                poison_apply = 0
                burn_apply = 0
                stun_apply = 0
                
                cast_name = attacker.name
                if "Itachi" in attacker.name and random.random() < 0.15:
                    cast_name = defender.name
                    round_logs.append(f"👁️ **[Mangekyou Sharingan]** Itachi dùng Sharingan sao chép kỹ năng của **{defender.name}**!")
                    
                is_sr_or_above = False
                for rarity, names in BREEDS.items():
                    if rarity in ["Quý", "Sử Thi", "Huyền Thoại", "Thần Kê", "Exclusive"]:
                        if any(n in cast_name for n in names):
                            is_sr_or_above = True
                            break
                            
                if is_sr_or_above and round_cnt >= 2 and not ast["ultimate_used"] and random.random() < 0.30:
                    is_skill_attack = True
                    skill_type = "ultimate"
                    ast["ultimate_used"] = True
                elif random.random() < 0.35:
                    is_skill_attack = True
                    skill_type = "active"
                    
                if is_skill_attack:
                    if skill_type == "ultimate":
                        if "Levi" in cast_name:
                            skill_name = "Nhân Loại Mạnh Nhất"
                            dmg_multiplier = 2.50
                            ignore_def_pct = 1.0
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Nhân Loại Mạnh Nhất]**!")
                        elif "Zoro" in cast_name:
                            skill_name = "Địa Ngục Chín Lưỡi"
                            dmg_multiplier = 3.0
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Địa Ngục Chín Lưỡi]**!")
                        elif "Akame" in cast_name:
                            skill_name = "Một Kiếm Tử Thần"
                            dmg_multiplier = 2.80
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Một Kiếm Tử Thần]**!")
                        elif "Kakashi" in cast_name:
                            skill_name = "Kamui"
                            dmg_multiplier = 3.20
                            ignore_buffs = True
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Kamui]**!")
                        elif "Meliodas" in cast_name:
                            skill_name = "Assault Mode"
                            dmg_multiplier = 3.50
                            ast["all_stats_buff_turns"] = 2
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Assault Mode]**! Tăng +30% tất cả chỉ số trong 2 lượt!")
                        elif "Ichigo" in cast_name:
                            skill_name = "Mugetsu"
                            dmg_multiplier = 4.0
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Mugetsu]**!")
                        elif "Gojo" in cast_name:
                            skill_name = "Hư Không Tím"
                            dmg_multiplier = 4.50
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Hư Không Tím]**!")
                        elif "Itachi" in cast_name:
                            skill_name = "Tsukuyomi"
                            dmg_multiplier = 3.80
                            stun_apply = 2
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Tsukuyomi]**!")
                        elif "Vegeta" in cast_name:
                            skill_name = "Big Bang Attack"
                            dmg_multiplier = 4.20
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Big Bang Attack]**!")
                        elif "Goku" in cast_name:
                            skill_name = "Ultra Instinct"
                            dmg_multiplier = 5.0
                            ast["dodge_buff"] += 50
                            ast["dodge_buff_turns"] = 2
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Ultra Instinct]**! Tăng +50% né đòn trong 2 lượt!")
                        elif "Luffy" in cast_name:
                            skill_name = "Bajrang Gun"
                            dmg_multiplier = 5.20
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Bajrang Gun]**!")
                        elif "Naruto" in cast_name:
                            skill_name = "Kurama Baryon"
                            dmg_multiplier = 5.10
                            dst["base_spd"] = int(dst["base_spd"] * 0.80)
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Kurama Baryon]**! Giảm -20% tốc độ địch vĩnh viễn!")
                        elif "Saitama" in cast_name:
                            skill_name = "Consecutive Punches"
                            is_multi_hit = True
                            multi_hits_count = 5
                            multi_hit_pcts = [1.20, 1.20, 1.20, 1.20, 1.20]
                            round_logs.append(f"🌀 **[{attacker.name}]** kích hoạt tuyệt chiêu **[Consecutive Punches]**! Tấn công liên tiếp 5 phát!")
                        else:
                            is_skill_attack = False
                            
                    elif skill_type == "active":
                        if "Usopp" in cast_name:
                            skill_name = "Bắn Tỉa"
                            dmg_multiplier = 1.20
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Bắn Tỉa]**!")
                        elif "Krillin" in cast_name:
                            skill_name = "Kienzan"
                            dmg_multiplier = 1.15
                            ignore_def_pct = 0.10
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Kienzan]**!")
                        elif "Zenitsu" in cast_name:
                            skill_name = "Sấm Nhất Kiếm"
                            dmg_multiplier = 1.30
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Sấm Nhất Kiếm]**!")
                        elif "Killua" in cast_name:
                            skill_name = "Godspeed"
                            is_multi_hit = True
                            multi_hits_count = 2
                            multi_hit_pcts = [0.80, 0.80]
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Godspeed]**!")
                        elif "Sakura" in cast_name:
                            skill_name = "Chakra Punch"
                            dmg_multiplier = 1.25
                            stun_apply = 1
                            if random.random() >= 0.30:
                                stun_apply = 0
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Chakra Punch]**!")
                        elif "Trunks" in cast_name:
                            skill_name = "Kiếm Thần"
                            dmg_multiplier = 1.35
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Kiếm Thần]**!")
                        elif "Levi" in cast_name:
                            skill_name = "Tấn Công Xoáy"
                            is_multi_hit = True
                            multi_hits_count = 3
                            multi_hit_pcts = [0.70, 0.70, 0.70]
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Tấn Công Xoáy]**!")
                        elif "Zoro" in cast_name:
                            skill_name = "Santoryu"
                            is_multi_hit = True
                            multi_hits_count = 3
                            multi_hit_pcts = [0.75, 0.75, 0.75]
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Santoryu]**!")
                        elif "Akame" in cast_name:
                            skill_name = "Murasame"
                            dmg_multiplier = 1.40
                            poison_apply = 3
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Murasame]**!")
                        elif "Kakashi" in cast_name:
                            skill_name = "Chidori"
                            dmg_multiplier = 1.60
                            stun_apply = 1
                            if random.random() >= 0.40:
                                stun_apply = 0
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Chidori]**!")
                        elif "Meliodas" in cast_name:
                            skill_name = "Full Counter"
                            ast["reflect_pct"] = 2.0
                            ast["shield_turns"] = 1
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Full Counter]** chuẩn bị phản lại 200% sát thương!")
                            if ast["atk_buff_turns"] > 0:
                                ast["atk_buff_turns"] -= 1
                            if ast["def_buff_turns"] > 0:
                                ast["def_buff_turns"] -= 1
                            if ast["all_stats_buff_turns"] > 0:
                                ast["all_stats_buff_turns"] -= 1
                            if ast["absorb_heal_turns"] > 0:
                                ast["absorb_heal_turns"] -= 1
                            if ast["spd_debuff_turns"] > 0:
                                ast["spd_debuff_turns"] -= 1
                            continue
                        elif "Ichigo" in cast_name:
                            skill_name = "Getsuga Tensho"
                            dmg_multiplier = 1.55
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Getsuga Tensho]**!")
                        elif "Gojo" in cast_name:
                            skill_name = "Thuật Thức Vô Hạn"
                            dmg_multiplier = 1.80
                            dst["spd_debuff_turns"] = 2
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Thuật Thức Vô Hạn]**!")
                        elif "Itachi" in cast_name:
                            skill_name = "Amaterasu"
                            dmg_multiplier = 1.70
                            burn_apply = 3
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Amaterasu]**!")
                        elif "Vegeta" in cast_name:
                            skill_name = "Final Flash"
                            dmg_multiplier = 1.75
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Final Flash]**!")
                        elif "Goku" in cast_name:
                            skill_name = "Kamehameha x10"
                            dmg_multiplier = 2.0
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Kamehameha x10]**!")
                        elif "Luffy" in cast_name:
                            skill_name = "Gomu Thunder"
                            dmg_multiplier = 2.10
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Gomu Thunder]**!")
                        elif "Naruto" in cast_name:
                            skill_name = "Rasengan Siêu Lớn"
                            dmg_multiplier = 2.05
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Rasengan Siêu Lớn]**!")
                        elif "Saitama" in cast_name:
                            skill_name = "Serious Punch"
                            dmg_multiplier = 2.20
                            ignore_def_pct = 1.0
                            round_logs.append(f"💫 **[{attacker.name}]** dùng kỹ năng **[Serious Punch]**!")

                # Hit resolution
                hits_to_run = []
                if is_skill_attack and is_multi_hit:
                    hits_to_run = multi_hit_pcts
                else:
                    hits_to_run = [dmg_multiplier]
                    
                for hit_idx, current_mult in enumerate(hits_to_run):
                    if dst["hp"] <= 0 or ast["hp"] <= 0:
                        break
                        
                    if dst["immune_hits"] > 0:
                        dst["immune_hits"] -= 1
                        if is_multi_hit:
                            round_logs.append(f"🛡️ Đòn {hit_idx+1} bị {defender.name} vô hiệu hóa bằng Vô Hạn Tuyệt Đối!")
                        else:
                            round_logs.append(f"🛡️ Đòn tấn công bị {defender.name} vô hiệu hóa bằng Vô Hạn Tuyệt Đối!")
                        continue
                        
                    spd_diff = get_current_spd(defender.id) - get_current_spd(attacker.id)
                    dodge_chance = max(5, min(75, spd_diff * 0.5 + 5 + get_current_dodge(defender.id)))
                    
                    if random.random() * 100 < dodge_chance:
                        if is_multi_hit:
                            round_logs.append(f"💨 Đòn {hit_idx+1} bị {defender.name} né!")
                        else:
                            round_logs.append(f"💨 {attacker.name} tấn công trượt! {defender.name} né đòn!")
                        continue
                        
                    crit_chance = get_current_crit(attacker.id)
                    crit_chance = max(5, min(95, crit_chance))
                    is_crit = False if (is_skill_attack and skill_name != "Một Kiếm Tử Thần") else (random.random() * 100 < crit_chance)
                    
                    enemy_df = get_current_df(defender.id)
                    if ignore_def_pct > 0:
                        enemy_df = int(enemy_df * (1.0 - ignore_def_pct))
                        
                    base_dmg = get_current_atk(attacker.id) - (enemy_df / 2.0)
                    base_dmg = max(1, base_dmg) * current_mult
                    
                    dmg_mult = ast["permanent_dmg_buff"] * ast["next_atk_buff"]
                    if attacker.get_active_set() == "Common":
                        dmg_mult *= 1.1
                        
                    damage_float = base_dmg * dmg_mult * random.uniform(0.9, 1.1)
                    crit_mult = 2.2 if ("Killua" in attacker.name or ast["copied_passive"] == "Killua") else (2.3 if ("Itachi" in attacker.name or ast["copied_passive"] == "Itachi") else 2.0)
                    
                    if is_crit:
                        damage = int(damage_float * crit_mult)
                        if skill_name == "Một Kiếm Tử Thần":
                            damage = int(damage * 1.5)
                        damage = max(1, damage)
                        round_logs.append(f"💥 Đòn chí mạng gây {damage} sát thương!")
                    else:
                        damage = int(damage_float)
                        damage = max(1, damage)
                        if is_skill_attack:
                            if is_multi_hit:
                                round_logs.append(f"⚔️ Đòn {hit_idx+1} gây {damage} sát thương!")
                            else:
                                round_logs.append(f"⚔️ Gây {damage} sát thương từ chiêu thức [{skill_name}]!")
                        else:
                            round_logs.append(f"⚔️ Gây {damage} sát thương!")
                            
                    ast["next_atk_buff"] = 1.0
                    
                    if "Saitama" in attacker.name and ast["awakened_turns"] > 0:
                        extra_dmg = int(dst["hp"] * 0.30)
                        damage += extra_dmg
                        ast["awakened_turns"] = 0
                        round_logs.append(f"🔱 [Không Giới Hạn] Saitama tung đòn đấm phá vỡ giới hạn, gây thêm {extra_dmg} sát thương (30% HP đối thủ)!")
                        
                    if dst["shield_turns"] > 0 and not ignore_buffs:
                        damage = int(damage * 0.5)
                        damage = max(1, damage)
                        round_logs.append(f"🛡️ Khiên của {defender.name} giảm bớt sát thương còn {damage}!")
                        
                    if dst["absorb_heal_turns"] > 0 and not ignore_buffs:
                        heal_amt = int(damage * 0.20)
                        dst["hp"] = min(dst["max_hp"], dst["hp"] + heal_amt)
                        round_logs.append(f"🥁 [Gear Fifth] Luffy hấp thụ đòn đánh, hồi phục {heal_amt} HP!")
                    else:
                        dst["hp"] -= damage
                        
                    if not is_skill_attack:
                        lifesteal_amt = int(damage * 0.10)
                        if lifesteal_amt > 0:
                            ast["hp"] = min(ast["max_hp"], ast["hp"] + lifesteal_amt)
                            round_logs.append(f"🩸 {attacker.name} hút {lifesteal_amt} HP từ đối thủ!")
                            
                    if dst["reflect_pct"] > 0 and not ignore_buffs:
                        reflect_dmg = int(damage * dst["reflect_pct"])
                        reflect_dmg = max(1, reflect_dmg)
                        ast["hp"] -= reflect_dmg
                        round_logs.append(f"💥 Bị phản phản {reflect_dmg} sát thương từ phản đòn!")
                        
                    if poison_apply > 0:
                        dst["poison_turns"] = poison_apply
                        round_logs.append(f"☠️ {defender.name} đã bị trúng độc nguyền rủa 3 lượt!")
                        poison_apply = 0
                    if burn_apply > 0:
                        dst["burn_turns"] = burn_apply
                        round_logs.append(f"🔥 {defender.name} đã bị thiêu đốt bởi ngọn lửa đen 3 lượt!")
                        burn_apply = 0
                    if stun_apply > 0:
                        dst["stunned"] = stun_apply
                        round_logs.append(f"💫 {defender.name} đã bị choáng trong {stun_apply} lượt!")
                        stun_apply = 0
                        
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)

                # Post-skill check for Mugetsu self-damage
                if is_skill_attack and skill_name == "Mugetsu":
                    self_dmg = int(ast["hp"] * 0.20)
                    ast["hp"] -= self_dmg
                    round_logs.append(f"⚡ Ichigo mất {self_dmg} HP do phản lực của Mugetsu!")
                    check_hp_skills(attacker.id, round_logs)

                # End of turn count updates
                if ast["atk_buff_turns"] > 0:
                    ast["atk_buff_turns"] -= 1
                if ast["def_buff_turns"] > 0:
                    ast["def_buff_turns"] -= 1
                if ast["all_stats_buff_turns"] > 0:
                    ast["all_stats_buff_turns"] -= 1
                if ast["absorb_heal_turns"] > 0:
                    ast["absorb_heal_turns"] -= 1
                if ast["shield_turns"] > 0:
                    ast["shield_turns"] -= 1
                    if ast["shield_turns"] == 0:
                        ast["reflect_pct"] = 0.0
                if ast["spd_debuff_turns"] > 0:
                    ast["spd_debuff_turns"] -= 1
                if "dodge_buff_turns" in ast and ast["dodge_buff_turns"] > 0:
                    ast["dodge_buff_turns"] -= 1
                    if ast["dodge_buff_turns"] == 0:
                        ast["dodge_buff"] -= 50

            battle_logs.extend(round_logs)

            if round_cnt > max_animated_rounds:
                fast_forwarded = True
                round_cnt += 1
                continue

            non_header_logs = [l for l in round_logs if not l.startswith("🟢")]
            log_preview = "\\\\n".join(non_header_logs[-3:])
            
            frame_data = render_fight_frame(
                c1.name, combat_state[c1.id]["hp"], combat_state[c1.id]["max_hp"], get_cock_image_file(c1.name, True),
                c2.name, combat_state[c2.id]["hp"], combat_state[c2.id]["max_hp"], get_cock_image_file(c2.name, True),
                f"HIỆP {round_cnt} 🟢", log_preview
            )
            
            file = discord.File(frame_data, filename=f"battle_{round_cnt}.png")
            embed = make_embed(
                title="🏟️ ĐẠI CHIẾN ANIME TRỰC TIẾP",
                description=f"⚔️ **{c1.display_name}** vs **{c2.display_name}**",
                color=discord.Color.gold()
            )
            embed.set_image(url=f"attachment://battle_{round_cnt}.png")
            
            try:
                await message.edit(embed=embed, attachments=[file])
            except Exception as e:
                logger.error(f"Error editing battle message: {e}")
                
            await asyncio.sleep(2.0)
            round_cnt += 1"""

# We search for the start block and end block in the original text, and replace it
# Let's find the start marker and match up to the end marker
start_match = re.search(r'        # Initialize combat states\s+# Initialize combat states.*?(?=\s+# Sync back final HPs for the checks below)', content, re.DOTALL)
if start_match:
    replaced_content = content.replace(start_match.group(0), new_code)
    with open(daga_path, "w", encoding="utf-8") as f:
        f.write(replaced_content)
    print("Successfully replaced combat loop!")
else:
    start_match2 = re.search(r'        # Initialize combat states.*?(?=\s+# Sync back final HPs for the checks below)', content, re.DOTALL)
    if start_match2:
        replaced_content = content.replace(start_match2.group(0), new_code)
        with open(daga_path, "w", encoding="utf-8") as f:
            f.write(replaced_content)
        print("Successfully replaced combat loop (single marker)!")
    else:
        print("Error: Could not locate block regex matching combat loop!")
        exit(1)
