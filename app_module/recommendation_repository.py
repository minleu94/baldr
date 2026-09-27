"""
推薦結果儲存庫 (Recommendation Result Repository)
管理推薦結果的儲存、載入、刪除
"""

import json
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import numpy as np

from app_module.recommendation.legacy_dtos import RecommendationResultDTO, RecommendationDTO


def _make_json_serializable(obj: Any) -> Any:
    """
    將對象轉換為 JSON 可序列化的格式
    
    處理：
    - numpy bool -> Python bool
    - numpy int -> Python int
    - numpy float -> Python float
    - numpy array -> list
    - 其他不可序列化的類型
    """
    # 處理 numpy 類型
    if isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    # 處理基本類型（已經可序列化）
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # 處理容器類型（遞歸處理）
    elif isinstance(obj, dict):
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    else:
        # 嘗試轉換為字符串
        try:
            return str(obj)
        except:
            return None


@dataclass
class RecommendationRun:
    """推薦結果記錄"""
    result_id: str
    result_name: str
    config: Dict[str, Any]
    regime: Optional[str]
    stock_count: int
    created_at: str
    notes: str = ""
    
    def __post_init__(self):
        """初始化後處理"""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class RecommendationRepository:
    """推薦結果儲存庫"""
    
    def __init__(self, config):
        """
        初始化儲存庫
        
        Args:
            config: TWStockConfig 實例
        """
        self.config = config
        # 儲存在 output_root/recommendation/runs/
        self.runs_dir = config.resolve_output_path('recommendation/runs')
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        
        # SQLite 資料庫
        self.db_path = self.runs_dir / "recommendation_runs.db"
        self._init_database()
    
    def _init_database(self):
        """初始化資料庫結構"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 建立 runs 表（儲存基本資訊）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT NOT NULL,
                regime TEXT,
                stock_count INTEGER,
                config TEXT,  -- JSON
                notes TEXT,
                created_at TEXT,
                data_path TEXT  -- 檔案路徑（JSON）
            )
        """)
        
        # 建立索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON runs(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime ON runs(regime)")
        
        conn.commit()
        conn.close()

    def _assert_no_canonical_execution_identity(
        self, cursor: sqlite3.Cursor, result_id: str
    ) -> None:
        """Fail closed if the new immutable namespace already claims this ID.

        This check is called inside the legacy writer's ``BEGIN IMMEDIATE``
        transaction, so it serializes with the canonical writer's identity
        reservation. The file check also protects a canonical file-only orphan
        left by a process interruption before its metadata transaction commits.
        """

        tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table_name in ("result_artifact_index", "result_artifact_metadata"):
            if table_name not in tables:
                continue
            if cursor.execute(
                f"SELECT 1 FROM {table_name} WHERE result_id = ? LIMIT 1",
                (result_id,),
            ).fetchone() is not None:
                raise RuntimeError(
                    "recommendation legacy save refused: result_id is claimed "
                    "by the canonical execution namespace"
                )

        try:
            opaque_id = result_id.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise RuntimeError(
                "recommendation legacy save cannot safely check canonical identity"
            ) from exc
        canonical_file = (
            self.runs_dir
            / "execution_artifacts"
            / f"{hashlib.sha256(opaque_id).hexdigest()}.json"
        )
        if os.path.lexists(canonical_file):
            raise RuntimeError(
                "recommendation legacy save refused: canonical artifact already exists"
            )

    @staticmethod
    def _contains_personalization_capture(data_file: Path) -> bool:
        """Return whether a saved result carries an immutable personal capture.

        This deliberately inspects the persisted JSON directly so the repository
        can enforce the boundary without importing the personalization adapter
        (and without turning the repository into a second projection writer).
        """
        try:
            payload = json.loads(data_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "recommendation legacy save cannot classify existing data "
                f"file; refusing overwrite: {data_file}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                "recommendation legacy save found an invalid existing data "
                f"file; refusing overwrite: {data_file}"
            )

        run_context = payload.get("run_context")
        if isinstance(run_context, dict):
            captures = run_context.get("personalization_delivery_captures")
            if isinstance(captures, list) and captures:
                return True

        recommendations = payload.get("recommendations")
        if not isinstance(recommendations, list):
            return False
        for recommendation in recommendations:
            if not isinstance(recommendation, dict):
                continue
            provenance = recommendation.get("calibration_provenance")
            if not isinstance(provenance, dict):
                continue
            if isinstance(provenance.get("personalization_delivery_capture"), dict):
                return True
        return False

    @staticmethod
    def _create_or_reuse_data_file(
        data_file: Path,
        serialized_data: str,
    ) -> bool:
        """Create a JSON file exclusively, or reuse an identical orphan.

        Returns ``True`` only when this call created the file.  An identical
        file without a metadata row is a recoverable prior-attempt orphan and is
        safe to reuse; a different file is never overwritten.
        """
        try:
            with data_file.open("x", encoding="utf-8") as handle:
                handle.write(serialized_data)
            return True
        except FileExistsError as exc:
            try:
                existing_data = data_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as read_exc:
                raise RuntimeError(
                    "recommendation create-only data path exists but cannot be "
                    f"inspected for safe retry: {data_file}"
                ) from read_exc
            if existing_data != serialized_data:
                raise RuntimeError(
                    "recommendation create-only data path contains a different "
                    f"orphan; refusing overwrite: {data_file}"
                ) from exc
            return False
    
    def save_result(
        self,
        result: RecommendationResultDTO,
        result_name: Optional[str] = None
    ) -> str:
        """
        儲存推薦結果
        
        Args:
            result: RecommendationResultDTO 實例
            result_name: 結果名稱（如果為 None 則自動生成）
        
        Returns:
            結果ID
        """
        if not result.result_id:
            result.result_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if not result.created_at:
            result.created_at = datetime.now().isoformat()
        
        if not result_name:
            result_name = f"推薦結果_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        result.result_name = result_name
        
        data_file = self.runs_dir / f"{result.result_id}.json"
        data = result.to_dict()
        # 清理數據，確保所有類型都是 JSON 可序列化的
        data = _make_json_serializable(data)
        serialized_data = json.dumps(data, ensure_ascii=False, indent=2)

        # Keep the legacy replace behavior for ordinary results, but serialize
        # the check and replacement under the same SQLite write lock used by
        # save_result_create_only().
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            self._assert_no_canonical_execution_identity(cursor, result.result_id)
            cursor.execute(
                "SELECT data_path FROM runs WHERE result_id = ?",
                (result.result_id,),
            )
            existing_row = cursor.fetchone()
            if existing_row and existing_row[0]:
                existing_file = Path(existing_row[0])
                if self._contains_personalization_capture(existing_file):
                    raise RuntimeError(
                        "recommendation legacy save refused: existing result "
                        "contains an immutable personal capture"
                    )
            elif existing_row:
                raise RuntimeError(
                    "recommendation legacy save found an existing metadata row "
                    "without a data path; refusing overwrite"
                )
            elif data_file.exists():
                raise RuntimeError(
                    "recommendation legacy save found an existing data path "
                    "without metadata; refusing overwrite: "
                    f"{data_file}"
                )

            # 清理 config，確保 JSON 可序列化
            config_cleaned = _make_json_serializable(result.config)
            data_file.write_text(serialized_data, encoding="utf-8")
            cursor.execute(
                """
                INSERT OR REPLACE INTO runs
                (result_id, result_name, regime, stock_count, config, notes, created_at, data_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.result_name,
                    result.regime,
                    len(result.recommendations),
                    json.dumps(config_cleaned, ensure_ascii=False),
                    result.notes,
                    result.created_at,
                    str(data_file),
                ),
            )
            conn.commit()
            return result.result_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_result_create_only(
        self,
        result: RecommendationResultDTO,
        result_name: Optional[str] = None,
    ) -> str:
        """Create a result exactly once without replacing an existing row.

        Personal delivery capture uses this additive boundary so two callers
        that both observed a missing result cannot race into a JSON overwrite.
        The SQLite transaction is held while the new JSON path is created; an
        existing metadata row is an idempotent create-only hit and is read
        back by the caller for exact capture verification.
        """

        if not result.result_id:
            result.result_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not result.created_at:
            result.created_at = datetime.now().isoformat()
        resolved_name = result_name or result.result_name or (
            f"推薦結果_{datetime.now().strftime('%Y%m%d_%H%M')}"
        )
        result.result_name = resolved_name

        data_file = self.runs_dir / f"{result.result_id}.json"
        data = _make_json_serializable(result.to_dict())
        serialized_data = json.dumps(data, ensure_ascii=False, indent=2)
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        data_file_created = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.cursor()
            self._assert_no_canonical_execution_identity(cursor, result.result_id)
            cursor.execute(
                "SELECT result_id FROM runs WHERE result_id = ?",
                (result.result_id,),
            )
            if cursor.fetchone() is not None:
                connection.commit()
                return result.result_id
            # _create_or_reuse_data_file() accepts only an exact, recoverable
            # orphan and never overwrites an existing path.
            data_file_created = self._create_or_reuse_data_file(
                data_file,
                serialized_data,
            )
            config_cleaned = _make_json_serializable(result.config)
            try:
                cursor.execute(
                    """
                    INSERT INTO runs
                    (result_id, result_name, regime, stock_count, config, notes, created_at, data_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.result_id,
                        result.result_name,
                        result.regime,
                        len(result.recommendations),
                        json.dumps(config_cleaned, ensure_ascii=False),
                        result.notes,
                        result.created_at,
                        str(data_file),
                    ),
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if data_file_created:
                    raise RuntimeError(
                        "recommendation create-only metadata write failed; "
                        "retained data file for safe retry: "
                        f"{data_file}"
                    ) from exc
                raise
            return result.result_id
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
    
    def load_result(self, result_id: str) -> Optional[RecommendationResultDTO]:
        """
        載入推薦結果
        
        Args:
            result_id: 結果ID
        
        Returns:
            RecommendationResultDTO 或 None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT data_path FROM runs WHERE result_id = ?", (result_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        data_file = Path(row[0])
        if not data_file.exists():
            return None
        
        try:
            data = json.loads(data_file.read_text(encoding='utf-8'))
            return RecommendationResultDTO.from_dict(data)
        except Exception as e:
            print(f"[RecommendationRepository] 載入失敗 {result_id}: {e}")
            return None
    
    def list_results(self) -> List[Dict[str, Any]]:
        """
        列出所有推薦結果
        
        Returns:
            結果列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT result_id, result_name, regime, stock_count, created_at, notes
            FROM runs
            ORDER BY created_at DESC
        """)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'result_id': row[0],
                'result_name': row[1],
                'regime': row[2],
                'stock_count': row[3],
                'created_at': row[4],
                'notes': row[5] or ''
            })
        
        conn.close()
        return results
    
    def delete_result(self, result_id: str) -> bool:
        """
        刪除推薦結果
        
        Args:
            result_id: 結果ID
        
        Returns:
            是否成功刪除
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 獲取檔案路徑
        cursor.execute("SELECT data_path FROM runs WHERE result_id = ?", (result_id,))
        row = cursor.fetchone()
        
        if row:
            data_file = Path(row[0])
            if data_file.exists():
                try:
                    data_file.unlink()
                except:
                    pass
        
        # 從資料庫刪除
        cursor.execute("DELETE FROM runs WHERE result_id = ?", (result_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted

