"""
ZIP解凍とXBRL抽出モジュール
"""
import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm


class Extractor:
    """ZIP解凍とXBRL抽出クラス"""
    
    def __init__(self, zip_dir: Path, xbrl_dir: Path):
        """
        初期化
        
        Args:
            zip_dir: ZIPファイルディレクトリ
            xbrl_dir: XBRL保存ディレクトリ
        """
        self.zip_dir = zip_dir
        self.xbrl_dir = xbrl_dir
        self.logger = logging.getLogger('edinet_downloader')
    
    def extract_xbrl_files(
        self,
        zip_path: Path,
        doc_id: str,
        year: str
    ) -> bool:
        """
        ZIPファイルからXBRLファイルを抽出
        
        Args:
            zip_path: ZIPファイルのパス
            doc_id: 書類ID
            year: 年（YYYY）
            
        Returns:
            成功時True、失敗時False
        """
        extract_dir = self.xbrl_dir / year / doc_id
        
        # 既に解凍済みの場合はスキップ
        if extract_dir.exists() and any(extract_dir.glob("*.xbrl")):
            self.logger.info(f"SKIP [{doc_id}] XBRL already extracted")
            return True
        
        try:
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # XBRLファイルのみ抽出
                xbrl_files = [
                    name for name in zip_ref.namelist()
                    if name.endswith('.xbrl')
                ]
                
                if not xbrl_files:
                    self.logger.warning(f"No XBRL files found in [{doc_id}]")
                    return False
                
                # ファイルを抽出
                for xbrl_file in xbrl_files:
                    # ファイル名からパスを取得
                    file_name = Path(xbrl_file).name
                    extract_path = extract_dir / file_name
                    
                    # ZIPから読み込んで保存
                    with zip_ref.open(xbrl_file) as source:
                        with open(extract_path, 'wb') as target:
                            target.write(source.read())
            
            self.logger.info(f"SUCCESS [{doc_id}] XBRL extracted ({len(xbrl_files)} files)")
            return True
        
        except zipfile.BadZipFile:
            self.logger.error(f"ERROR [{doc_id}] Invalid ZIP file")
            return False
        except Exception as e:
            self.logger.error(f"ERROR [{doc_id}] Extraction failed: {str(e)}")
            return False
    
    def process_year(self, year: str) -> Dict[str, str]:
        """
        指定年のZIPファイルを全て処理
        
        Args:
            year: 年（YYYY）
            
        Returns:
            {doc_id: status} の辞書
        """
        year_zip_dir = self.zip_dir / year
        if not year_zip_dir.exists():
            return {}
        
        zip_files = list(year_zip_dir.glob("*.zip"))
        if not zip_files:
            return {}
        
        results = {}
        
        with tqdm(zip_files, desc=f"Extracting [{year}]", leave=False) as pbar:
            for zip_path in pbar:
                doc_id = zip_path.stem  # .zipを除いたファイル名
                
                success = self.extract_xbrl_files(zip_path, doc_id, year)
                results[doc_id] = "SUCCESS" if success else "ERROR"
        
        return results
    
    def process_zip(self, zip_path: Path, year: str) -> bool:
        """
        単一のZIPファイルを処理
        
        Args:
            zip_path: ZIPファイルのパス
            year: 年（YYYY）
            
        Returns:
            成功時True、失敗時False
        """
        doc_id = zip_path.stem
        return self.extract_xbrl_files(zip_path, doc_id, year)
