from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from 初始化文件处理.init_config import FILES
from 初始化文件处理.main import process_initial_files
from 初始化文件处理.weld_library_maintenance import maintain_weld_library
from 初始化文件处理.自动焊划分.main import main as split_auto_welds


def main():
    print('开始生成预制焊口库')

    if not process_initial_files():
        print('初始化文件处理失败，停止生成预制焊口库')
        return False

    if not split_auto_welds():
        print('自动焊划分失败，停止生成预制焊口库')
        return False

    result = maintain_weld_library(
        prefab_source_file=FILES['prefab_filtered_output'],
        auto_source_file=FILES['weld_library_source'],
        library_file=FILES['weld_library'],
    )
    if result is None or result.empty:
        print('焊口库生成失败')
        return False

    print(f'生成预制焊口库完成：{FILES["weld_library"]}')
    return True


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
