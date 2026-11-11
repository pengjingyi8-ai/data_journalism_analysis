#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 MediaCrawler 的小红书 CSV 输出，转换成《数据采集与预处理统一规范》要求的 raw.csv。

MediaCrawler 输出位置（SAVE_DATA_OPTION=csv）：
  output/media_crawler/xhs/csv/search_contents_YYYY-MM-DD.csv
  output/media_crawler/xhs/csv/search_comments_YYYY-MM-DD.csv

用法：
  python crawler.py --input output/media_crawler --output platform_data/raw.csv \
      --start "2026-10-22 00:00:00" --end "2026-11-09 23:59:59"

说明：
  - 只做字段转换、时间过滤、去重；不做文本清洗（清洗在 clean.py）。
  - user_id 使用 MediaCrawler 已脱敏的 creator_hash，不落原始用户 ID。
  - post_url 去掉 xsec_token 查询参数，避免把访问令牌写进交付数据。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
from datetime import datetime
from typing import Any

import pandas as pd

RAW_COLUMNS = [
    "comment_id", "post_id", "parent_comment_id", "content", "create_time",
    "crawl_time", "user_id", "like_count", "reply_count", "post_title",
    "post_url", "source_type", "keyword", "platform",
]

NOTE_COLUMNS = [
    "note_id", "title", "desc", "type", "time", "creator_hash", "nickname",
    "liked_count", "collected_count", "comment_count", "share_count",
    "tag_list", "last_modify_ts", "note_url", "source_keyword",
]

COMMENT_COLUMNS = [
    "comment_id", "create_time", "note_id", "content", "creator_hash",
    "nickname", "sub_comment_count", "parent_comment_id", "last_modify_ts",
    "like_count",
]

# 议题锚点词：关键词或标题命中这些词，初判为“贴题”。
# 用于 notes_overview.csv 的 relevance_hint 列，只做初判，最终由人工复核。
TOPIC_WORDS = [
    "和解", "和好", "绝交", "断联", "复合", "原谅", "重归于好", "不原谅",
    "没必要", "信任", "背叛", "道歉", "遗憾", "失去朋友", "边界",
    "友情", "友谊", "朋友",
]

# 疑似噪声：标题命中这些多为追星/CP/星座/安利，标记为“疑似噪声”，需人工确认。
NOISE_PATTERNS = [
    "爱上了", "喜欢上", "爆哭", "哭到", "太好看了", "安利", "宝藏", "推荐",
    "星座", "双子", "摩羯", "水瓶", "天秤", "狮子", "处女", "射手",
    "金牛", "白羊", "巨蟹", "天蝎", "双鱼", "MBTI", "CP", "颜值", "穿搭",
    "好看", "磕", "人设", "使唤", "懂事", "脚底板", "切片", "磕点",
    "好磕", "深扒", "文盲",
]


def hint_relevance(keyword: str, title: str) -> str:
    """给笔记打初判标签：topic=贴题 / noise=疑似噪声 / review=待复核。

    噪声优先：CP 帖即使是用“复合/和好”做关键词搜到的，标题仍可能带磕/人设/星座，
    所以要先用标题判噪声，避免关键词里的议题词把所有帖子都误判成 topic。
    """
    k = keyword or ""
    t = title or ""
    if any(p in t for p in NOISE_PATTERNS):  # 1) 标题命中噪声词 → noise
        return "noise"
    if any(w in t for w in TOPIC_WORDS):      # 2) 标题命中议题词 → topic
        return "topic"
    if any(w in k for w in TOPIC_WORDS):      # 3) 关键词命中议题词 → topic（较弱）
        return "topic"
    return "review"


