"""
EDINET API v2 クライアント
"""
import time
import logging
from typing import List, Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class EdinetClient:
    """EDINET API v2 クライアントクラス"""
    
    BASE_URL = "https://disclosure.edinet-fsa.go.jp/api/v2"
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1
    
    def __init__(self, api_key: str, sleep_seconds: float = 0.2):
        """
        初期化
        
        Args:
            api_key: EDINET APIキー
            sleep_seconds: リクエスト間の待機時間（秒）
        """
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.logger = logging.getLogger('edinet_downloader')
        
        # セッション設定（リトライ機能付き）
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        # 共通ヘッダー
        self.headers = {
            "Ocp-Apim-Subscription-Key": self.api_key
        }
    
    def get_documents_list(self, date: str) -> Optional[Dict[str, Any]]:
        """
        指定日の書類一覧を取得
        
        Args:
            date: 日付（YYYY-MM-DD）
            
        Returns:
            書類一覧のJSONレスポンス、失敗時はNone
        """
        url = f"{self.BASE_URL}/documents.json"
        params = {
            "date": date,
            "type": 2  # 書類一覧取得
        }
        
        try:
            time.sleep(self.sleep_seconds)
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"書類一覧取得エラー [{date}]: {str(e)}")
            return None
    
    def filter_documents(
        self,
        documents_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        有価証券報告書のみをフィルタリング
        
        Args:
            documents_data: 書類一覧のJSONデータ
            
        Returns:
            フィルタリングされた書類リスト
        """
        if not documents_data or "results" not in documents_data:
            return []
        
        filtered = []
        for doc in documents_data["results"]:
            # 条件チェック: formCode == "030000"（有価証券報告書）のみ
            if doc.get("formCode") == "030000":
                filtered.append(doc)
        
        return filtered
    
    def download_xbrl_zip(
        self,
        doc_id: str,
        save_path: str
    ) -> bool:
        """
        XBRL ZIPファイルをダウンロード
        
        Args:
            doc_id: 書類ID
            save_path: 保存先パス
            
        Returns:
            成功時True、失敗時False
        """
        url = f"{self.BASE_URL}/documents/{doc_id}"
        params = {
            "type": 1  # XBRL ZIP取得
        }
        
        try:
            time.sleep(self.sleep_seconds)
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=60,
                stream=True
            )
            response.raise_for_status()
            
            # ファイル保存
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"XBRL ZIPダウンロードエラー [{doc_id}]: {str(e)}")
            return False
