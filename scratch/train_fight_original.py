    @daga_group.command(name="train", brief="Huấn luyện gà tăng chỉ số ngẫu nhiên (cooldown 1 tiếng).")
    async def daga_train(self, ctx: commands.Context):
        active_row = self.economy.get_active_cock(ctx.author.id)
        if not active_row:
            await ctx.send("❌ Bạn chưa có chiến kê chính xuất trận nào.")
            return

        cock = Cock(active_row)
        now = int(time.time())
        cooldown = 3600 # 1 tiếng

        if now - cock.last_train < cooldown:
            seconds_left = cooldown - (now - cock.last_train)
            minutes = seconds_left // 60
            seconds = seconds_left % 60
            await ctx.send(f"⏳ **{cock.name}** đang mệt mỏi sau giáo trình huấn luyện trước. Hãy quay lại sau `{minutes} phút {seconds} giây`.")
            return

        # Train and increase random stat
        stats = ["hp", "atk", "df", "spd", "luk"]
        chosen_stat = random.choice(stats)
        stat_gain = random.randint(1, 3)

        current_val = getattr(cock, chosen_stat)
        new_val = current_val + stat_gain

        self.economy.update_cock(cock.id, last_train=now, **{chosen_stat: new_val})

        stat_names_vn = {
            "hp": "Máu (HP)",
            "atk": "Sát thương (ATK)",
            "df": "Phòng thủ (DEF)",
            "spd": "Tốc độ (SPD)",
            "luk": "May mắn (LUK)"
        }

        await ctx.send(f"🏋️‍♂️ Bạn cho **{cock.name}** tập luyện bài tập thể lực. Chiến kê tăng thêm **+{stat_gain} {stat_names_vn[chosen_stat]}**!")

        # Trigger random event check after training
        await self._trigger_random_event(ctx, cock)

    @daga_group.command(
        name="fight",
        brief="Thách đấu đá gà PvP đặt cược với người chơi khác.",
        usage="fight @user <tiền_cược>",
    )
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def daga_fight(self, ctx: commands.Context, opponent: discord.Member, bet: int = config.bot.default_bet):
        if opponent.bot:
            await ctx.send("❌ Bạn không thể thách đấu với bot!")
            return

        if opponent.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể tự thách đấu với chính mình!")
            return

        # Check user cocks
        author_cock_row = self.economy.get_active_cock(ctx.author.id)
        if not author_cock_row:
            await ctx.send("❌ Bạn chưa có chiến kê chính xuất trận. Hãy dùng `i?daga active`.")
            return

        opponent_cock_row = self.economy.get_active_cock(opponent.id)
        if not opponent_cock_row:
            await ctx.send(f"❌ Đối thủ {opponent.mention} chưa có chiến kê chính xuất trận để thi đấu.")
            return

        # Validate bet amounts
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except Exception as exc:
            await ctx.send(f"❌ **Bạn không đủ tiền cược:** {exc}")
            return

        try:
            validate_money_bet(self.economy, opponent.id, bet)
        except Exception:
            await ctx.send(f"❌ Đối thủ {opponent.mention} không có đủ tiền cược ({bet:,} VND).")
            return

        view = AcceptFightView(opponent, ctx.author, bet)
        msg = await ctx.send(f"🥊 {opponent.mention}, bạn có đồng ý lời thách đấu đá gà mức cược **{bet:,} VND** từ {ctx.author.mention} không?", view=view)

        await view.wait()

        if not view.accepted:
            return

        # Re-check money & cocks before fighting (just in case they lost it while waiting)
        author_cock_row = self.economy.get_active_cock(ctx.author.id)
        opponent_cock_row = self.economy.get_active_cock(opponent.id)
        if not author_cock_row or not opponent_cock_row:
            await ctx.send("❌ Trận đấu bị hủy: Một trong hai người chơi không còn chiến kê chính xuất trận.")
            return

        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
            validate_money_bet(self.economy, opponent.id, bet)
        except Exception:
            await ctx.send("❌ Trận đấu bị hủy: Một trong hai người chơi không còn đủ tiền đặt cược.")
            return

        # Instantiate cocks
        c1 = Cock(author_cock_row)
        c2 = Cock(opponent_cock_row)

        hp1 = c1.get_max_hp()
        hp2 = c2.get_max_hp()

        # Initialize combat states
        # Initialize combat states
        combat_state = {
            c1.id: {
                "hp": hp1,
                "max_hp": hp1,
                "skill_used": False,
                "stunned": 0,
                "dodge_buff": 0,
                "dmg_buff_turns": 0,
                "dmg_buff_mult": 1.0,
                "next_atk_buff": 1.0,
                "burn_turns": 0,
                "shield_turns": 0,
                "reflect_pct": 0.0,
                "permanent_dmg_buff": 1.0,
                "tu_linh_triggered": False,
                "rebirth_triggered": False,
                "spd_debuff_turns": 0
            },
            c2.id: {
                "hp": hp2,
                "max_hp": hp2,
                "skill_used": False,
                "stunned": 0,
                "dodge_buff": 0,
                "dmg_buff_turns": 0,
                "dmg_buff_mult": 1.0,
                "next_atk_buff": 1.0,
                "burn_turns": 0,
                "shield_turns": 0,
                "reflect_pct": 0.0,
                "permanent_dmg_buff": 1.0,
                "tu_linh_triggered": False,
                "rebirth_triggered": False,
                "spd_debuff_turns": 0
            }
        }

        def check_hp_skills(cid, logs):
            c_state = combat_state[cid]
            c_obj = c1 if cid == c1.id else c2
            name = c_obj.name
            
            # Luffy (Gear 5 / Gear 4) rebirth check
            if "Luffy" in name and c_state["hp"] <= c_state["max_hp"] * 0.10 and not c_state["rebirth_triggered"]:
                heal = c_state["max_hp"]
                c_state["hp"] = heal
                c_state["permanent_dmg_buff"] = 1.5
                c_state["rebirth_triggered"] = True
                if "Gear 4" in name:
                    logs.append(f"✨ **[{c_obj.name}]** kích hoạt [Boundman - Sức Mạnh Rực Lửa]! Hồi phục 100% HP và tăng +50% sức đánh vĩnh viễn! 🦍")
                else:
                    logs.append(f"✨ **[{c_obj.name}]** kích hoạt [Trống Giải Phóng - Gear 5]! Hồi phục 100% HP và tăng +50% sức đánh vĩnh viễn! 🥁")
                
            if c_state["hp"] <= 0:
                return
                
            # Chu Tước: HP < 30%
            if "Chu Tước" in name and c_state["hp"] < c_state["max_hp"] * 0.3 and not c_state["skill_used"]:
                heal = int(c_state["max_hp"] * 0.3)
                c_state["hp"] = min(c_state["max_hp"], c_state["hp"] + heal)
                c_state["dmg_buff_turns"] = 3
                c_state["dmg_buff_mult"] = 1.2
                c_state["skill_used"] = True
                logs.append(f"✨ **[{c_obj.name}]** kích hoạt [Dục Hỏa]! Hồi {heal} HP, tăng +20% công trong 3 lượt!")
                
            # Kim Ô: HP < 50%
            elif "Kim Ô" in name and c_state["hp"] < c_state["max_hp"] * 0.5 and not c_state["skill_used"]:
                heal = int(c_state["max_hp"] * 0.2)
                c_state["hp"] = min(c_state["max_hp"], c_state["hp"] + heal)
                c_state["next_atk_buff"] = 1.3
                c_state["skill_used"] = True
                logs.append(f"✨ **[{c_obj.name}]** kích hoạt [Thái Dương]! Hồi {heal} HP, tăng +30% công đòn sau!")

            # Tứ Linh Set Check: HP < 20%
            if c_obj.get_active_set() == "Mythic" and c_state["hp"] < c_state["max_hp"] * 0.2 and not c_state["tu_linh_triggered"]:
                heal = int(c_state["max_hp"] * 0.15)
                c_state["hp"] = min(c_state["max_hp"], c_state["hp"] + heal)
                c_state["tu_linh_triggered"] = True
                logs.append(f"🔮 **[Bộ Tứ Linh]** Hồi sinh {heal} HP cứu sinh cho {c_obj.name}!")

        # Render initial preparation frame
        frame_data = render_fight_frame(
            c1.name, hp1, hp1, get_cock_image_file(c1.name, True),
            c2.name, hp2, hp2, get_cock_image_file(c2.name, True),
            "CHUẨN BỊ XUẤT TRẬN 🥊", f"Chiến kê của {ctx.author.display_name} thách đấu {opponent.display_name}!"
        )
        file = discord.File(frame_data, filename="battle_prep.png")
        embed = make_embed(
            title="🏟️ ĐÁ GÀ TRỰC TIẾP",
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
                        round_logs.append(f"💀 {attacker.name} đã gục ngã vì bị thiêu đốt!")
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
                    if "Bạch Hổ" in attacker.name and dst["hp"] > dst["max_hp"] * 0.5:
                        is_skill_attack = True
                        skill_name = "Hổ Vồ"
                        dmg_multiplier = 1.4
                        ast["skill_used"] = True
                        dst["spd_debuff_turns"] = 2
                        round_logs.append(f"✨ {attacker.name} kích hoạt [Hổ Vồ]!")
                        
                    elif "Xích Long" in attacker.name and round_cnt >= 3:
                        is_skill_attack = True
                        skill_name = "Long Hỏa"
                        dmg_multiplier = 1.6
                        ast["skill_used"] = True
                        dst["burn_turns"] = 3
                        round_logs.append(f"✨ {attacker.name} kích hoạt [Long Hỏa]!")
                        
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
                        
                    elif "Thanh Long" in attacker.name and ast["hp"] < ast["max_hp"] * 0.5:
                        is_skill_attack = True
                        skill_name = "Long Phong"
                        ast["skill_used"] = True

                # Multi-hit skill Thanh Long
                if is_skill_attack and skill_name == "Long Phong":
                    round_logs.append(f"✨ {attacker.name} kích hoạt [Long Phong]!")
                    hits_multiplier = [0.5, 0.5, 0.6]
                    for hit in range(3):
                        if dst["hp"] <= 0 or ast["hp"] <= 0:
                            break
                        dodge_chance = max(5, min(50, (defender.get_spd() - attacker.get_spd()) * 0.5 + 5 + (30.0 if dst["dodge_buff"] > 0 else 0.0) + defender.get_dodge_bonus()))
                        if random.random() * 100 < dodge_chance:
                            round_logs.append(f"💨 Đòn {hit+1} bị {defender.name} né!")
                            if "Hắc Kê" in defender.name and not dst["skill_used"]:
                                dst["dodge_buff"] = 2
                                dst["dmg_buff_turns"] = 2
                                dst["dmg_buff_mult"] = 1.2
                                dst["skill_used"] = True
                                round_logs.append(f"✨ [{defender.name}] kích hoạt [Bóng Đêm]!")
                            continue
                            
                        base_dmg = attacker.get_atk() - (defender.get_df() / 2.0)
                        base_dmg = max(1, base_dmg) * hits_multiplier[hit]
                        
                        dmg_mult = ast["dmg_buff_mult"] * ast["permanent_dmg_buff"] * ast["next_atk_buff"]
                        if attacker.get_active_set() == "Common":
                            dmg_mult *= 1.1
                            
                        damage = int(base_dmg * dmg_mult * random.uniform(0.9, 1.1))
                        damage = max(1, damage)
                        
                        if dst["shield_turns"] > 0:
                            reduction = 0.35 if "Huyền Vũ" in defender.name else 0.50
                            damage = int(damage * (1.0 - reduction))
                            damage = max(1, damage)
                            
                        dst["hp"] -= damage
                        round_logs.append(f"⚔️ Đòn {hit+1} gây {damage} sát thương!")
                        
                        # Thanh Long skill lifesteal: heals 50% of damage dealt
                        heal_amt = int(damage * 0.50)
                        if heal_amt > 0:
                            ast["hp"] = min(ast["max_hp"], ast["hp"] + heal_amt)
                            round_logs.append(f"🩸 {attacker.name} hút {heal_amt} HP từ đòn đánh!")
                            
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
                    round_logs.append(f"💨 {attacker.name} đánh trượt! {defender.name} né đòn!")
                    ast["next_atk_buff"] = 1.0
                    if "Hắc Kê" in defender.name and not dst["skill_used"]:
                        dst["dodge_buff"] = 2
                        dst["dmg_buff_turns"] = 2
                        dst["dmg_buff_mult"] = 1.2
                        dst["skill_used"] = True
                        round_logs.append(f"✨ [{defender.name}] kích hoạt [Bóng Đêm]!")
                    
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
                    round_logs.append(f"💥 {attacker.name} đá chí mạng gây {damage} sát thương!")
                    if "Huyền Vũ" in defender.name and not dst["skill_used"]:
                        dst["shield_turns"] = 2
                        dst["reflect_pct"] = 0.15
                        dst["skill_used"] = True
                        round_logs.append(f"✨ [{defender.name}] kích hoạt [Bất Diệt]!")
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
                    reduction = 0.35 if "Huyền Vũ" in defender.name else 0.50
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
                        reduction = 0.35 if "Huyền Vũ" in attacker.name else 0.50
                        counter_damage = int(counter_damage * (1.0 - reduction))
                        counter_damage = max(1, counter_damage)
                        
                    ast["hp"] -= counter_damage
                    
                    if counter_is_crit:
                        round_logs.append(f"💥 {defender.name} phản công chí mạng gây {counter_damage} dame!")
                        if "Huyền Vũ" in attacker.name and not ast["skill_used"]:
                            ast["shield_turns"] = 2
                            ast["reflect_pct"] = 0.15
                            ast["skill_used"] = True
                            round_logs.append(f"✨ [{attacker.name}] kích hoạt [Bất Diệt]!")
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

            battle_logs.extend(round_logs)

            if round_cnt > max_animated_rounds:
                fast_forwarded = True
                round_cnt += 1
                continue

            non_header_logs = [l for l in round_logs if not l.startswith("🟢")]
            log_preview = "\n".join(non_header_logs[-3:])
            
            frame_data = render_fight_frame(
                c1.name, combat_state[c1.id]["hp"], hp1, get_cock_image_file(c1.name, True),
                c2.name, combat_state[c2.id]["hp"], hp2, get_cock_image_file(c2.name, True),
                f"HIỆP {round_cnt} 🟢", log_preview
            )
            
            file = discord.File(frame_data, filename=f"battle_{round_cnt}.png")
            embed = make_embed(
                title="🏟️ ĐÁ GÀ TRỰC TIẾP",
                description=f"⚔️ **{c1.display_name}** vs **{c2.display_name}**",
                color=discord.Color.gold()
            )
            embed.set_image(url=f"attachment://battle_{round_cnt}.png")
            
            try:
                await message.edit(embed=embed, attachments=[file])
            except Exception as e:
                logger.error(f"Error editing battle message: {e}")
                
            await asyncio.sleep(2.0)
            round_cnt += 1

        # Sync back final HPs for the checks below
        hp1 = combat_state[c1.id]["hp"]
        hp2 = combat_state[c2.id]["hp"]

        # Determine winner
        if hp1 <= 0 and hp2 <= 0:
            winner = None
            loser = None
        elif hp1 <= 0:
            winner = opponent
            loser = ctx.author
            winner_cock = c2
            loser_cock = c1
        elif hp2 <= 0:
            winner = ctx.author
            loser = opponent
            winner_cock = c1
            loser_cock = c2
        else:
            p1 = hp1 / c1.get_max_hp()
            p2 = hp2 / c2.get_max_hp()
            if p1 > p2:
                winner = ctx.author
                loser = opponent
                winner_cock = c1
                loser_cock = c2
            elif p2 > p1:
                winner = opponent
                loser = ctx.author
                winner_cock = c2
                loser_cock = c1
            else:
                winner = None
                loser = None

        if winner is None:
            embed_title = "🤝 TRẬN ĐẤU HÒA 🤝"
            desc = f"Sau 30 hiệp tranh tài khốc liệt, cả hai chiến kê **{c1.display_name}** và **{c2.display_name}** đều kiệt sức. Trận đấu bất phân thắng bại!\nTiền cược được hoàn trả."
            embed_color = discord.Color.blue()
        else:
            self.economy.add_money(winner.id, bet)
            self.economy.add_money(loser.id, -bet)
            
            self.economy.update_cock(
                winner_cock.id,
                wins=winner_cock.wins + 1,
                streak=winner_cock.streak + 1,
                exp=winner_cock.exp + 150,
            )
            self.economy.update_cock(
                loser_cock.id,
                losses=loser_cock.losses + 1,
                streak=0,
                exp=loser_cock.exp + 20,
            )
            
            log_wallet_change(
                logger,
                event="daga_pvp_winner",
                user_id=winner.id,
                money_delta=bet,
                ctx=ctx,
                opponent_id=loser.id,
                winner_cock_id=winner_cock.id,
            )
            
            log_wallet_change(
                logger,
                event="daga_pvp_loser",
                user_id=loser.id,
                money_delta=-bet,
                ctx=ctx,
                opponent_id=winner.id,
                loser_cock_id=loser_cock.id,
            )
            
            winner_row = self.economy.get_cock(winner_cock.id)
            loser_row = self.economy.get_cock(loser_cock.id)
            
            lvl_up_winner_msg = ""
            if winner_row:
                lvl_up_w, start_lvl_w, end_lvl_w = self._level_up_cock(Cock(winner_row))
                if lvl_up_w:
                    lvl_up_winner_msg = f"\n🎉 **Chiến kê {winner_cock.name} đã tăng từ cấp {start_lvl_w} lên cấp {end_lvl_w}!**"
                    
            lvl_up_loser_msg = ""
            if loser_row:
                lvl_up_l, start_lvl_l, end_lvl_l = self._level_up_cock(Cock(loser_row))
                if lvl_up_l:
                    lvl_up_loser_msg = f"\n🎉 **Chiến kê {loser_cock.name} đã tăng từ cấp {start_lvl_l} lên cấp {end_lvl_l}!**"

            log_preview = "\n".join(battle_logs[-6:])
            
            embed_title = f"🏆 {winner.display_name.upper()} CHIẾN THẮNG 🏆"
            desc = (
                f"🏟️ **SÂN ĐẤU ĐÁ GÀ TRỰC TIẾP**\n"
                f"🐓 **{c1.display_name}** ({ctx.author.display_name}) vs 🐓 **{c2.display_name}** ({opponent.display_name})\n\n"
                f"📝 **Diễn biến hiệp cuối:**\n"
                f"... {log_preview}\n\n"
                f"🏆 **Người chiến thắng:** {winner.mention}\n"
                f"💰 **Số tiền nhận:** `+{bet:,} VND` (và **+150 EXP**){lvl_up_winner_msg}\n\n"
                f"💸 **Người thua cuộc:** {loser.mention}\n"
                f"📉 **Số tiền mất:** `-{bet:,} VND` (và **+20 EXP**){lvl_up_loser_msg}"
            )
            embed_color = discord.Color.green() if winner == ctx.author else discord.Color.red()

        # Render final KO/Draw frame
        if winner is None:
            final_round_text = "HÒA NHAU 🤝"
            final_log = "Trận đấu bất phân thắng bại!"
        else:
            final_round_text = "KẾT THÚC (KO) 🏆"
            final_log = f"{winner_cock.name} giành chiến thắng!"

        final_frame_data = render_fight_frame(
            c1.name, max(0, hp1), c1.get_max_hp(), get_cock_image_file(c1.name, True),
            c2.name, max(0, hp2), c2.get_max_hp(), get_cock_image_file(c2.name, True),
            final_round_text, final_log
        )
        
        final_file = discord.File(final_frame_data, filename="battle_final.png")
        embed = make_embed(
            title=embed_title,
            description=desc,
            color=embed_color,
        )
        embed.set_image(url="attachment://battle_final.png")
        
        try:
            await message.edit(embed=embed, attachments=[final_file])
        except Exception as e:
            logger.error(f"Error editing final battle message: {e}")
            await ctx.send(embed=embed, file=final_file)

        # Trigger random post-battle event checks for both players
        if winner:
            winner_row = self.economy.get_cock(winner_cock.id)
            if winner_row:
                await self._trigger_random_event(ctx, Cock(winner_row))
            loser_row = self.economy.get_cock(loser_cock.id)
            if loser_row:
                await self._trigger_random_event(ctx, Cock(loser_row))

