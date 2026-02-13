"""
EDINET XBRL取得システム - メイン処理（エントリーポイント）
プロジェクトルートから実行する場合のエントリーポイント
"""
import sys
import os
from pathlib import Path

# プロジェクトルートを環境変数として設定
project_root = Path(__file__).parent
os.environ['PROJECT_ROOT'] = str(project_root)

# srcディレクトリをパスに追加
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

# src/main.pyをモジュールとしてインポートして実行
if __name__ == "__main__":
    import importlib.util
    spec = importlib.util.spec_from_file_location("edinet_main", src_dir / "main.py")
    edinet_main = importlib.util.module_from_spec(spec)
    # __file__を正しく設定
    edinet_main.__file__ = str(src_dir / "main.py")
    spec.loader.exec_module(edinet_main)
    edinet_main.main()
