import random
from typing import Tuple, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import BODY_REALMS, BODY_REALM_CONFIG, DAO_FUSION_MATRIX
from app.discord_bot.modules.tutien.models import CultivatorProfile


def upgrade_body_refining(player: CultivatorProfile, herb_count: int = 0) -> Tuple[bool, str, CultivatorProfile, int]:
    """
    Upgrades player Body Refining realm (`!luyenthe` / `!toithe`).
    Requires: Realm Gate (Khí Tu), Linh Thạch, Thảo Dược Thô, Tinh Lực.
    Calculates success rate based on Base Rate + Ngộ Tính + Đạo Tâm + Mộc Linh Căn.
    Returns: (is_success, message, updated_player, consumed_herbs)
    """
    if player.body_realm_index >= len(BODY_REALMS) - 1:
        return False, "🌟 Bạn đã đạt cấp độ Luyện Thể tối cao: **Bất Diệt Thể**! Nhục thân bất hủ!", player, 0

    next_index = player.body_realm_index + 1
    cfg = BODY_REALM_CONFIG.get(next_index)
    if not cfg:
        return False, "❌ Dữ liệu cảnh giới Luyện Thể không hợp lệ!", player, 0

    # 1. Kiểm tra Cảnh Giới Khí Tu (Realm Gate)
    if player.realm_index < cfg["req_realm_index"]:
        return (
            False,
            f"🚫 **CĂN CƠ CHƯA ĐỦ!**\n"
            f"> Đột phá lên **[{cfg['to_realm']}]** yêu cầu cảnh giới tối thiểu: **{cfg['req_realm_name']}** (Hiện tại: `{player.realm_name}`).\n"
            f"> 🧘 Hãy bế quan tu luyện tu vi trước khi gượng ép tôi luyện nhục thân!",
            player,
            0
        )

    # 2. Kiểm tra Thảo Dược Thô
    if herb_count < cfg["herbs"]:
        return (
            False,
            f"🌿 **THIẾU NGUYÊN LIỆU LUYỆN THỂ!**\n"
            f"> Cần **`{cfg['herbs']}` Thảo Dược Thô** để nấu Dược Dục tôi thể (Hiện có: `{herb_count}`).\n"
            f"> ⚔️ Hãy đi Săn Yêu (`!sanyeu`) hoặc mở rương để thu thập thêm thảo dược!",
            player,
            0
        )

    # 3. Kiểm tra Linh Thạch
    if player.linh_thach < cfg["linh_thach"]:
        return (
            False,
            f"💎 **THIẾU LINH THẠCH!**\n"
            f"> Cần **`{cfg['linh_thach']:,}` Linh Thạch** để kích hoạt linh trận (Hiện có: `{player.linh_thach:,}`).",
            player,
            0
        )

    # 4. Kiểm tra Tinh Lực
    if player.tinh_luc < cfg["tinh_luc"]:
        return (
            False,
            f"⚡ **KIỆT QUỆ TINH LỰC!**\n"
            f"> Cần **`{cfg['tinh_luc']}` Tinh Lực** để vận khí tôi thể (Hiện có: `{player.tinh_luc}/{player.max_tinh_luc}`).\n"
            f"> ⏳ Hãy nghỉ ngơi hồi phục tinh lực hoặc dùng `Tiên Mật Hồi Tinh Lực`!",
            player,
            0
        )

    # Trừ tài nguyên (Linh Thạch & Tinh Lực)
    player.linh_thach -= cfg["linh_thach"]
    player.tinh_luc -= cfg["tinh_luc"]
    consumed_herbs = cfg["herbs"]

    # Tính toán Tỷ lệ thành công
    rate = cfg["base_rate"] + (player.ngo_tinh * 0.005) + (player.dao_tam * 0.003)
    if "Mộc" in player.linh_can_element:
        rate += 0.05  # Mộc Linh Căn: Sinh mệnh tràn trề +5% tỷ lệ tôi thể

    success_rate = min(0.95, max(0.20, rate))
    roll = random.random()

    if roll <= success_rate:
        # Thành công
        player.body_realm_index = next_index
        player.body_realm_name = cfg["to_realm"]
        hp_gain = int(player.max_hp * cfg["hp_gain_pct"]) + cfg["hp_gain_flat"]
        player.max_hp += hp_gain
        player.hp += hp_gain

        msg = (
            f"💪 **TÔI THỂ THÀNH CÔNG!**\n"
            f"> Bạn đã hấp thu hoàn toàn Dược Dục và đột phá Luyện Thể lên **[{player.body_realm_name}]**!\n"
            f"> 💖 **Max HP:** `+{hp_gain:,}` (Tổng HP: `{player.max_hp:,}`)\n"
            f"> 📜 *{cfg['desc']}*\n"
            f"> *(Tiêu hao: `{cfg['linh_thach']:,}` Linh Thạch, `{cfg['herbs']}` Thảo Dược, `{cfg['tinh_luc']}` Tinh Lực - Tỷ lệ: `{int(success_rate * 100)}%`)*"
        )
        return True, msg, player, consumed_herbs
    else:
        # Thất bại - Bị phản phệ nhục thân
        hp_loss = max(100, int(player.hp * 0.15))
        player.hp = max(1, player.hp - hp_loss)
        player.can_co = max(0.0, round(player.can_co - 1.0, 1))

        msg = (
            f"💥 **TÔI THỂ THẤT BẠI - DƯỢC LỰC PHẢN PHỆ!**\n"
            f"> Dược lực quá mạnh khiến kinh mạch và huyết nhục chấn động dữ dội!\n"
            f"> 🩸 Tổn thất: `- {hp_loss:,} HP`, `-1% Căn Cơ` (Căn Cơ còn: `{player.can_co}%`)\n"
            f"> 💸 Tiêu hao: `{cfg['linh_thach']:,}` Linh Thạch, `{cfg['herbs']}` Thảo Dược, `{cfg['tinh_luc']}` Tinh Lực.\n"
            f"> *(Tỷ lệ thành công: `{int(success_rate * 100)}%` - Chúc đạo hữu may mắn lần sau!)*"
        )
        return False, msg, player, consumed_herbs



def fuse_dao_domains(dao_1: str, dao_2: str) -> Optional[Dict[str, str]]:
    """
    Fuse two Dao branches into a Complex Domain (`!ngo-dao`).
    """
    pair_1 = (dao_1, dao_2)
    pair_2 = (dao_2, dao_1)
    if pair_1 in DAO_FUSION_MATRIX:
        return DAO_FUSION_MATRIX[pair_1]
    elif pair_2 in DAO_FUSION_MATRIX:
        return DAO_FUSION_MATRIX[pair_2]
    return None
