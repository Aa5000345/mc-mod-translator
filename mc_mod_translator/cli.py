from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from .cache import TranslationCache
from .config import CACHE_PATH, GLOSSARY_PATH, Config, load_config, save_config
from .engines.registry import create_engine, list_engines
from .glossary import Glossary
from .packager import build_merged_pack, build_per_mod_packs
from .progress import NullProgress, SimpleProgress
from .proofread import export_csv, import_csv
from .scanner import resolve_mods_dir, scan_mods_dir
from .scanner_preview import preview as preview_scan
from .translator import MANUAL_ENGINE, TranslatedEntry, Translator
from .versions import detect_mc_version, pack_format_for


app = typer.Typer(help="Minecraft mod 自动翻译工具", no_args_is_help=True)
proofread_app = typer.Typer(help="校对文件导入/导出")
engines_app = typer.Typer(help="翻译引擎相关")
app.add_typer(proofread_app, name="proofread")
app.add_typer(engines_app, name="engines")


def _resolve_inputs(
    mods_dir: Optional[Path], pack_root: Optional[Path]
) -> tuple[Path, Optional[Path]]:
    if mods_dir:
        d = resolve_mods_dir(mods_dir)
        if d is None:
            raise typer.BadParameter(f"无法定位 mods 目录: {mods_dir}")
        return d, pack_root
    if pack_root:
        d = resolve_mods_dir(pack_root)
        if d is None:
            raise typer.BadParameter(f"在 {pack_root} 下找不到 mods 目录")
        return d, pack_root
    raise typer.BadParameter("必须指定 --mods-dir 或 --pack-root")


def _setup_log_file(log_file: Optional[Path]) -> None:
    if not log_file:
        return
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_file),
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )
    logger.info(f"日志将写入 {log_file}")


def _auto_install(pack_root: Optional[Path], packs: list[Path]) -> None:
    if pack_root is None:
        logger.warning("未提供整合包根目录，无法自动安装")
        return
    rp = pack_root / "resourcepacks"
    rp.mkdir(parents=True, exist_ok=True)
    import shutil

    for p in packs:
        dest = rp / Path(p).name
        shutil.copy2(p, dest)
        logger.info(f"已安装: {dest}")


@app.command()
def translate(
    mods_dir: Optional[Path] = typer.Option(None, "--mods-dir", help="mods 文件夹"),
    pack_root: Optional[Path] = typer.Option(None, "--pack-root", help="整合包根目录"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="输出目录"),
    engine: Optional[str] = typer.Option(None, "--engine", help="翻译引擎"),
    mode: Optional[str] = typer.Option(None, "--mode", help="merged | per_mod"),
    mc_version: Optional[str] = typer.Option(None, "--mc-version"),
    pack_format: Optional[int] = typer.Option(None, "--pack-format"),
    target_lang: Optional[str] = typer.Option(
        None, "--target-lang", help="目标语言，例如 zh_cn / zh_tw"
    ),
    concurrency: Optional[int] = typer.Option(None, "--concurrency"),
    auto_install: bool = typer.Option(False, "--auto-install"),
    export_proof: Optional[Path] = typer.Option(None, "--export-proof"),
    merge_existing: bool = typer.Option(True, "--merge-existing/--no-merge-existing"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    no_glossary: bool = typer.Option(False, "--no-glossary"),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="日志文件路径"),
    gui: bool = typer.Option(False, "--gui", help="启动 GUI 而不是 CLI 翻译"),
):
    # --- --gui 分支：优先启动 GUI ---
    if gui:
        typer.echo("--gui 已设置，启动 GUI（忽略其他参数）", err=True)
        try:
            from .gui.main import main as gui_main
        except ImportError as e:  # noqa: BLE001
            typer.echo(f"GUI 未安装: {e}", err=True)
            raise typer.Exit(1)
        raise typer.Exit(gui_main())

    _setup_log_file(log_file)

    cfg: Config = load_config()
    if engine:
        cfg.engine = engine
    if mode:
        cfg.output_mode = mode
    if output_dir:
        cfg.output_dir = str(output_dir)
    if mc_version:
        cfg.mc_version = mc_version
    if pack_format is not None:
        cfg.pack_format = pack_format
    if target_lang:
        cfg.target_language = target_lang
    if concurrency is not None:
        cfg.concurrency = max(1, concurrency)
    if auto_install:
        cfg.auto_install = True
    cfg.merge_existing = merge_existing
    if no_cache:
        cfg.cache_enabled = False
    if no_glossary:
        cfg.glossary_enabled = False

    mods_path, resolved_root = _resolve_inputs(mods_dir, pack_root)

    detected_version = cfg.mc_version
    if detected_version is None and resolved_root is not None:
        detected_version = detect_mc_version(resolved_root)
    if detected_version is None:
        logger.warning("未能自动检测 MC 版本，默认使用 1.20.1")
        detected_version = "1.20.1"

    pf = (
        cfg.pack_format
        if cfg.pack_format is not None
        else pack_format_for(detected_version)
    )
    logger.info(
        f"目标版本: {detected_version} (pack_format={pf}), "
        f"目标语言: {cfg.target_language}"
    )

    entries = scan_mods_dir(mods_path, target_lang=cfg.target_language)
    if not entries:
        logger.error("未找到可翻译的 mod 语言文件")
        raise typer.Exit(1)
    logger.info(f"扫描到 {len(entries)} 个语言文件")

    # 预览
    stats = preview_scan(mods_path, target_lang=cfg.target_language, entries=entries)
    logger.info(f"预览: {stats.summary()}")
    if stats.unique_missing_texts == 0:
        logger.warning(
            "没有需要翻译的内容（缺失 key=0）。"
            "如果希望重新翻译，请使用 --no-merge-existing。"
        )
        raise typer.Exit(0)

    engine_cfg = cfg.engines.get(cfg.engine, {})
    eng = create_engine(cfg.engine, engine_cfg)
    logger.info(f"使用引擎: {cfg.engine}")

    cache = TranslationCache(CACHE_PATH) if cfg.cache_enabled else None
    glossary = Glossary()
    if cfg.glossary_enabled:
        glossary.load(GLOSSARY_PATH)

    sp = (
        SimpleProgress(prefix="翻译")
        if sys.stderr.isatty()
        else NullProgress()
    )

    try:
        def _progress_cb(done: int, total: int) -> None:
            sp.update(done, total)
            logger.debug(f"进度: {done}/{total}")

        tr = Translator(
            engine=eng,
            cache=cache,
            glossary=glossary,
            concurrency=cfg.concurrency,
            merge_existing=cfg.merge_existing,
            log_cb=lambda m: logger.info(m),
            progress_cb=_progress_cb,
        )

        async def _run_translation():
            try:
                return await tr.translate_entries(
                    entries, target_lang=cfg.target_language
                )
            finally:
                await eng.aclose()

        results: list[TranslatedEntry] = asyncio.run(_run_translation())
        sp.finish(f"翻译完成：{len(results)} 个语言文件")

        out_dir = Path(cfg.output_dir)
        packs: list[Path] = []
        if cfg.output_mode == "merged":
            out = out_dir / f"{cfg.resourcepack_name}.zip"
            build_merged_pack(out, results, pf, target_lang=cfg.target_language)
            packs.append(out)
            logger.info(f"已生成资源包: {out}")
        else:
            packs = build_per_mod_packs(
                out_dir, results, pf, target_lang=cfg.target_language
            )
            for p in packs:
                logger.info(f"已生成资源包: {p}")

        if export_proof:
            export_csv(export_proof, results, tgt_lang=cfg.target_language)
            logger.info(f"校对文件已导出: {export_proof}")

        if cfg.auto_install:
            _auto_install(resolved_root, packs)
    finally:
        if cache:
            cache.close()


