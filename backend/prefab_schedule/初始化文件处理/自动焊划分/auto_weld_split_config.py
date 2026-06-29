# -*- coding: utf-8 -*-
"""自动焊划分配置转发。"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

PARENT_CONFIG = Path(__file__).resolve().parents[1] / 'init_config.py'
spec = spec_from_file_location('_init_config', PARENT_CONFIG)
module = module_from_spec(spec)
spec.loader.exec_module(module)

for name in dir(module):
    if not name.startswith('_'):
        globals()[name] = getattr(module, name)
