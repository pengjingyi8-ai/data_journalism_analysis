# 《后会友期》微博数据采集与预处理（角色 B）

> 项目：我们真的希望破镜重圆吗？——《后会友期》评论区中的和解观念与关系研究
> 平台：**微博（weibo）**
> 采集窗口：2026-10-22 — 2026-11-12

## 一、交付文件

| 文件 | 说明 | 数量 |
|---|---|---:|
| `raw.csv` | 原始数据，16 字段（按 `content` 完全一致去重） | 4437 条评论 |
| `processed.csv` | 最终数据，16 字段（程序清洗 + 人工筛选） | 1547 条评论 |
| `crawler.py` | MediaCrawler 微博 jsonl → 规范 CSV | — |
| `clean.py` | raw.csv → processed.csv（初筛）+ 质量报告 | — |
| `data_quality_report.txt` | 数据质量报告（最终版） | — |

`raw.csv` 与 `processed.csv` 字段名、顺序完全一致，严格遵循《数据采集与预处理统一规范》（16 字段），可与小红书端直接合并。

## 二、数据概况

- 原始评论：**4437 条**（按 `content` 完全一致去重后）
- 程序清洗后：**4398 条**
- 人工筛选后保留：**1547 条**
- 覆盖帖子数：394 篇
- 一级评论 / 回复：1486 / 61（部分关键词开启了二级评论抓取）
- source_type 分布：user_discussion 1189 / guest 262 / official 96

## 三、采集方法

- **工具**：开源 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)（微博搜索模式，`SAVE_DATA_OPTION=jsonl`），复用本机浏览器登录态（CDP）。
- **关键词分层**：议题锚点词（和解/绝交/断联/复合/原谅/不原谅/重归于好/破镜重圆/意难平…）+ 嘉宾×议题（许飞/厉娜/白小纯/青稚/马天宇/张萌/文吉儿/王子璇）+ 泛话题（友情和解/体面告别/友情边界/边界感/内耗/自我保护/消耗型朋友/朋友绝交/要不要和好…）。
- **转换**：`crawler.py` 把 `data/weibo/**/*.jsonl` 转为规范 16 字段 CSV，并按 `content` 去重。

## 四、清洗

**程序清洗（clean.py）**：4437 条原始评论 → 4398 条有效评论。

| 删除项 | 数量 |
|---|---:|
| 评论 ID / 文本重复 | 4 |
| 空 / 纯符号 / 纯 URL | 29 |
| 广告 / 引流 | 6 |

- `content` 保留原文；`clean_content` 仅做符号/URL/@/空白清理，保留否定词、程度副词、表情。
- 未按评论长度删除；`tokens` 为 jieba 分词（空格分隔）。
- **人工筛选**：4398 条有效评论 → 1547 条保留（`processed.csv`）。

## 五、字段规范（16 字段）

`raw.csv` 与 `processed.csv` 字段完全一致：

```
comment_id, post_id, parent_comment_id, platform, content,
clean_content, tokens, create_time, crawl_time, user_id,
like_count, reply_count, post_title, post_url, source_type, keyword
```

字段说明：`user_id` 为 MediaCrawler 脱敏后的 `creator_hash`；`source_type` 按采集文件夹前缀推导（嘉宾_→guest、节目_/后会友期_→official、社会_/补充_→user_discussion）；`platform=weibo`；微博正文无标题，故 `post_title` 为空。`clean_content` 为 `content` 清理后的文本，`tokens` 为 jieba 分词结果（空格分隔）。

## 六、合规与隐私

- 复用本机浏览器登录态，不采集私信、手机号、真实姓名等个人信息；
- `user_id` 为脱敏后的 `creator_hash`，不含原始用户 ID；
- 控制采集频率，遇验证码人工通过，不做验证码破解、不挂代理池；
- 数据仅用于课程研究，不公开、不商用。
