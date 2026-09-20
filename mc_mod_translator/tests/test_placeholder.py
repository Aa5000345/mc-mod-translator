from __future__ import annotations

from mc_mod_translator.placeholder import protect, restore, validate_restore


def test_protect_percent():
    text = "Hello %s, you have %d items"
    protected, ph = protect(text)
    assert ph == ["%s", "%d"]
    assert "__PH_0__" in protected
    assert "__PH_1__" in protected


def test_protect_braces():
    protected, ph = protect("Hi {0}, welcome {name}")
    assert ph == ["{0}", "{name}"]


def test_protect_color_code():
    protected, ph = protect("§aGreen §rText")
    assert ph == ["§a", "§r"]


def test_protect_escape():
    protected, ph = protect("Line1\\nLine2")
    assert ph == ["\\n"]


def test_protect_amp_color():
    protected, ph = protect("&aGreen")
    assert ph == ["&a"]


def test_restore_exact():
    text = "Hello %s and %d"
    protected, ph = protect(text)
    # 模拟翻译后引擎返回的文本
    translated = protected.replace("Hello", "你好").replace("and", "和")
    restored = restore(translated, ph)
    assert restored == "你好 %s 和 %d"


def test_restore_tolerates_engine_spaces():
    text = "Value: {0}"
    protected, ph = protect(text)
    # 引擎偶尔会在占位符前后加空格
    mangled = protected.replace("__PH_0__", "__PH_ 0 __")
    restored = restore(mangled, ph)
    assert "{0}" in restored


def test_validate_restore_ok():
    """还原之后应当通过校验。"""
    text = "A %s B"
    protected, ph = protect(text)
    translated = protected.replace("A", "甲").replace("B", "乙")
    # 关键：先 restore 再 validate
    restored = restore(translated, ph)
    assert restored == "甲 %s 乙"
    assert validate_restore(restored, ph)


def test_validate_restore_residue():
    """译文中仍残留 __PH_N__ 视为失败。"""
    text = "A %s B"
    protected, ph = protect(text)
    assert not validate_restore(protected, ph)


def test_validate_restore_missing_placeholder():
    text = "A %s and %d"
    _, ph = protect(text)
    # 译文中缺少 %d
    assert not validate_restore("你好 %s", ph)


def test_validate_restore_no_placeholders():
    assert validate_restore("任意文本", [])


def test_validate_restore_duplicate_placeholders():
    text = "%s %s"
    _, ph = protect(text)
    assert len(ph) == 2
    # 只有 1 个 %s 还原 -> 失败
    assert not validate_restore("你好 %s", ph)
    # 2 个都还原 -> 成功
    assert validate_restore("甲 %s %s 乙", ph)