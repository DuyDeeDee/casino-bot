"""Tests for Profile Card module (fonts, database, shortcuts, and cog)."""
import os
import unittest
from app.discord_bot.modules.profile_card_fonts import FONTS, apply_font, display_len
from app.discord_bot.modules.profile_card_db import (
    init_db,
    get_card,
    upsert_card,
    add_image,
    remove_image,
    add_shortcut,
    remove_shortcut,
    remove_all_shortcuts,
    is_keyword_taken,
    find_shortcut,
    load_shortcuts,
)
from app.discord_bot.cogs.profile_card import ProfileCard, build_profile_embed


class TestProfileCardFonts(unittest.TestCase):
    def test_fonts_available(self):
        self.assertGreaterEqual(len(FONTS), 12)
        for key in ["bold", "italic", "gothic", "bubble", "mono", "script"]:
            self.assertIn(key, FONTS)

    def test_apply_font_and_emoji_preservation(self):
        text = "Hello <:pepe:123456789> World <a:anim:987654321>"
        styled = apply_font(text, "bold")
        self.assertIn("<:pepe:123456789>", styled)
        self.assertIn("<a:anim:987654321>", styled)
        self.assertIn("𝐇𝐞𝐥𝐥𝐨", styled)
        self.assertIn("𝐖𝐨𝐫𝐥𝐝", styled)

    def test_display_len(self):
        self.assertEqual(display_len("Test"), 4)
        # Custom emoji counts as 2 chars
        self.assertEqual(display_len("A<:emoji:123>B"), 4)


class TestProfileCardDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.user_id = "test_user_999"
        self.guild_id = "test_guild_888"

    def tearDown(self):
        # Clean up test user record
        upsert_card(
            self.user_id,
            self.guild_id,
            title="",
            content="",
            footer="",
            images=[],
            shorts=[],
            color=None,
            font_title=None,
            font_content=None,
            font_footer=None,
        )
        remove_all_shortcuts(self.user_id, self.guild_id)

    def test_upsert_and_get_card(self):
        card = upsert_card(
            self.user_id,
            self.guild_id,
            title="My Title",
            content="My Content",
            footer="My Footer",
            color=0xFF00FF,
            font_title="bold",
        )
        self.assertEqual(card["title"], "My Title")

        fetched = get_card(self.user_id, self.guild_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "My Title")
        self.assertEqual(fetched["content"], "My Content")
        self.assertEqual(fetched["footer"], "My Footer")
        self.assertEqual(fetched["color"], 0xFF00FF)
        self.assertEqual(fetched["font_title"], "bold")

    def test_images_management(self):
        count1 = add_image(self.user_id, self.guild_id, "img_1.png")
        count2 = add_image(self.user_id, self.guild_id, "img_2.png")
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 2)

        card = get_card(self.user_id, self.guild_id)
        self.assertEqual(card["images"], ["img_1.png", "img_2.png"])

        removed = remove_image(self.user_id, self.guild_id, 1)
        self.assertEqual(removed, "img_1.png")

        card = get_card(self.user_id, self.guild_id)
        self.assertEqual(card["images"], ["img_2.png"])

    def test_shortcuts_management(self):
        add_shortcut(self.user_id, self.guild_id, "myname")
        load_shortcuts()

        found = find_shortcut("myname", self.guild_id)
        self.assertEqual(found, self.user_id)

        # Case insensitivity
        found_upper = find_shortcut("MYNAME", self.guild_id)
        self.assertEqual(found_upper, self.user_id)

        # Keyword taken check
        self.assertTrue(is_keyword_taken("myname", self.guild_id, "other_user"))
        self.assertFalse(is_keyword_taken("myname", self.guild_id, self.user_id))

        # Removal
        ok = remove_shortcut(self.user_id, self.guild_id, "myname")
        self.assertTrue(ok)
        self.assertIsNone(find_shortcut("myname", self.guild_id))

    def test_brand_new_user_shortcut(self):
        import time
        new_uid = f"brand_new_user_{int(time.time() * 1000)}"
        self.assertIsNone(get_card(new_uid, self.guild_id))
        card = get_card(new_uid, self.guild_id) or {}
        self.assertEqual(card.get("shorts") or [], [])
        add_shortcut(new_uid, self.guild_id, "newbie")
        self.assertEqual(find_shortcut("newbie", self.guild_id), new_uid)
        remove_all_shortcuts(new_uid, self.guild_id)


if __name__ == "__main__":
    unittest.main()
