"""Regression checks for the launcher's configuration and process ownership."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dev


class LauncherTests(unittest.TestCase):
    def test_sync_preserves_keys_and_backs_up_before_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = "# Keep my settings\nGLM_API_KEY='private-test-key'\nLLM_PROVIDER=glm\nPORT=3100\n"
            (root / ".env").write_text(original, encoding="utf-8")
            (root / ".env.example").write_text("GLM_API_KEY=\nLLM_PROVIDER=local\nPORT=3000\nPOSTGRES_PASSWORD=\nDATABASE_URL=\n", encoding="utf-8")
            with patch.object(dev, "ROOT", root):
                dev.sync_env()
                first = (root / ".env").read_bytes()
                parsed = dev.values(root / ".env")
                self.assertEqual(parsed["GLM_API_KEY"], "private-test-key")
                self.assertEqual(parsed["LLM_PROVIDER"], "glm")
                self.assertEqual(parsed["PORT"], "3100")
                self.assertTrue(parsed["POSTGRES_PASSWORD"])
                self.assertEqual(parsed["RUST_API_BASE"], "http://127.0.0.1:3100/v1")
                backups = list(root.glob(".env.backup-*.local"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(), original)
                dev.sync_env()
                self.assertEqual(first, (root / ".env").read_bytes())
                self.assertEqual(len(list(root.glob(".env.backup-*.local"))), 1)

    def test_dotenv_is_data_not_shell_and_retains_legacy_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text("GROQ_API_KEY=\n", encoding="utf-8")
            (root / ".env.llm.local").write_text("GROQ_API_KEY='$(not-a-command) # literal'\n", encoding="utf-8")
            with patch.object(dev, "ROOT", root):
                dev.sync_env()
            self.assertEqual(dev.values(root / ".env")["GROQ_API_KEY"], "$(not-a-command) # literal")

    def test_docker_mode_rejects_unrelated_database(self):
        env = {"LOCAL_INFRA": "docker", "LOCAL_SEARCH": "external", "POSTGRES_USER": "datavault", "POSTGRES_PASSWORD": "test-only", "POSTGRES_DB": "datavault", "POSTGRES_PORT": "5432", "REDIS_PORT": "6379", "DATABASE_URL": "postgres://other:other@elsewhere:5432/other", "REDIS_URL": "redis://127.0.0.1:6379"}
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL differs"):
            dev.validate_local_config(env)
        env["LOCAL_INFRA"] = "external"
        dev.validate_local_config(env)

    def test_pid_reuse_record_does_not_target_live_unrelated_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            record = dev.identity(proc.pid)
            record["created"] -= 100
            self.assertIsNone(dev.owned(record))
            dev.terminate(record)
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_terminate_owned_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            dev.terminate(dev.identity(proc.pid))
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.returncode)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_stop_includes_owned_child_processes(self):
        import psutil
        child_code = "import time; time.sleep(30)"
        parent_code = "import subprocess, sys, time; p=subprocess.Popen([sys.executable, '-c', " + repr(child_code) + "]); print(p.pid, flush=True); time.sleep(30)"
        proc = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE, text=True)
        child = None
        try:
            child = psutil.Process(int(proc.stdout.readline().strip()))
            dev.terminate(dev.identity(proc.pid))
            proc.wait(timeout=5)
            self.assertFalse(child.is_running() and child.status() != psutil.STATUS_ZOMBIE)
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if child and child.is_running():
                child.kill()

    def test_lock_rejects_concurrent_lifecycle_command(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(dev, "RUNTIME", Path(directory)):
                with dev.lifecycle_lock():
                    with self.assertRaisesRegex(RuntimeError, "Another setup/start/stop"):
                        with dev.lifecycle_lock():
                            self.fail("Concurrent lock acquired")
                self.assertFalse((Path(directory) / "lifecycle.lock").exists())


if __name__ == "__main__":
    unittest.main()
