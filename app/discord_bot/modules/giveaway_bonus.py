"""Server bonus catalog, with draft editing and versioned saves."""
import copy
import json
import time

import discord

MANAGEMENT_HINT = 'Bạn cần quyền Administrator, Quản lý Server hoặc Quản lý tin nhắn để sửa menu bonus server.'


def can_manage_catalog(member, guild):
    perms = getattr(member, 'guild_permissions', discord.Permissions.none())
    return bool(
        guild and getattr(getattr(member, 'guild', None), 'id', None) == guild.id
        and (perms.administrator or perms.manage_guild or perms.manage_messages)
    )


def as_dict(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def matching_benefits(member, benefits):
    return {str(rid): text for rid, text in benefits.items() if member.get_role(int(rid)) is not None}


class BonusCatalog:
    def __init__(self, connection):
        self.connection = connection
        connection.execute('''CREATE TABLE IF NOT EXISTS giveaway_bonus_catalog (
            guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL,
            benefit_text TEXT NOT NULL, enabled INTEGER NOT NULL,
            sort_order INTEGER NOT NULL, updated_by INTEGER NOT NULL,
            updated_at INTEGER NOT NULL, PRIMARY KEY(guild_id, role_id))''')
        connection.execute('''CREATE TABLE IF NOT EXISTS giveaway_bonus_catalog_versions (
            guild_id INTEGER PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0)''')
        connection.commit()

    def load(self, guild_id):
        row = self.connection.execute(
            'SELECT version FROM giveaway_bonus_catalog_versions WHERE guild_id=?', (guild_id,)
        ).fetchone()
        entries = self.connection.execute('''SELECT role_id, benefit_text, enabled, sort_order
            FROM giveaway_bonus_catalog WHERE guild_id=? ORDER BY sort_order, role_id''', (guild_id,)).fetchall()
        return (row[0] if row else 0), {
            str(rid): dict(text=text, enabled=bool(enabled), order=order)
            for rid, text, enabled, order in entries
        }

    def active(self, guild):
        _, entries = self.load(guild.id)
        return {rid: item['text'] for rid, item in entries.items()
                if item['enabled'] and guild.get_role(int(rid)) is not None}

    def save(self, guild, member, version, entries):
        if not can_manage_catalog(member, guild):
            raise ValueError(MANAGEMENT_HINT)
        if len(entries) > 100:
            raise ValueError('Menu tối đa 100 mục; hãy xóa mục không dùng.')
        for rid, item in entries.items():
            if not str(rid).isdigit() or not 1 <= len(item['text'].strip()) <= 300:
                raise ValueError('Mỗi mục phải có role hợp lệ và quyền lợi từ 1–300 ký tự.')
            if item['enabled'] and guild.get_role(int(rid)) is None:
                raise ValueError('Có role đã bị xóa. Hãy tắt hoặc xóa mục đó trước khi lưu.')
        # Leave room for the giveaway title, prize, time and winner information.
        size = sum(len(item['text']) + len(str(rid)) + 12 for rid, item in entries.items() if item['enabled'])
        if size > 2000:
            raise ValueError('Tổng nội dung bonus đang bật quá dài (tối đa 2000 ký tự kể cả role). Hãy rút gọn hoặc tắt bớt mục.')
        conn = self.connection
        conn.execute('SAVEPOINT bonus_catalog_save')
        try:
            conn.execute('INSERT OR IGNORE INTO giveaway_bonus_catalog_versions VALUES (?, 0)', (guild.id,))
            changed = conn.execute('''UPDATE giveaway_bonus_catalog_versions SET version=version+1
                WHERE guild_id=? AND version=?''', (guild.id, version)).rowcount
            if not changed:
                raise ValueError('Admin khác đã cập nhật menu. Đóng bảng và mở setup lại để lấy bản mới.')
            conn.execute('DELETE FROM giveaway_bonus_catalog WHERE guild_id=?', (guild.id,))
            conn.executemany('INSERT INTO giveaway_bonus_catalog VALUES (?, ?, ?, ?, ?, ?, ?)', [
                (guild.id, int(rid), item['text'].strip(), int(item['enabled']), item['order'], member.id, int(time.time()))
                for rid, item in entries.items()
            ])
            conn.execute('RELEASE SAVEPOINT bonus_catalog_save')
        except Exception:
            conn.execute('ROLLBACK TO SAVEPOINT bonus_catalog_save')
            conn.execute('RELEASE SAVEPOINT bonus_catalog_save')
            raise
        return version + 1


class BonusPages(discord.ui.View):
    def __init__(self, user_id, title, lines):
        super().__init__(timeout=600)
        self.user_id, self.title, self.lines = user_id, title, lines or ['Chưa có mục bonus phù hợp.']
        self.page = 0
        self.message = None

    def embed(self):
        pages = max(1, (len(self.lines) + 4) // 5)
        self.page = max(0, min(self.page, pages - 1))
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page == pages - 1
        result = discord.Embed(title=self.title[:256], description='\n\n'.join(self.lines[self.page*5:self.page*5+5]), color=discord.Color.gold())
        result.set_footer(text=f'Trang {self.page+1}/{pages} • Quyền lợi theo điều kiện mô tả; bot không tự phát quà.')
        return result

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Hãy dùng lệnh để mở menu riêng của bạn.', ephemeral=True)
            return False
        return True

    async def refresh(self, interaction):
        await interaction.response.edit_message(embed=self.embed(), view=self, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label='← Trước', row=3)
    async def previous(self, interaction, button):
        self.page -= 1
        await self.refresh(interaction)

    @discord.ui.button(label='Sau →', row=3)
    async def next_page(self, interaction, button):
        self.page += 1
        await self.refresh(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class CatalogRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Chọn role để thêm hoặc sửa quyền lợi', row=0)

    async def callback(self, interaction):
        await interaction.response.send_modal(CatalogBenefitModal(self.view, self.values[0]))


class CatalogBenefitModal(discord.ui.Modal):
    def __init__(self, view, role):
        super().__init__(title='Quyền lợi theo role')
        self.editor, self.role = view, role
        current = view.entries.get(str(role.id), {})
        self.benefit = discord.ui.TextInput(label='Quyền lợi / điều kiện áp dụng', style=discord.TextStyle.paragraph,
            default=current.get('text', ''), max_length=300)
        self.order = discord.ui.TextInput(label='Thứ tự hiển thị (0–9999)', default=str(current.get('order', len(view.entries))), max_length=4)
        self.add_item(self.benefit)
        self.add_item(self.order)

    async def on_submit(self, interaction):
        if not await self.editor.interaction_check(interaction):
            return
        if not self.benefit.value.strip() or not self.order.value.isdigit():
            await interaction.response.send_message('Nhập quyền lợi và thứ tự bằng số từ 0–9999.', ephemeral=True)
            return
        rid = str(self.role.id)
        if rid not in self.editor.entries and len(self.editor.entries) >= 100:
            await interaction.response.send_message('Menu đã đủ 100 mục.', ephemeral=True)
            return
        self.editor.entries[rid] = dict(text=self.benefit.value.strip(), order=int(self.order.value),
            enabled=self.editor.entries.get(rid, {}).get('enabled', True))
        self.editor.selected = rid
        ordered = sorted(self.editor.entries, key=lambda key: (self.editor.entries[key]['order'], int(key)))
        self.editor.page = ordered.index(rid) // 5
        await self.editor.refresh(interaction)


class CatalogEntrySelect(discord.ui.Select):
    def __init__(self, view, items):
        options = []
        for rid, entry in items:
            role = view.guild.get_role(int(rid))
            options.append(discord.SelectOption(label=(role.name if role else f'Role đã xóa: {rid}')[:100],
                value=rid, description=('Bật' if entry['enabled'] else 'Tắt'), default=rid == view.selected))
        super().__init__(placeholder='Chọn mục trên trang để bật/tắt hoặc xóa', options=options, row=1)

    async def callback(self, interaction):
        self.view.selected = self.values[0]
        await self.view.refresh(interaction)


class CatalogEditor(BonusPages):
    def __init__(self, store, guild, member):
        super().__init__(member.id, 'Bản nháp menu bonus server', [])
        self.store, self.guild = store, guild
        self.version, self.entries = store.load(guild.id)
        self.original = copy.deepcopy(self.entries)
        self.selected = None
        self.add_item(CatalogRoleSelect())

    async def interaction_check(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if self.is_finished() or not can_manage_catalog(interaction.user, self.guild):
            await interaction.response.send_message('Bảng đã hết hạn hoặc bạn không còn quyền quản lý menu.', ephemeral=True)
            return False
        return True

    def embed(self):
        items = sorted(self.entries.items(), key=lambda x: (x[1]['order'], int(x[0])))
        self.lines = [f"{'✅' if item['enabled'] else '⏸️'} <@&{rid}>"
            f"{' — role đã bị xóa' if self.guild.get_role(int(rid)) is None else ''}\n{item['text']}"
            for rid, item in items] or ['Chọn role ở menu bên dưới để thêm quyền lợi.']
        result = super().embed()
        for child in list(self.children):
            if isinstance(child, CatalogEntrySelect):
                self.remove_item(child)
        visible = items[self.page*5:self.page*5+5]
        if self.selected not in dict(visible):
            self.selected = None
        if visible:
            self.add_item(CatalogEntrySelect(self, visible))
        dirty = self.entries != self.original
        selected = self.entries.get(self.selected)
        self.toggle.disabled = self.delete.disabled = self.edit_entry.disabled = selected is None
        self.toggle.label = 'Tắt mục' if selected and selected['enabled'] else 'Bật mục'
        self.edit_entry.disabled = selected is None or self.guild.get_role(int(self.selected)) is None
        self.save.disabled = self.discard.disabled = not dirty
        result.title = 'Bonus server • ' + ('Có thay đổi chưa lưu' if dirty else 'Đã lưu')
        result.description = ('Chọn role để thêm/sửa → **Lưu** để áp dụng.\n'
            'Dùng chung cho server, chỉ tự áp dụng vào **giveaway mới**.\n\n' + result.description)
        result.set_footer(text=f'Trang {self.page+1}/{max(1, (len(items)+4)//5)} • {len(items)} mục • ✅ Bật / ⏸️ Tắt • Bonus quà, không phải vé quay')
        return result

    @discord.ui.button(label='Sửa mục', row=2)
    async def edit_entry(self, interaction, button):
        role = self.guild.get_role(int(self.selected)) if self.selected else None
        if role is None:
            await interaction.response.send_message('Chọn một role còn tồn tại để sửa.', ephemeral=True)
            return
        await interaction.response.send_modal(CatalogBenefitModal(self, role))

    @discord.ui.button(label='Tắt mục', row=2)
    async def toggle(self, interaction, button):
        if self.selected in self.entries:
            self.entries[self.selected]['enabled'] = not self.entries[self.selected]['enabled']
        await self.refresh(interaction)

    @discord.ui.button(label='Xóa mục', style=discord.ButtonStyle.danger, row=2)
    async def delete(self, interaction, button):
        self.entries.pop(self.selected, None)
        self.selected = None
        await self.refresh(interaction)

    @discord.ui.button(label='Xem trước', row=2)
    async def preview(self, interaction, button):
        items = sorted(self.entries.items(), key=lambda x: (x[1]['order'], int(x[0])))
        view = BonusPages(self.user_id, 'Xem trước menu — bản nháp', [
            f'<@&{rid}>\n{item["text"]}' for rid, item in items
            if item['enabled'] and self.guild.get_role(int(rid)) is not None
        ])
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())
        view.message = await interaction.original_response()

    @discord.ui.button(label='Lưu', style=discord.ButtonStyle.success, row=3)
    async def save(self, interaction, button):
        if not await self.interaction_check(interaction):
            return
        try:
            self.version = self.store.save(self.guild, interaction.user, self.version, self.entries)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        self.original = copy.deepcopy(self.entries)
        await self.refresh(interaction)

    @discord.ui.button(label='Hoàn tác', row=3)
    async def discard(self, interaction, button):
        self.entries = copy.deepcopy(self.original)
        self.selected = None
        await self.refresh(interaction)
