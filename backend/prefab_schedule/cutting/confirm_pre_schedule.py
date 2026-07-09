from pathlib import Path
import shutil
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import prepare_output_file
from cutting.cutting_config import CUTTING_FILES


def _sync_pending_library(pending_file, target_file):
    pending_path = Path(pending_file)
    target_path = Path(target_file)
    if not pending_path.exists() or pending_path.stat().st_size == 0:
        raise FileNotFoundError(f'待确认文件不存在，无法同步：{pending_path}')

    backup_path = prepare_output_file(target_path)
    shutil.copy2(pending_path, target_path)
    return target_path, backup_path


def _validate_pending_libraries(file_paths):
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(f'待确认文件不存在，无法同步：{path}')


def confirm_pre_schedule(
    pending_pipe_library_file=CUTTING_FILES['pending_pipe_library'],
    pending_fitting_library_file=CUTTING_FILES['pending_fitting_library'],
    pending_anti_corrosion_pipe_library_file=CUTTING_FILES['pending_anti_corrosion_pipe_library'],
    pending_anti_corrosion_fitting_library_file=CUTTING_FILES['pending_anti_corrosion_fitting_library'],
    pipe_library_file=CUTTING_FILES['pipe_library'],
    fitting_library_file=CUTTING_FILES['fitting_library'],
    anti_corrosion_pipe_library_file=CUTTING_FILES['anti_corrosion_pipe_library'],
    anti_corrosion_fitting_library_file=CUTTING_FILES['anti_corrosion_fitting_library'],
):
    _validate_pending_libraries([
        pending_pipe_library_file,
        pending_fitting_library_file,
        pending_anti_corrosion_pipe_library_file,
        pending_anti_corrosion_fitting_library_file,
    ])
    ordinary_pipe_target, ordinary_pipe_backup = _sync_pending_library(
        pending_pipe_library_file,
        pipe_library_file,
    )
    ordinary_fitting_target, ordinary_fitting_backup = _sync_pending_library(
        pending_fitting_library_file,
        fitting_library_file,
    )
    pipe_target, pipe_backup = _sync_pending_library(
        pending_anti_corrosion_pipe_library_file,
        anti_corrosion_pipe_library_file,
    )
    fitting_target, fitting_backup = _sync_pending_library(
        pending_anti_corrosion_fitting_library_file,
        anti_corrosion_fitting_library_file,
    )
    return {
        'pipe_library': ordinary_pipe_target,
        'pipe_library_backup': ordinary_pipe_backup,
        'fitting_library': ordinary_fitting_target,
        'fitting_library_backup': ordinary_fitting_backup,
        'anti_corrosion_pipe_library': pipe_target,
        'anti_corrosion_pipe_library_backup': pipe_backup,
        'anti_corrosion_fitting_library': fitting_target,
        'anti_corrosion_fitting_library_backup': fitting_backup,
    }


if __name__ == '__main__':
    result = confirm_pre_schedule()
    print(f"已同步普通管子材料库：{result['pipe_library']}")
    print(f"已同步普通管件法兰材料库：{result['fitting_library']}")
    print(f"已同步防腐管子材料库：{result['anti_corrosion_pipe_library']}")
    if result['anti_corrosion_pipe_library_backup']:
        print(f"防腐管子材料库备份：{result['anti_corrosion_pipe_library_backup']}")
    print(f"已同步防腐管件法兰材料库：{result['anti_corrosion_fitting_library']}")
    if result['anti_corrosion_fitting_library_backup']:
        print(f"防腐管件法兰材料库备份：{result['anti_corrosion_fitting_library_backup']}")
