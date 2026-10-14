"""腾讯实时快照源（qt.gtimg.cn，批量 HTTP 轮询）。

字段映射 2026-10-14 用茅台实测校准（与我们已入库的日线 high/low 完全对齐）：
[3]最新价 [4]昨收 [5]今开 [6]成交量(手) [9..18]买一~五价/量 [19..28]卖一~五价/量
[30]时间 yyyyMMddHHmmss [33]最高 [34]最低 [36]成交量(手) [37]成交额(万元)。

已知口径差异（D4 跨源校验输入）：腾讯快照含盘后固定价格交易（16:14 后仍更新），
成交量额口径与东财日线接口存在差异（600519 实测 26573 手 vs 22726 手）。

合规：免费源自用研究落库，不转发不售卖（LC-05）。
"""

from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd

from data_platform.sources.base import SNAPSHOT_COLUMNS

_BATCH_URL = "http://qt.gtimg.cn/q={codes}"


def to_tencent_code(symbol: str) -> str | None:
    """A 股代码 → 腾讯市场前缀代码；北交所 v1 不支持（返回 None，由调用方剔除）。"""
    if symbol.startswith("6"):
        return f"sh{symbol}"
    if symbol.startswith(("0", "3")):
        return f"sz{symbol}"
    return None


class TencentRealtimeSource:
    source_name = "tencent"

    def __init__(self, batch_size: int = 60, timeout: float = 5.0) -> None:
        self._client = httpx.Client(timeout=timeout)
        self._batch_size = batch_size

    def fetch_quotes(self, symbols: list[str]) -> pd.DataFrame:
        """批量拉取快照（自动分批串行请求）；单批失败抛异常。"""
        codes = [(s, to_tencent_code(s)) for s in symbols]
        valid = [(s, c) for s, c in codes if c]
        frames: list[pd.DataFrame] = []
        for i in range(0, len(valid), self._batch_size):
            batch = valid[i : i + self._batch_size]
            url = _BATCH_URL.format(codes=",".join(c for _, c in batch))
            resp = self._client.get(url)
            resp.raise_for_status()
            frames.append(self._parse(resp.content.decode("gbk", errors="replace")))
        if not frames:
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
        return pd.concat(frames, ignore_index=True)

    def _parse(self, text: str) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for line in text.strip().split(";"):
            if "=" not in line:
                continue
            _, raw = line.split("=", 1)
            f = raw.strip('"').split("~")
            if len(f) < 38 or not f[3] or not f[30]:
                continue
            try:
                exchange_ts = dt.datetime.strptime(f[30], "%Y%m%d%H%M%S")
                rows.append(
                    {
                        "symbol": f[2],
                        "exchange_ts": exchange_ts,
                        "last": float(f[3]),
                        "open": float(f[5] or 0),
                        "high": float(f[33]),
                        "low": float(f[34]),
                        "pre_close": float(f[4]),
                        "volume": int(float(f[36]) * 100),  # 手→股
                        "amount": float(f[37]) * 10_000,  # 万→元
                        "bid1": float(f[9]), "bid1_vol": int(float(f[10] or 0)) * 100,
                        "ask1": float(f[19]), "ask1_vol": int(float(f[20] or 0)) * 100,
                        "bid2": float(f[11]), "bid2_vol": int(float(f[12] or 0)) * 100,
                        "ask2": float(f[21]), "ask2_vol": int(float(f[22] or 0)) * 100,
                        "bid3": float(f[13]), "bid3_vol": int(float(f[14] or 0)) * 100,
                        "ask3": float(f[23]), "ask3_vol": int(float(f[24] or 0)) * 100,
                        "bid4": float(f[15]), "bid4_vol": int(float(f[16] or 0)) * 100,
                        "ask4": float(f[25]), "ask4_vol": int(float(f[26] or 0)) * 100,
                        "bid5": float(f[17]), "bid5_vol": int(float(f[18] or 0)) * 100,
                        "ask5": float(f[27]), "ask5_vol": int(float(f[28] or 0)) * 100,
                        "source": "tencent",
                    }
                )
            except (ValueError, IndexError):
                continue  # 单票字段异常不拖垮整批
        return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
