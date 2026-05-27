import os
import pytest
from pathlib import Path
from typing import List, Dict
from utils.common import clean_env_value
from utils.cookie_manager import CookieManager, CookieSource

class CookieLoader:
    """
    Cookie安全加载与清洗器
    使用 utils.common.clean_env_value 提取 USER_COOKIE_1 和 USER_COOKIE_2
    """
    def __init__(self, logger=None):
        self.cookie_manager = CookieManager(logger)

    def load_mandatory_cookies(self, var_names: List[str]) -> Dict[str, List[Dict]]:
        """
        加载必须的 Cookie，如果任意一个缺失则 skip
        """
        results = {}
        env_file = Path(".env")
        env_map = {}
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                key, raw = line.split("=", 1)
                env_map[key.strip()] = clean_env_value(raw)

        for var_name in var_names:
            val = clean_env_value(os.getenv(var_name)) or env_map.get(var_name)
            if not val:
                pytest.skip(f"跳过测试：缺失必要的环境变量 {var_name}")

            os.environ[var_name] = val
            
            source = CookieSource(
                type="env_var",
                identifier=var_name,
                display_name=var_name
            )
            cookies = self.cookie_manager.load_cookies(source)
            if not cookies:
                pytest.skip(f"跳过测试：无法从 {var_name} 加载有效的 Cookie 数据")
            
            results[var_name] = cookies
            
        return results
