#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 MediaCrawler 的微博 jsonl 输出，转换成《数据采集与预处理统一规范》要求的 raw.csv。

MediaCrawler 输出位置（SAVE_DATA_OPTION=jsonl）：
  data/weibo/**/search_comments_YYYY-MM-DD.jsonl
  data/weibo/**/search_contents_YYYY-MM-DD.jsonl

用法：
  python crawler.py --input data/weibo --output B/raw.csv --contents B/contents.csv

说明：
  - 只做字段转换与去重（按 content 完全一致去重，保留首条），不做文本清洗（清洗在 clean.py）。
  - user_id 使用 MediaCrawler 已脱敏的 creator_hash，不落原始用户 ID。
  - source_type 按采集文件夹前缀推导：嘉宾_→guest，节目_/后会友期_→official，社会_/补充_→user_discussion。
  - keyword：评论通过 note_id 回填对应正文的 source_keyword；正文直接取 source_keyword。
  - platform 固定为 weibo。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from datetime import datetime

import pandas as pd

RAW_COLUMNS = [
    "comment_id", "post_id", "parent_comment_id", "content", "create_time",
    "crawl_time", "user_id", "like_count", "reply_count", "post_title",
    "post_url", "source_type", "keyword", "platform",
]


def parse_ts(value) -> "pd.Timestamp | None":
    """10/13 位时间戳或日期字符串统一成 Timestamp。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    if re.fullmatch(r"\d{10,13}", s):
        x = int(s)
        if x > 10_000_000_000:  # 毫秒
            x = x / 1000
        return pd.Timestamp(datetime.fromtimestamp(x))
    return pd.to_datetime(s, errors="coerce")


def fmt_ts(value) -> str:
    ts = parse_ts(value)
    if ts is None or pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def source_type_of(category: str | None) -> str:
    if category is None:
        return "user_discussion"
    if category.startswith("嘉宾"):
        return "guest"
    if category.startswith("节目") or category.startswith("后会友期"):
        return "official"
    if category.startswith("社会") or category.startswith("补充"):
        return "user_discussion"
    return "user_discussion"


def category_of(filepath: str, base: str) -> str | None:
    rel = os.path.relpath(filepath, base)
    parts = rel.split(os.sep)
    # 顶层: jsonl/search_xxx.jsonl -> parts[0] == 'jsonl'
    # 分类: <分类>/weibo/jsonl/search_xxx.jsonl -> parts[0] == <分类>
    return None if parts[0] == "jsonl" else parts[0]


def read_jsonl_with_category(pattern: str, base: str):
    """返回 [(record, category), ...]，按文件路径顺序。"""
    out = []
    for path in sorted(glob.glob(pattern, recursive=True)):
        cat = category_of(path, base)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append((json.loads(line), cat))
                    except json.JSONDecodeError:
                        continue
    return out


def dedup_by_content(rows: list[list]) -> list[list]:
    """按 content（第 4 列）完全一致去重，保留首条。"""
    seen = set()
    out = []
    for row in rows:
        key = row[3]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/weibo", help="MediaCrawler 微博输出根目录")
    parser.add_argument("--output", default="B/raw.csv")
    parser.add_argument("--contents", default="B/contents.csv")
    args = parser.parse_args()

    base = os.path.abspath(args.input)
    comments = read_jsonl_with_category(os.path.join(args.input, "**", "search_comments_*.jsonl"), base)
    contents = read_jsonl_with_category(os.path.join(args.input, "**", "search_contents_*.jsonl"), base)
    if not comments:
        raise SystemExit(f"[ERROR] 在 {args.input} 下没有找到 search_comments_*.jsonl")

    # note_id -> 搜索关键词集合（供评论回填 keyword）
    note_kw: dict[str, set] = {}
    for c, _cat in contents:
        nid = str(c.get("note_id", "") or "")
        kw = c.get("source_keyword", "") or ""
        if nid:
            note_kw.setdefault(nid, set())
            if kw:
                note_kw[nid].add(kw)

    # 组装评论
    comment_rows = []
    for c, cat in comments:
        note_id = str(c.get("note_id", "") or "")
        kws = note_kw.get(note_id)
        keyword = "、".join(sorted(kws)) if kws else ""
        comment_rows.append([
            c.get("comment_id", ""), note_id, c.get("parent_comment_id", ""),
            c.get("content", ""),
            fmt_ts(c.get("create_time") or c.get("create_date_time")),
            fmt_ts(c.get("last_modify_ts")), c.get("creator_hash", ""),
            c.get("comment_like_count", ""), c.get("sub_comment_count", ""), "",
            f"https://m.weibo.cn/detail/{note_id}" if note_id else "",
            source_type_of(cat), keyword, "weibo",
        ])

    # 组装正文/帖子
    content_rows = []
    for c, cat in contents:
        note_id = str(c.get("note_id", "") or "")
        content_rows.append([
            "", note_id, "", c.get("content", ""),
            fmt_ts(c.get("create_time") or c.get("create_date_time")),
            fmt_ts(c.get("last_modify_ts")), c.get("creator_hash", ""),
            c.get("liked_count", ""), c.get("comments_count", ""), "",
            c.get("note_url", ""), source_type_of(cat),
            c.get("source_keyword", ""), "weibo",
        ])

    raw = dedup_by_content(comment_rows)
    contents_out = dedup_by_content(content_rows)

    def save(path, rows):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        pd.DataFrame(rows, columns=RAW_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[OK] {path} ({len(rows)} 行)")

    save(args.output, raw)
    save(args.contents, contents_out)
    print(f"[SUMMARY] 评论 {len(raw)} 条；正文 {len(contents_out)} 条")


if __name__ == "__main__":
    main()
