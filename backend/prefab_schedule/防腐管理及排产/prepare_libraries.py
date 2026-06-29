from pathlib import Path
import shutil
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import prepare_output_file
from project_config import LIBRARY_DIR


SOURCE_PIPE_LIBRARY = LIBRARY_DIR / '管子材料库.xlsx'
SOURCE_FITTING_LIBRARY = LIBRARY_DIR / '管件法兰材料库.xlsx'
ANTI_PIPE_LIBRARY = LIBRARY_DIR / '防腐管子材料库.xlsx'
ANTI_FITTING_LIBRARY = LIBRARY_DIR / '防腐管件法兰材料库.xlsx'


def _copy_library(source_file, target_file):
    source_file = Path(source_file)
    target_file = Path(target_file)
    if not source_file.exists():
        raise FileNotFoundError(f'源材料库不存在：{source_file}')

    target_file.parent.mkdir(parents=True, exist_ok=True)
    prepare_output_file(target_file)
    shutil.copy2(source_file, target_file)
    return target_file


def prepare_anti_corrosion_libraries():
    pipe_target = _copy_library(SOURCE_PIPE_LIBRARY, ANTI_PIPE_LIBRARY)
    fitting_target = _copy_library(SOURCE_FITTING_LIBRARY, ANTI_FITTING_LIBRARY)
    return {
        'pipe_library': pipe_target,
        'fitting_library': fitting_target,
    }


if __name__ == '__main__':
    result = prepare_anti_corrosion_libraries()
    print(f"已复制防腐管子材料库：{result['pipe_library']}")
    print(f"已复制防腐管件法兰材料库：{result['fitting_library']}")
