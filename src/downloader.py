"""
ZIPダウンロード管理モジュール
"""
import logging
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

from edinet_client import EdinetClient


class Downloader:
    """ダウンロード管理クラス"""
    
    def __init__(self, client: EdinetClient, zip_dir: Path):
        """
        初期化
        
        Args:
            client: EDINET APIクライアント
            zip_dir: ZIP保存ディレクトリ
        """
        self.client = client
        self.zip_dir = zip_dir
        self.logger = logging.getLogger('edinet_downloader')
    
    def get_zip_path(self, doc_id: str, year: str) -> Path:
        """
        ZIPファイルの保存パスを取得
        
        Args:
            doc_id: 書類ID
            year: 年（YYYY）
            
        Returns:
            ZIPファイルのパス
        """
        year_dir = self.zip_dir / year
        year_dir.mkdir(parents=True, exist_ok=True)
        return year_dir / f"{doc_id}.zip"
    
    def download_documents(
        self,
        date: str,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        書類リストをダウンロード
        
        Args:
            date: 日付（YYYY-MM-DD）
            documents: 書類リスト
            
        Returns:
            {doc_id: status} の辞書（status: SUCCESS/SKIP/ERROR）
        """
        year = date[:4]
        results = {}
        
        if not documents:
            return results
        
        # プログレスバー表示
        with tqdm(documents, desc=f"Downloading [{date}]", leave=False) as pbar:
            for doc in pbar:
                doc_id = doc.get("docID")
                if not doc_id:
                    continue
                
                zip_path = self.get_zip_path(doc_id, year)
                
                # 既に存在する場合はスキップ
                if zip_path.exists():
                    self.logger.info(f"SKIP [{date}] [{doc_id}] ZIP already exists")
                    results[doc_id] = "SKIP"
                    continue
                
                # ダウンロード実行
                success = self.client.download_xbrl_zip(doc_id, str(zip_path))
                
                if success:
                    self.logger.info(f"SUCCESS [{date}] [{doc_id}] ZIP downloaded")
                    results[doc_id] = "SUCCESS"
                else:
                    self.logger.error(f"ERROR [{date}] [{doc_id}] ZIP download failed")
                    results[doc_id] = "ERROR"
                    # 失敗時はファイルを削除
                    if zip_path.exists():
                        zip_path.unlink()
        
        return results
