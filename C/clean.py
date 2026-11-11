#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取 raw.csv，按《数据采集与预处理统一规范》生成 processed.csv 和质量报告。

用法：
  python clean.py --input platform_data/raw.csv --output platform_data/processed.csv \
      --report platform_data/data_quality_report.txt

原则：
  - content 保留原文，不覆盖；
  - clean_content 只做符号/URL/@/空白清理，保留否定词、程度副词、表情；
  - 不因评论短就删除；
  - tokens 使用 jieba 分词，空格分隔；
  - 字段名和顺序严格按规范。
"""
from __future__ import annotations

import os
import tempfile

# jieba 的缓存默认写到 C 盘 Temp；在导入 jieba/pandas 之前把临时目录指到项目 E 盘
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = os.path.join(_ROOT, "tmp")
os.makedirs(_TMP, exist_ok=True)
os.environ["TMP"] = _TMP
os.environ["TEMP"] = _TMP
tempfile.tempdir = _TMP

import argparse
import html
import re

import jieba
import pandas as pd

RAW_COLUMNS = [
    "comment_id", "post_id", "parent_comment_id", "content", "create_time",
    "crawl_time", "user_id", "like_count", "reply_count", "post_title",
    "post_url", "source_type", "keyword", "platform",
]
PROCESSED_COLUMNS = [
    "comment_id", "post_id", "parent_comment_id", "platform", "content",
    "clean_content", "tokens", "create_time", "crawl_time", "user_id",
    "like_count", "reply_count", "post_title", "post_url", "source_type", "keyword",
]

# 只匹配明显广告/引流，避免误伤普通评论
AD_PATTERNS = [
    r"加\s*[Vv微]", r"微信", r"vx", r"VX", r"私信", r"代写", r"兼职",
    r"引流", r"关注我", r"点我主页", r"主页有", r"领取资料", r"优惠券",
    r"抽奖", r"购买链接", r"咨询客服", r"扫码", r"二维码",
]
AD_RE = re.compile("|".join(AD_PATTERNS), re.I)

# 保留有意义的字符（中文/英文/数字/表情）
MEANINGFUL_RE = re.compile(r"[一-龥A-Za-z0-9]|[\U0001F300-\U0001FAFF☀-➿]")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
AT_RE = re.compile(r"@[\w一-龥_\-]+")
TOPIC_RE = re.compile(r"#([^#]{1,50})#")
CTRL_RE = re.compile(r"[​-‏‪-‮﻿]")

CUSTOM_WORDS = [
    "后会友期", "破镜重圆", "意难平", "消耗型朋友", "情绪价值", "边界感",
    "断联", "友尽", "闹掰", "和好", "和解", "绝交", "重归于好", "不原谅",
]


def clean_text(text: str) -> str:
    s = html.unescape(str(text or ""))
    s = URL_RE.sub(" ", s)
    s = AT_RE.sub(" ", s)
    s = TOPIC_RE.sub(r"\1", s)
    s = CTRL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_meaningful(text: str) -> bool:
    return bool(MEANINGFUL_RE.search(str(text or "")))


def tokenize(text: str) -> str:
    tokens = []
    for t in jieba.lcut(text):
        t = t.strip()
        if not t or not is_meaningful(t):
            continue
        tokens.append(t)
    return " ".join(tokens)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="platform_data/raw.csv")
    parser.add_argument("--output", default="platform_data/processed.csv")
    parser.add_argument("--report", default="platform_data/data_quality_report.txt")
    parser.add_argument("--exclude-comments", default="docs/exclude_comments.txt",
                        help="人工排除的评论 ID 清单，一行一个（保守删除明显无关/无信息量评论）")
    args = parser.parse_args()

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for col in RAW_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    raw_count = len(df)

    # 去重 1：comment_id
    df = df.drop_duplicates(subset=["comment_id"], keep="first").copy()
    after_id_dedup = len(df)

    # 规范化文本
    df["content"] = df["content"].fillna("").astype(str)
    df["clean_content"] = df["content"].map(clean_text)

    # 去重 2：同一帖子、同一用户、同一清洗后文本
    df["_dup_key"] = df["post_id"].astype(str) + "|" + df["user_id"].astype(str) + "|" + df["clean_content"]
    before_text_dedup = len(df)
    df = df.drop_duplicates(subset=["_dup_key"], keep="first").copy()
    after_text_dedup = len(df)

    # 删除空/纯符号/纯 URL
    before_invalid = len(df)
    df = df[df["content"].map(is_meaningful) & df["clean_content"].map(is_meaningful)].copy()
    after_invalid = len(df)

    # 删除广告/引流
    before_ad = len(df)
    df = df[~df["clean_content"].map(lambda x: bool(AD_RE.search(x)))].copy()
    after_ad = len(df)

    # 删除人工排除的评论（保守删除明显无关/无信息量评论，comment_id 一行一个）
    exclude_comments: set[str] = set()
    if os.path.exists(args.exclude_comments):
        with open(args.exclude_comments, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    exclude_comments.add(s)
    before_excl = len(df)
    if exclude_comments:
        df = df[~df["comment_id"].astype(str).isin(exclude_comments)].copy()
    after_excl = len(df)

    # 分词
    for w in CUSTOM_WORDS:
        jieba.add_word(w)
    df["tokens"] = df["clean_content"].map(tokenize)

    # 数值/默认值
    df["platform"] = df["platform"].replace("", "xiaohongshu")
    df["source_type"] = df["source_type"].replace("", "user_discussion")
    df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce").fillna(0).astype(int)
    df["reply_count"] = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0).astype(int)
    for col in PROCESSED_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    out = df[PROCESSED_COLUMNS].copy()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[OK] processed.csv -> {args.output} ({len(out)} 行)")

    # 质量报告
    lines = []
    lines.append("《后会友期》小红书数据质量报告")
    lines.append("=" * 40)
    lines.append(f"原始评论数: {raw_count}")
    lines.append(f"按 comment_id 去重后: {after_id_dedup}")
    lines.append(f"按 帖子+用户+文本 去重后: {after_text_dedup}")
    lines.append(f"删除空/纯符号/纯URL: {before_invalid - after_invalid}")
    lines.append(f"删除广告/引流: {before_ad - after_ad}")
    lines.append(f"删除明显无关内容（人工排除）: {before_excl - after_excl}")
    lines.append(f"最终有效评论数: {len(out)}")
    lines.append(f"覆盖帖子数: {out['post_id'].nunique()}")
    lines.append(f"一级评论: {(out['parent_comment_id'].astype(str) == '').sum()}")
    lines.append(f"回复: {(out['parent_comment_id'].astype(str) != '').sum()}")
    lines.append("")
    lines.append("source_type 分布:")
    lines.append(out["source_type"].value_counts().to_string())
    lines.append("")
    lines.append("评论时间分布（按天）:")
    dt = pd.to_datetime(out["create_time"], errors="coerce")
    day_counts = dt.dt.strftime("%Y-%m-%d").value_counts().sort_index()
    lines.append(day_counts.to_string() if len(day_counts) else "（无法解析时间）")
    lines.append("")
    lines.append("字段缺失情况（空字符串计数）:")
    for col in PROCESSED_COLUMNS:
        empties = int((out[col].astype(str).str.strip() == "").sum())
        if empties:
            lines.append(f"  {col}: {empties}")
    lines.append("")
    lines.append("说明:")
    lines.append("- user_id 为 MediaCrawler 已脱敏的 creator_hash，不含原始用户 ID。")
    lines.append("- content 保留原文；clean_content 仅做符号/URL/@/空白清理。")
    lines.append("- 保留否定词、程度副词、表情；未按长度删除短评论。")
    lines.append("- 删除的评论统一归为「明显无关内容」：空/纯符号/纯URL、广告引流、纯附和（是的/同意/点了）、"
                 "纯语气词/纯表情/纯@好友/纯笑等零信息量短评论。")
    lines.append("- 未按评论长度整体删除；未做主题相关性/立场过滤，相关性/立场编码由 A/D 统一标注。")

    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] 质量报告 -> {args.report}")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
