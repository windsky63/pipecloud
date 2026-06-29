from pathlib import Path
import sys
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from 初始化文件处理.init_config import FILES
from 初始化文件处理.weld_library_maintenance import maintain_weld_library


def run():
    return maintain_weld_library(
        prefab_source_file=FILES['prefab_filtered_output'],
        auto_source_file=FILES['weld_library_source'],
        library_file=FILES['weld_library'],
        work_order_file=FILES['extract_output_data'],
    )


if __name__ == '__main__':
    run()