@proofread_app.command("export")
def proofread_export(
    mods_dir: Path = typer.Option(..., "--mods-dir", help="mods 文件夹"),
    output: Path = typer.Option(..., "--output", help="输出 CSV 路径"),
    target_lang: str = typer.Option("zh_cn", "--target-lang"),
    only_modified: bool = typer.Option(
        False, "--only-modified", help="只导出已有翻译的行"
    ),
):
    """从 mods 目录中已有的翻译导出校对 CSV。"""
    entries = scan_mods_dir(mods_dir, target_lang=target_lang)
    if not entries:
        typer.echo("未找到可导出的语言文件", err=True)
        raise typer.Exit(1)
    tr_entries = [
        TranslatedEntry(entry=e, merged=dict(e.existing)) for e in entries
    ]
    export_csv(output, tr_entries, tgt_lang=target_lang, only_modified=only_modified)
    typer.echo(f"已导出 {len(tr_entries)} 个语言文件的校对 CSV 到 {output}")


@proofread_app.command("import")
def proofread_import(
    input_file: Path = typer.Option(..., "--input"),
    engine: str = typer.Option(MANUAL_ENGINE, "--engine"),
    target_lang: str = typer.Option("zh_cn", "--target-lang"),
):
    cache = TranslationCache(CACHE_PATH)
    glossary = Glossary()
    glossary.load(GLOSSARY_PATH)
    try:
        n = import_csv(
            input_file,
            cache,
            glossary,
            engine_name=engine,
            tgt_lang=target_lang,
        )
        glossary.save(GLOSSARY_PATH)
    finally:
        cache.close()
    typer.echo(f"已导入 {n} 条校对结果 (engine={engine}, target_lang={target_lang})")


@engines_app.command("list")
def engines_list():
    for name in list_engines():
        typer.echo(name)


@engines_app.command("test")
def engines_test(engine: str = typer.Option(..., "--engine")):
    cfg = load_config()
    eng = create_engine(engine, cfg.engines.get(engine, {}))

    async def _run():
        try:
            text = await eng.translate("hello", "en", "zh")
            return True, text
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
        finally:
            await eng.aclose()

    ok, info = asyncio.run(_run())
    if ok:
        typer.echo(f"OK: {info!r}")
    else:
        typer.echo(f"FAILED: {info}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()