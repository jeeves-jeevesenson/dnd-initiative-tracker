import pathlib
import unittest


class LanInventoryUiTests(unittest.TestCase):
    SOURCE_PATH = pathlib.Path("assets/web/lan/index.html")

    def test_inventory_layout_includes_bg3_style_slots_and_backpack_list(self):
        source = self.SOURCE_PATH.read_text(encoding="utf-8")

        self.assertIn('id="inventoryHeadSelect"', source)
        self.assertIn('id="inventoryCloakSelect"', source)
        self.assertIn('id="inventoryArmourSelect"', source)
        self.assertIn('id="inventoryGlovesSelect"', source)
        self.assertIn('id="inventoryBootsSelect"', source)
        self.assertIn('id="inventoryAmuletSelect"', source)
        self.assertIn('id="inventoryRingOneSelect"', source)
        self.assertIn('id="inventoryRingTwoSelect"', source)
        self.assertIn('id="inventoryItemsList"', source)

    def test_inventory_button_opens_panel_without_toggle_hide(self):
        source = self.SOURCE_PATH.read_text(encoding="utf-8")

        self.assertIn('inventoryBtn.addEventListener("click", () => {', source)
        self.assertIn("setInventoryPanelOpen(true);", source)
        self.assertNotIn("setInventoryPanelOpen(!inventoryPanelOpen)", source)
        self.assertIn('id="inventoryModal"', source)
        self.assertIn("inventoryModal.classList.toggle(\"show\", inventoryPanelOpen);", source)

    def test_inventory_defaults_prefer_equipped_items(self):
        source = self.SOURCE_PATH.read_text(encoding="utf-8")

        self.assertIn("function isInventoryItemEquipped(item, equippedSet)", source)
        self.assertIn("Array.isArray(inventory?.equipped)", source)
        self.assertIn("const magicItems = profile?.magic_items;", source)
        self.assertIn("Array.isArray(magicItems?.equipped)", source)
        self.assertIn("const equippedDefaults = getEquippedInventoryDefaultsBySlot();", source)

    def test_inventory_slot_matching_supports_explicit_tags_and_common_armor_names(self):
        source = self.SOURCE_PATH.read_text(encoding="utf-8")

        self.assertIn("function normalizeInventorySlotTag(value)", source)
        self.assertIn("item?.equip_slot", source)
        self.assertIn('"plate"', source)
        self.assertIn('"mail"', source)
        self.assertIn('"breastplate"', source)
        self.assertIn('"leather"', source)


if __name__ == "__main__":
    unittest.main()
