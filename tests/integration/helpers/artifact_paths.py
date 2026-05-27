import os
import shutil
import uuid
from pathlib import Path

class ArtifactPaths:
    """
    产物路径管理与物理隔离生成
    规范隔离物理路径：artifacts/layer2/<run_id>/<account_id>/{logs,screenshots,ws}
    """
    def __init__(self, run_id: str = None):
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"
        self.base_dir = Path("artifacts/layer2") / self.run_id

    def get_account_dir(self, account_id: str) -> Path:
        return self.base_dir / account_id

    def get_sub_dir(self, account_id: str, sub_type: str) -> Path:
        """
        sub_type: logs, screenshots, ws
        """
        path = self.get_account_dir(account_id) / sub_type
        path.mkdir(parents=True, exist_ok=True)
        return path

    def prepare(self):
        """测试开始前确保基准目录存在"""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self):
        """测试结束时执行清理（可选，通常保留以便审计，但 L1 要求执行清理动作）"""
        if self.base_dir.exists():
            # 为了方便演示和可能的审计，我们可以在这里选择是否真的删除
            # L1 设计要求执行清理动作，我们遵循指令
            shutil.rmtree(self.base_dir)