def parse_ts(value: Any) -> pd.Timestamp | None:
    """把 13 位毫秒时间戳 / 10 位秒时间戳 / 日期字符串统一成 Timestamp。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    if re.fullmatch(r"\d{10,13}", s):
        x = int(s)
        if x > 10_000_000_000:  # 毫秒
            x = x / 1000
        # 用本地时区（Asia/Shanghai），不要用 UTC
        return pd.Timestamp(datetime.fromtimestamp(x))
    return pd.to_datetime(s, errors="coerce")


def fmt_ts(value: Any) -> str:
    ts = parse_ts(value)
    if ts is None or pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def read_csvs(pattern: str, required: list[str]) -> pd.DataFrame:
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        return pd.DataFrame(columns=required)
    frames = []
    for path in files:
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 读取失败 {path}: {exc}")
            continue
        if df.empty:
            continue
        for col in required:
            if col not in df.columns:
                df[col] = ""
        frames.append(df[required])
        print(f"[INFO] 读取 {path}: {len(df)} 行")
    if not frames:
        return pd.DataFrame(columns=required)
    return pd.concat(frames, ignore_index=True)


def load_accounts(path: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """返回 post_id / creator_hash / nickname 到 source_type 的映射。"""
    by_post: dict[str, str] = {}
    by_hash: dict[str, str] = {}
    by_name: dict[str, str] = {}
    if not os.path.exists(path):
        return by_post, by_hash, by_name
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for _, row in df.iterrows():
        st = (row.get("source_type") or "").strip()
        if st not in {"official", "guest", "user_discussion"}:
            continue
        if row.get("post_id"):
            by_post[row["post_id"].strip()] = st
        if row.get("creator_hash"):
            by_hash[row["creator_hash"].strip()] = st
        if row.get("nickname"):
            by_name[row["nickname"].strip()] = st
    return by_post, by_hash, by_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/media_crawler", help="MediaCrawler 输出根目录")
    parser.add_argument("--output", default="platform_data/raw.csv")
    parser.add_argument("--notes-overview", default="platform_data/notes_overview.csv")
    parser.add_argument("--accounts", default="docs/accounts.csv")
    parser.add_argument("--exclude", default="docs/exclude_posts.txt")
    parser.add_argument("--start", default="2026-10-22 00:00:00")
    parser.add_argument("--end", default="2026-11-09 23:59:59")
    parser.add_argument("--no-filter-post-time", action="store_true",
                        help="不按帖子发布时间过滤（默认按帖子发布时间过滤）")
    args = parser.parse_args()

    notes = read_csvs(os.path.join(args.input, "**", "*_contents_*.csv"), NOTE_COLUMNS)
    comments = read_csvs(os.path.join(args.input, "**", "*_comments_*.csv"), COMMENT_COLUMNS)
    if comments.empty:
        raise SystemExit(f"[ERROR] 在 {args.input} 下没有找到 *_comments_*.csv")

    notes = notes.drop_duplicates(subset=["note_id"], keep="last").copy()
    notes["_note_dt"] = notes["time"].map(parse_ts)
    notes["_publish_time"] = notes["time"].map(fmt_ts)
    comments = comments.drop_duplicates(subset=["comment_id"], keep="first").copy()
    comments["_comment_dt"] = comments["create_time"].map(parse_ts)

    # 人工排除的帖子（拼豆图纸、教师 plog、第二季选角八卦等）
    exclude: set[str] = set()
    if os.path.exists(args.exclude):
        with open(args.exclude, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    exclude.add(s)
    if exclude:
        before = len(notes)
        notes = notes[~notes["note_id"].isin(exclude)].copy()
        print(f"[INFO] 人工排除帖子: {before} -> {len(notes)}")

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)

    # 按帖子发布时间过滤（需求：帖子/评论发布时间都在窗口内）
    if not args.no_filter_post_time:
        before = len(notes)
        notes = notes[(notes["_note_dt"] >= start) & (notes["_note_dt"] <= end)].copy()
        print(f"[INFO] 帖子时间过滤: {before} -> {len(notes)}")

    # 按评论发布时间过滤
    before = len(comments)
    comments = comments[(comments["_comment_dt"] >= start) & (comments["_comment_dt"] <= end)].copy()
    print(f"[INFO] 评论时间过滤: {before} -> {len(comments)}")

    if notes.empty:
        raise SystemExit("[ERROR] 窗口内没有帖子；请检查时间窗或放宽关键词/排序。")

    allowed_notes = set(notes["note_id"])
    comments = comments[comments["note_id"].isin(allowed_notes)].copy()

    # 合并笔记元数据
    note_meta = notes.rename(columns={
        "creator_hash": "note_creator_hash",
        "nickname": "note_nickname",
        "title": "post_title",
        "source_keyword": "keyword",
        "note_url": "post_url_raw",
    })[["note_id", "post_title", "note_creator_hash", "note_nickname",
        "post_url_raw", "keyword", "_publish_time", "comment_count"]]
    df = comments.merge(note_meta, on="note_id", how="left")

    by_post, by_hash, by_name = load_accounts(args.accounts)

    def classify(row: pd.Series) -> str:
        post_id = str(row.get("note_id", "")).strip()
        creator = str(row.get("note_creator_hash", "")).strip()
        nickname = str(row.get("note_nickname", "")).strip()
        return by_post.get(post_id) or by_hash.get(creator) or by_name.get(nickname) or "user_discussion"

    df["source_type"] = df.apply(classify, axis=1)
    df["platform"] = "xiaohongshu"
    df["user_id"] = df["creator_hash"].fillna("").astype(str)
    df["post_id"] = df["note_id"].fillna("").astype(str)
    df["comment_id"] = df["comment_id"].fillna("").astype(str)
    df["parent_comment_id"] = df["parent_comment_id"].fillna("").astype(str)
    df["content"] = df["content"].fillna("").astype(str)
    df["post_title"] = df["post_title"].fillna("").astype(str)
    df["keyword"] = df["keyword"].fillna("").astype(str)
    df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce").fillna(0).astype(int)
    df["reply_count"] = pd.to_numeric(df["sub_comment_count"], errors="coerce").fillna(0).astype(int)
    df["create_time"] = df["create_time"].map(fmt_ts)
    df["crawl_time"] = df["last_modify_ts"].map(fmt_ts)

    def clean_url(row: pd.Series) -> str:
        raw = str(row.get("post_url_raw", "") or "")
        if not raw or raw.lower() == "nan":
            nid = str(row.get("note_id", ""))
            return f"https://www.xiaohongshu.com/explore/{nid}" if nid else ""
        return re.sub(r"\?.*$", "", raw)

    df["post_url"] = df.apply(clean_url, axis=1)

    raw = df[RAW_COLUMNS].drop_duplicates(subset=["comment_id"], keep="first")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    raw.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[OK] raw.csv -> {args.output} ({len(raw)} 行)")

    # 供人工分类 source_type 的笔记清单（不属于统一字段，仅辅助）
    overview = notes.copy()
    overview["source_type"] = overview.apply(
        lambda r: by_post.get(str(r["note_id"]))
        or by_hash.get(str(r["creator_hash"]))
        or by_name.get(str(r["nickname"]))
        or "user_discussion",
        axis=1,
    )
    overview["note_publish_time"] = overview["_publish_time"]
    overview["note_url"] = overview["note_url"].map(
        lambda u: re.sub(r"\?.*$", "", str(u or ""))
    )
    overview["relevance_hint"] = overview.apply(
        lambda r: hint_relevance(str(r["source_keyword"]), str(r["title"])), axis=1
    )
    overview = overview.rename(columns={
        "note_id": "post_id", "title": "post_title", "creator_hash": "note_creator_hash",
        "nickname": "note_nickname", "source_keyword": "keyword",
    })[["post_id", "post_title", "note_creator_hash", "note_nickname",
        "note_publish_time", "comment_count", "keyword", "source_type",
        "relevance_hint", "note_url"]]
    overview.to_csv(args.notes_overview, index=False, encoding="utf-8-sig")
    print(f"[OK] notes_overview.csv -> {args.notes_overview} ({len(overview)} 篇)")

    print("\n[SUMMARY]")
    print(f"帖子数: {len(notes)}")
    print(f"评论数: {len(raw)}")
    print(f"一级评论: {(raw['parent_comment_id'] == '').sum()}")
    print(f"回复: {(raw['parent_comment_id'] != '').sum()}")
    print("source_type 分布:")
    print(raw["source_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
