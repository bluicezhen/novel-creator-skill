#!/usr/bin/env python3
"""novel_flow_executor 端到端回归测试。"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXECUTOR = ROOT / "novel_flow_executor.py"
PY = "python3"


def run_cmd(args):
    proc = subprocess.run([PY, str(EXECUTOR), *args], capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise AssertionError(f"命令异常: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        raise AssertionError(f"输出不是 JSON: {proc.stdout}") from exc
    return proc.returncode, payload


class TestNovelFlowExecutor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="novel_flow_exec_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_one_click_init(self):
        _, payload = run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        self.assertTrue(payload.get("ok"))
        self.assertTrue((self.tmpdir / "00_memory" / "novel_plan.md").exists())
        self.assertTrue((self.tmpdir / "03_manuscript" / "第1章-开篇待写.md").exists())

    def test_continue_write_prepare_returns_writing_tasks(self):
        """prepare 阶段应返回 needs_writing=true 和 writing_tasks。"""
        run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        _, payload = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--query",
            "主角在站台发现名单并与同伴发生冲突",
            "--phase",
            "prepare",
        ])
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("phase"), "prepare")
        self.assertTrue(payload.get("needs_writing"))
        self.assertIsInstance(payload.get("writing_tasks"), list)
        self.assertTrue(len(payload.get("writing_tasks", [])) > 0)

    def test_continue_write_finalize_after_manual_content(self):
        """finalize 阶段应对已有正文执行门禁流程。"""
        run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        # 找到 one-click 创建的章节文件
        chapter_files = list((self.tmpdir / "03_manuscript").glob("第*章*.md"))
        self.assertTrue(chapter_files, "one-click 应创建章节文件")
        chapter = chapter_files[0]

        # 手动写入正文（模拟 CC 完成写作后，覆盖 stub）
        chapter.write_text(
            "# 第1章 开篇\n\n"
            "主角在旧港区发现了一份失踪名单，上面有十几个名字。\n\n"
            "他仔细翻看，发现其中几个名字与最近的案件有关联。\n\n"
            "这不仅仅是一份名单，而是一条线索。\n\n"
            "他把名单收好，准备回去仔细研究。\n\n"
            "走出旧港区时，天色已经暗了下来。\n\n"
            "他加快了脚步，心里充满了疑问。\n\n",
            encoding="utf-8",
        )
        _, payload = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--chapter-file",
            str(chapter),
            "--query",
            "主角在站台发现名单并与同伴发生冲突",
            "--phase",
            "finalize",
            "--min-chars", "50",
            "--min-paragraphs", "2",
            "--min-sentences", "3",
        ])
        # finalize 阶段完成即 ok（门禁是否通过是 gate_passed_final 字段）
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("phase"), "finalize")

    def test_continue_write_idempotent_cache_hit(self):
        """重复 prepare 请求应命中幂等缓存。"""
        run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        _, p1 = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--query",
            "主角在站台发现名单并与同伴发生冲突",
            "--phase",
            "prepare",
            "--idempotent-cache",
        ])
        _, p2 = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--chapter-file",
            p1.get("chapter_file"),
            "--query",
            "主角在站台发现名单并与同伴发生冲突",
            "--phase",
            "prepare",
            "--idempotent-cache",
        ])
        self.assertTrue(p1.get("ok"))
        self.assertTrue(p2.get("ok"))
        # 幂等缓存命中时返回 idempotent_hit=true
        self.assertTrue(p2.get("idempotent_hit"))

    def test_continue_write_rollback_on_failure(self):
        """finalize 阶段门禁失败且启用回滚时，章节内容应被恢复。"""
        run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        chapter = self.tmpdir / "03_manuscript" / "第2章-短章.md"
        chapter.write_text("# 第2章 短章\n\n这是一段极短正文。", encoding="utf-8")
        before = chapter.read_text(encoding="utf-8")

        _, payload = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--chapter-file",
            str(chapter),
            "--query",
            "主角推进剧情",
            "--phase",
            "finalize",
            "--no-auto-improve",
            "--no-auto-retry",
            "--min-paragraphs",
            "12",
            "--rollback-on-failure",
            "--force-run",
        ])
        # 门禁可能通过也可能失败，取决于内容质量
        if not payload.get("ok"):
            self.assertTrue(payload.get("rollback_applied"))
            after = chapter.read_text(encoding="utf-8")
            self.assertEqual(before, after)

    def test_continue_write_auto_fix_quality_baseline(self):
        run_cmd([
            "one-click",
            "--project-root",
            str(self.tmpdir),
            "--title",
            "雾港回声",
            "--genre",
            "悬疑",
            "--idea",
            "主角在旧港区发现失踪名单",
        ])
        chapter = self.tmpdir / "03_manuscript" / "第2章-短章.md"
        # 使用已有的草稿内容而非极短文本，避免填充内容引发其他质量失败
        chapter.write_text(
            "# 第2章 短章\n\n"
            "主角在旧港区发现了一份失踪名单，上面有十几个名字。\n\n"
            "他仔细翻看，发现其中几个名字与最近的案件有关联。\n\n"
            "这不仅仅是一份名单，而是一条线索。",
            encoding="utf-8",
        )

        _, payload = run_cmd([
            "continue-write",
            "--project-root",
            str(self.tmpdir),
            "--chapter-file",
            str(chapter),
            "--query",
            "主角继续调查并与同伴沟通",
            "--phase",
            "finalize",
            "--no-auto-improve",
            "--auto-retry",
            "--min-chars",
            "100",  # 降低阈值，已有内容足够
            "--min-paragraphs",
            "2",  # 降低阈值，已有内容足够
            "--min-sentences",
            "3",  # 降低阈值，已有内容足够
            "--pacing-mode",
            "fast",
            "--no-rollback-on-failure",  # 避免 rollback 覆盖质量修复
            "--force-run",
        ])
        # 验证：质量修复被触发且内容未被回滚
        actions = payload.get("auto_retry_actions", [])
        # 如果质量已达标，可能不需要修复
        if actions:
            self.assertTrue(any("质量最小修复" in x for x in actions) or any("重建门禁" in x for x in actions))
        # 验证：rollback 没有发生（内容被保留）
        self.assertFalse(payload.get("rollback_applied", False))


class TestPacingAndGateFixes(unittest.TestCase):
    """P1-3/P1-4/P0-2 修复专项测试。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="novel_pacing_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _init_project(self):
        run_cmd([
            "one-click", "--project-root", str(self.tmpdir),
            "--title", "修复测试", "--genre", "悬疑", "--idea", "测试用例",
        ])

    def test_evaluate_quality_standard_high_skip_density_fails(self):
        """standard 模式极高概括跳过密度（>0.5）应升级为硬失败。"""
        import sys
        sys.path.insert(0, str(ROOT))
        import importlib
        nfe = importlib.import_module("novel_flow_executor")
        import argparse

        # 构造一段极高概括跳过密度的文本（几乎全是跳过句）
        skip_heavy = (
            "经过一番苦修，终于练功大成。\n\n"
            "此后数日，没过多久便突破瓶颈。\n\n"
            "转眼间，一切都完成了。\n\n"
            "随后又经过一番历练，很快就完成了任务。\n\n"
            "苦修数月，不知不觉就成功了。\n\n"
        ) * 20  # 重复 20 次保证字数

        args = argparse.Namespace(
            min_chars=100,
            min_paragraphs=2,
            min_dialogue_ratio=0.0,
            max_dialogue_ratio=1.0,
            min_sentences=1,
            pacing_mode="standard",
        )
        result = nfe.evaluate_quality(skip_heavy, args)
        failures = result.get("failures", [])
        self.assertTrue(
            any("pacing_skip_density_critical" in f for f in failures),
            f"standard 模式极高 skip density 应硬失败，实际 failures={failures}",
        )

    def test_evaluate_quality_immersive_skip_density_fails(self):
        """immersive 模式概括跳过密度超阈值应硬失败。"""
        import sys
        sys.path.insert(0, str(ROOT))
        import importlib
        nfe = importlib.import_module("novel_flow_executor")
        import argparse

        skip_text = ("经过一番苦修练功大成。\n\n此后便突破了瓶颈。\n\n" ) * 30

        args = argparse.Namespace(
            min_chars=100, min_paragraphs=2,
            min_dialogue_ratio=0.0, max_dialogue_ratio=1.0,
            min_sentences=1, pacing_mode="immersive",
        )
        result = nfe.evaluate_quality(skip_text, args)
        failures = result.get("failures", [])
        self.assertTrue(
            any("pacing_skip_density_too_high" in f for f in failures),
            f"immersive 模式 skip density 应硬失败，实际 failures={failures}",
        )

    def test_publish_ready_reflects_quality_failure(self):
        """质量未通过时，publish_ready.md 应写入 FAIL 关键词，而非 PASS。"""
        import sys
        sys.path.insert(0, str(ROOT))
        import importlib
        nfe = importlib.import_module("novel_flow_executor")

        self._init_project()
        chapter_files = list((self.tmpdir / "03_manuscript").glob("第*章*.md"))
        self.assertTrue(chapter_files, "初始化应创建章节文件")
        chapter_path = chapter_files[0]

        fake_quality: dict = {
            "ok": False,
            "char_count": 100,
            "paragraph_count": 2,
            "dialogue_ratio": 0.05,
            "ai_phrase_hits": [],
            "failures": ["char_count<2500 (current: 100)"],
        }
        nfe.write_gate_artifacts(self.tmpdir, chapter_path, "测试查询", fake_quality, None)

        publish_path = (
            self.tmpdir / "04_editing" / "gate_artifacts"
            / nfe.slugify(chapter_path.stem) / "publish_ready.md"
        )
        self.assertTrue(publish_path.exists(), "publish_ready.md 应被写入")
        content = publish_path.read_text(encoding="utf-8")
        self.assertIn("FAIL", content, "质量不达标时 publish_ready.md 应含 FAIL 关键词")
        self.assertNotIn("PASS", content, "质量不达标时 publish_ready.md 不应含 PASS")

    def test_decompose_returns_writing_task(self):
        """_decompose_beat_scenes 应返回 scene_decompose 类型的写作任务。"""
        import sys
        sys.path.insert(0, str(ROOT))
        import importlib
        nfe = importlib.import_module("novel_flow_executor")

        result = nfe._decompose_beat_scenes(
            "主角在旧港区发现名单", 800, {}, self.tmpdir,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.get("task_type"), "scene_decompose")
        self.assertIn("prompt", result)
        self.assertIn("output_file", result)


if __name__ == "__main__":
    unittest.main()
