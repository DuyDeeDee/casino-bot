            
            # Determine speed order
            spd1 = c1.get_spd()
            if combat_state[c1.id]["spd_debuff_turns"] > 0:
                spd1 = int(spd1 * 0.8)
                
            spd2 = c2.get_spd()
            if combat_state[c2.id]["spd_debuff_turns"] > 0:
                spd2 = int(spd2 * 0.8)
            
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
                    burn_dmg = int(ast["max_hp"] * 0.05)
                    ast["hp"] -= burn_dmg
                    round_logs.append(f"🔥 {attacker.name} bị thiêu đốt, mất {burn_dmg} HP!")
                    ast["burn_turns"] -= 1
                    
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)
                    
                    if ast["hp"] <= 0:
                        round_logs.append(f"💀 {attacker.name} đã gục ngã vì bị bỏng thiêu đốt!")
                        if ast["dodge_buff"] > 0:
                            ast["dodge_buff"] -= 1
                        if ast["dmg_buff_turns"] > 0:
                            ast["dmg_buff_turns"] -= 1
                            if ast["dmg_buff_turns"] == 0:
                                ast["dmg_buff_mult"] = 1.0
                        if ast["shield_turns"] > 0:
                            ast["shield_turns"] -= 1
                            if ast["shield_turns"] == 0:
                                ast["reflect_pct"] = 0.0
                        if ast["spd_debuff_turns"] > 0:
                            ast["spd_debuff_turns"] -= 1
                        continue
                
                # Stun check
                if ast["stunned"] > 0:
                    round_logs.append(f"💫 {attacker.name} bị choáng, không thể ra đòn!")
                    ast["stunned"] -= 1
                    if ast["dodge_buff"] > 0:
                        ast["dodge_buff"] -= 1
                    if ast["dmg_buff_turns"] > 0:
                        ast["dmg_buff_turns"] -= 1
                        if ast["dmg_buff_turns"] == 0:
                            ast["dmg_buff_mult"] = 1.0
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    continue

                # Skill check
                is_skill_attack = False
                skill_name = ""
                dmg_multiplier = 1.0
                
                if not ast["skill_used"]:
                    if "Gojo Satoru" in attacker.name and dst["hp"] > dst["max_hp"] * 0.5:
                        is_skill_attack = True
                        skill_name = "Hổ Vồ"
                        dmg_multiplier = 1.4
                        ast["skill_used"] = True
                        dst["spd_debuff_turns"] = 2
                        round_logs.append(f"✨ {attacker.name} kích hoạt [Vô Lượng Không Xứ]!")
                        
                    elif "Goku" in attacker.name and round_cnt >= 3:
                        is_skill_attack = True
                        skill_name = "Long Hỏa"
                        dmg_multiplier = 1.6
                        ast["skill_used"] = True
                        dst["burn_turns"] = 3
                        round_logs.append(f"✨ {attacker.name} kích hoạt [Kamehameha]!")
                        
                    elif "Luffy" in attacker.name:
                        is_skill_attack = True
                        if "Gear 4" in attacker.name:
                            skill_name = "Gear 4 - Leo Bazooka"
                            round_logs.append(f"✨ {attacker.name} kích hoạt [Gear 4 - Leo Bazooka]! 🦍🤛")
                        else:
                            skill_name = "Gear 5 - Bajrang Gun"
                            round_logs.append(f"✨ {attacker.name} kích hoạt [Gear 5 - Bajrang Gun]! 🤛")
                        dmg_multiplier = 3.0
                        ast["skill_used"] = True
                        
                    elif "Luffy (Gear 5)" in attacker.name and ast["hp"] < ast["max_hp"] * 0.5:
                        is_skill_attack = True
                        skill_name = "Long Phong"
                        ast["skill_used"] = True

                # Multi-hit skill Thanh Long
                if is_skill_attack and skill_name == "Long Phong":
                    round_logs.append(f"✨ {attacker.name} kích hoạt [Cao Su Khổng Lồ]!")
                    hits_multiplier = [0.5, 0.5, 0.6]
                    for hit in range(3):
                        if dst["hp"] <= 0 or ast["hp"] <= 0:
                            break
                        dodge_chance = max(5, min(50, (defender.get_spd() - attacker.get_spd()) * 0.5 + 5 + (30.0 if dst["dodge_buff"] > 0 else 0.0) + defender.get_dodge_bonus()))
                        if random.random() * 100 < dodge_chance:
                            round_logs.append(f"💨 Đòn {hit+1} bị {defender.name} né!")
                            if "Itachi" in defender.name and not dst["skill_used"]:
                                dst["dodge_buff"] = 2
                                dst["dmg_buff_turns"] = 2
                                dst["dmg_buff_mult"] = 1.2
                                dst["skill_used"] = True
                                round_logs.append(f"✨ [{defender.name}] kích hoạt [Tsukuyomi]!")
                            continue
                            
                        base_dmg = attacker.get_atk() - (defender.get_df() / 2.0)
                        base_dmg = max(1, base_dmg) * hits_multiplier[hit]
                        
                        dmg_mult = ast["dmg_buff_mult"] * ast["permanent_dmg_buff"] * ast["next_atk_buff"]
                        if attacker.get_active_set() == "Common":
                            dmg_mult *= 1.1
                            
                        damage = int(base_dmg * dmg_mult * random.uniform(0.9, 1.1))
                        damage = max(1, damage)
                        
                        if dst["shield_turns"] > 0:
                            reduction = 0.35 if "Saitama" in defender.name else 0.50
                            damage = int(damage * (1.0 - reduction))
                            damage = max(1, damage)
                            
                        dst["hp"] -= damage
                        round_logs.append(f"⚔️ Đòn {hit+1} gây {damage} sát thương!")
                        
                        # Thanh Long skill lifesteal: heals 50% of damage dealt
                        heal_amt = int(damage * 0.50)
                        if heal_amt > 0:
                            ast["hp"] = min(ast["max_hp"], ast["hp"] + heal_amt)
                            round_logs.append(f"🩸 {attacker.name} hút {heal_amt} HP từ đòn tấn công!")
                            
                        if dst["reflect_pct"] > 0:
                            reflect_dmg = int(damage * dst["reflect_pct"])
                            reflect_dmg = max(1, reflect_dmg)
                            ast["hp"] -= reflect_dmg
                            round_logs.append(f"💥 Bị phản {reflect_dmg} sát thương!")
                            
                        check_hp_skills(attacker.id, round_logs)
                        check_hp_skills(defender.id, round_logs)
                        
                    ast["next_atk_buff"] = 1.0
                    
                    if ast["dodge_buff"] > 0:
                        ast["dodge_buff"] -= 1
                    if ast["dmg_buff_turns"] > 0:
                        ast["dmg_buff_turns"] -= 1
                        if ast["dmg_buff_turns"] == 0:
                            ast["dmg_buff_mult"] = 1.0
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    continue

                # Dodge check
                dodge_chance = max(5, min(50, (defender.get_spd() - attacker.get_spd()) * 0.5 + 5 + (30.0 if dst["dodge_buff"] > 0 else 0.0) + defender.get_dodge_bonus()))
                if random.random() * 100 < dodge_chance:
                    round_logs.append(f"💨 {attacker.name} tấn công trượt! {defender.name} né đòn!")
                    ast["next_atk_buff"] = 1.0
                    if "Itachi" in defender.name and not dst["skill_used"]:
                        dst["dodge_buff"] = 2
                        dst["dmg_buff_turns"] = 2
                        dst["dmg_buff_mult"] = 1.2
                        dst["skill_used"] = True
                        round_logs.append(f"✨ [{defender.name}] kích hoạt [Tsukuyomi]!")
                    
                    if ast["dodge_buff"] > 0:
                        ast["dodge_buff"] -= 1
                    if ast["dmg_buff_turns"] > 0:
                        ast["dmg_buff_turns"] -= 1
                        if ast["dmg_buff_turns"] == 0:
                            ast["dmg_buff_mult"] = 1.0
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    continue

                # Crit check
                crit_chance = max(5, min(75, attacker.get_luk() * 0.5 + 5 + attacker.get_crit_chance()))
                is_crit = False if is_skill_attack else (random.random() * 100 < crit_chance)

                # Damage calculate
                base_dmg = attacker.get_atk() - (defender.get_df() / 2.0)
                base_dmg = max(1, base_dmg)
                
                dmg_mult = ast["dmg_buff_mult"] * ast["permanent_dmg_buff"] * ast["next_atk_buff"] * dmg_multiplier
                if attacker.get_active_set() == "Common":
                    dmg_mult *= 1.1
                    
                damage_float = base_dmg * dmg_mult * random.uniform(0.9, 1.1)
                
                if is_crit:
                    damage = int(damage_float * 2.0)
                    damage = max(1, damage)
                    round_logs.append(f"💥 {attacker.name} tấn công chí mạng gây {damage} sát thương!")
                    if "Saitama" in defender.name and not dst["skill_used"]:
                        dst["shield_turns"] = 2
                        dst["reflect_pct"] = 0.15
                        dst["skill_used"] = True
                        round_logs.append(f"✨ [{defender.name}] kích hoạt [Thần Thể Bất Bại]!")
                else:
                    damage = int(damage_float)
                    damage = max(1, damage)
                    if is_skill_attack:
                        round_logs.append(f"✨ {attacker.name} tung [{skill_name}] gây {damage} dame!")
                    else:
                        round_logs.append(f"⚔️ {attacker.name} gây {damage} sát thương!")

                ast["next_atk_buff"] = 1.0

                if is_skill_attack and skill_name == "Long Hỏa":
                    dst["burn_turns"] = 3
                elif is_skill_attack and skill_name in ("Gear 5 - Bajrang Gun", "Gear 4 - Leo Bazooka"):
                    dst["burn_turns"] = 5
                    dst["stunned"] = 1
                    heal_amt = damage
                    if heal_amt > 0:
                        ast["hp"] = min(ast["max_hp"], ast["hp"] + heal_amt)
                        if skill_name == "Gear 4 - Leo Bazooka":
                            round_logs.append(f"⚡ {attacker.name} nén khí Boundman cực hạn hồi phục {heal_amt} HP!")
                        else:
                            round_logs.append(f"⚡ {attacker.name} thức tỉnh nhịp trống giải phóng hồi phục {heal_amt} HP!")

                if dst["shield_turns"] > 0:
                    reduction = 0.35 if "Saitama" in defender.name else 0.50
                    damage = int(damage * (1.0 - reduction))
                    damage = max(1, damage)
                    round_logs.append(f"🛡️ Khiên giảm còn {damage} sát thương!")

                dst["hp"] -= damage

                # Lifesteal for basic attacks (non-skill) - heals 10% of damage dealt
                if not is_skill_attack:
                    lifesteal_amt = int(damage * 0.10)
                    if lifesteal_amt > 0:
                        ast["hp"] = min(ast["max_hp"], ast["hp"] + lifesteal_amt)
                        round_logs.append(f"🩸 {attacker.name} hút {lifesteal_amt} HP từ đối thủ!")

                if dst["reflect_pct"] > 0:
                    reflect_dmg = int(damage * dst["reflect_pct"])
                    reflect_dmg = max(1, reflect_dmg)
                    ast["hp"] -= reflect_dmg
                    round_logs.append(f"💥 Bị phản phản {reflect_dmg} sát thương!")

                check_hp_skills(attacker.id, round_logs)
                check_hp_skills(defender.id, round_logs)

                if dst["hp"] <= 0:
                    round_logs.append(f"💀 {defender.name} đã bị hạ gục!")
                    if ast["dodge_buff"] > 0:
                        ast["dodge_buff"] -= 1
                    if ast["dmg_buff_turns"] > 0:
                        ast["dmg_buff_turns"] -= 1
                        if ast["dmg_buff_turns"] == 0:
                            ast["dmg_buff_mult"] = 1.0
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    break

                if ast["hp"] <= 0:
                    round_logs.append(f"💀 {attacker.name} gục ngã vì phản sát thương!")
                    if ast["dodge_buff"] > 0:
                        ast["dodge_buff"] -= 1
                    if ast["dmg_buff_turns"] > 0:
                        ast["dmg_buff_turns"] -= 1
                        if ast["dmg_buff_turns"] == 0:
                            ast["dmg_buff_mult"] = 1.0
                    if ast["shield_turns"] > 0:
                        ast["shield_turns"] -= 1
                        if ast["shield_turns"] == 0:
                            ast["reflect_pct"] = 0.0
                    if ast["spd_debuff_turns"] > 0:
                        ast["spd_debuff_turns"] -= 1
                    break

                # Counter-attack check
                counter_chance = max(5, min(40, defender.get_luk() * 0.4 + 5))
                if random.random() * 100 < counter_chance:
                    counter_base = defender.get_atk() - (attacker.get_df() / 2.0)
                    counter_base = max(1, counter_base) * random.uniform(0.9, 1.1)
                    
                    counter_is_crit = (random.random() * 100 < max(5, min(50, defender.get_luk() * 0.5 + 5)))
                    counter_damage = int(counter_base * (2.0 if counter_is_crit else 1.0))
                    counter_damage = max(1, counter_damage)
                    
                    if ast["shield_turns"] > 0:
                        reduction = 0.35 if "Saitama" in attacker.name else 0.50
                        counter_damage = int(counter_damage * (1.0 - reduction))
                        counter_damage = max(1, counter_damage)
                        
                    ast["hp"] -= counter_damage
                    
                    if counter_is_crit:
                        round_logs.append(f"💥 {defender.name} phản công chí mạng gây {counter_damage} dame!")
                        if "Saitama" in attacker.name and not ast["skill_used"]:
                            ast["shield_turns"] = 2
                            ast["reflect_pct"] = 0.15
                            ast["skill_used"] = True
                            round_logs.append(f"✨ [{attacker.name}] kích hoạt [Thần Thể Bất Bại]!")
                    else:
                        round_logs.append(f"💥 {defender.name} phản công gây {counter_damage} dame!")
                        
                    check_hp_skills(attacker.id, round_logs)
                    check_hp_skills(defender.id, round_logs)
                    
                    if ast["hp"] <= 0:
                        round_logs.append(f"💀 {attacker.name} bị hạ gục bởi phản đòn!")
                        if ast["dodge_buff"] > 0:
                            ast["dodge_buff"] -= 1
                        if ast["dmg_buff_turns"] > 0:
                            ast["dmg_buff_turns"] -= 1
                            if ast["dmg_buff_turns"] == 0:
                                ast["dmg_buff_mult"] = 1.0
                        if ast["shield_turns"] > 0:
                            ast["shield_turns"] -= 1
                            if ast["shield_turns"] == 0:
                                ast["reflect_pct"] = 0.0
                        if ast["spd_debuff_turns"] > 0:
                            ast["spd_debuff_turns"] -= 1
                        break

