from __future__ import annotations

from mc_mod_translator.placeholder import protect, restore, validate_restore


class TestRestoreSpaceTolerance:
    """验证 restore 能处理引擎插入空格的各种变形。"""

    def test_standard(self):
        text = "Ammo: %s/%s"
        protected, ph = protect(text)
        assert protected == "Ammo: __PH_0__/__PH_1__"
        assert restore(protected, ph) == text

    def test_space_after_underscores(self):
        """MyMemory 实际表现：__ PH_0 __"""
        text = "Ammo: %s/%s"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__ PH_0 __").replace(
            "__PH_1__", "__ PH_1 __"
        )
        assert restore(mangled, ph) == text

    def test_space_after_ph_underscore(self):
        """__PH_ 0 __"""
        text = "Mode: %s"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__PH_ 0 __")
        assert restore(mangled, ph) == text

    def test_space_before_ph_underscore_only(self):
        """__ PH_0__"""
        text = "Mode: %s"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__ PH_0__")
        assert restore(mangled, ph) == text

    def test_mixed_forms_in_one_text(self):
        """同一段文本中多种变形共存。"""
        text = "%s: %s"
        protected, ph = protect(text)
        # __PH_0__ 变 __ PH_0 __；__PH_1__ 保持不变
        mangled = protected.replace("__PH_0__", "__ PH_0 __")
        assert restore(mangled, ph) == text

    def test_validate_after_restore(self):
        """先 restore 再 validate 应通过。"""
        text = "Ammo: %s/%s"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__ PH_0 __").replace(
            "__PH_1__", "__ PH_1 __"
        )
        restored = restore(mangled, ph)
        assert validate_restore(restored, ph)


class TestValidateResidue:
    """验证残留检测也识别空格变形。"""

    def test_residue_standard(self):
        text = "A %s B"
        protected, ph = protect(text)
        # 没有还原，检测应失败
        assert not validate_restore(protected, ph)

    def test_residue_with_spaces(self):
        text = "A %s B"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__ PH_0 __")
        # 没有还原，检测应失败（说明 _RESIDUE_RE 确实匹配到了空格变形）
        assert not validate_restore(mangled, ph)

    def test_residue_extra_whitespace(self):
        text = "A %s B"
        protected, ph = protect(text)
        mangled = protected.replace("__PH_0__", "__  PH_  0  __")
        assert not validate_restore(mangled, ph)


class TestNoPlaceholders:
    def test_plain_text(self):
        assert restore("任意文本", []) == "任意文本"

    def test_validate_plain(self):
        assert validate_restore("任意文本", [])


class TestEdgeCases:
    def test_out_of_range_index_kept(self):
        """索引越界时保留原样，不抛异常。"""
        text = "__PH_5__"
        # placeholders 只有 1 个，索引 5 越界
        assert restore(text, ["%s"]) == "__PH_5__"

    def test_index_match_by_number(self):
        """restore 按数字取索引，不依赖替换顺序。"""
        text = "B %s A %s"
        protected, ph = protect(text)
        # 手工调换 0/1 的位置
        mangled = protected.replace("__PH_0__", "__PH_TMP__")
        mangled = mangled.replace("__PH_1__", "__PH_0__")
        mangled = mangled.replace("__PH_TMP__", "__PH_1__")
        restored = restore(mangled, ph)
        # 按数字还原：mangled 里 __PH_1__ 应该在第一位（对应 ph[1]）
        # 结果应该是 ph[1] + " A " + ph[0]（因为数字被交换了）
        # 原 ph = ['%s', '%s']，两个占位符相同，所以看不出差别
        # 用不同类型的占位符测试
        text2 = "B %s A %d"
        protected2, ph2 = protect(text2)
        assert ph2 == ["%s", "%d"]
        mangled2 = protected2.replace("__PH_0__", "TMP")
        mangled2 = mangled2.replace("__PH_1__", "__PH_0__")
        mangled2 = mangled2.replace("TMP", "__PH_1__")
        restored2 = restore(mangled2, ph2)
        # mangled2 里第一个位置是 __PH_1__（还原成 ph2[1] = %d）
        # 第二个位置是 __PH_0__（还原成 ph2[0] = %s）
        assert restored2 == "B %d A %s"