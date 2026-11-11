# 《后会友期》小红书数据采集与预处理（角色 C）

> 数据新闻项目：**我们真的希望破镜重圆吗？——《后会友期》评论区中的和解观念与关系研究**
> 本仓库负责 **小红书平台**的数据采集与预处理（B 负责微博平台，交付结构一致）。
>
> **作者：夏晨馨（角色 C · 数据设计师 2）**

## 一、交付物（`platform_data/`）

| 文件 | 说明 | 数量 |
|---|---|---:|
| `raw.csv` | 原始数据，14 字段 | 3432 条 / 118 帖 |
| `processed.csv` | 清洗后数据，16 字段 | **1646 条 / 100 帖** |
| `crawler.py` | MediaCrawler 输出 → raw.csv | — |
| `clean.py` | raw.csv → processed.csv + 质量报告 | — |
| `data_quality_report.txt` | 数据量、清洗规则、时间分布 | — |
| `sample_for_A.csv` | 给 A 检查的 50 条样例 | 50 条 |
| `notes_overview.csv` | 帖子清单（含链接，辅助人工复核） | 100 帖 |
| `交付说明.md` | 完整交付说明 | — |

**字段顺序与命名字严格遵循《数据采集与预处理统一规范》，可与微博端直接合并。**

## 二、数据概况

- 采集窗口：2026-10-22 — 2026-11-09
- 有效评论 **1646 条**，覆盖 **100 篇**帖子
- 一级评论 / 回复：570 / 1076
- 时间覆盖窗口内逐日
- 删除的评论统一归为「明显无关内容」：空/纯符号/广告引流/零信息量短评论（纯附和、纯表情、纯@、纯笑等）

## 三、目录结构

```text
houhuiyouqi_project/
├── platform_data/          # ★ 交付物（见上表）
├── docs/
│   ├── keyword_plan.md     # 关键词分层与采集计划
│   ├── accounts.csv        # 官号/嘉宾号 -> source_type 映射
│   ├── official_accounts.txt
│   ├── exclude_posts.txt   # 排除的帖子 ID（噪声帖）
│   └── exclude_comments.txt # 排除的评论 ID（明显无关内容，可复现）
├── output/
│   ├── media_crawler/      # MediaCrawler 原始 CSV（采集证据）
│   └── pilot_2026-11-10/   # 早期试点存档
├── run_crawl.bat / run_convert.bat / run_clean.bat / check_status.bat
└── README.md
```

## 四、复现流程

1. 安装采集引擎（第三方，未纳入本仓库）：

   ```bash
   git clone https://github.com/NanmiCoder/MediaCrawler.git tools/MediaCrawler
   cd tools/MediaCrawler && uv sync
   ```

2. 配置 `tools/MediaCrawler/config/base_config.py` 的 `KEYWORDS`、`CRAWLER_MAX_NOTES_COUNT`（关键词方案见 `docs/keyword_plan.md`）。

3. 采集（需用小红书小号扫码登录）：

   ```bat
   run_crawl.bat
   ```

4. 转换为规范 raw.csv：

   ```bat
   run_convert.bat
   ```

5. 清洗并生成质量报告：

   ```bat
   run_clean.bat
   ```

6. 一键自检：

   ```bat
   check_status.bat
   ```

> 说明：`clean.py` 依赖 `jieba`，需在 MediaCrawler 的虚拟环境里运行（`run_*.bat` 已指定该解释器）。

## 五、方法要点

- **关键词分层**：节目锚点、嘉宾×议题、议题锚点（和解/绝交/断联/复合/原谅…）、泛话题。只用"后会友期"一词会召回大量 CP/追星噪声，主力应为议题锚点词。
- **帖子级过滤**：排除纯 CP/星座/追星/八卦帖（`docs/exclude_posts.txt`）。
- **评论级清洗**：仅删除明显无关内容（空、纯符号、广告、零信息量短评论）；**不做相关性/立场判断**——那由 A/D 统一标注。
- **可复现**：所有删除项以 ID 清单保存，重跑结果一致。

## 六、合规与隐私

- 使用小号二维码登录，不采集私信、手机号、真实姓名；
- `user_id` 为 MediaCrawler 脱敏的 `creator_hash`，不含原始用户 ID；
- `post_url` 已去除 `xsec_token`；
- 控制采集频率，遇验证码人工通过，不做验证码破解、不挂代理池、不夜间大规模采集；
- 数据仅用于课程研究，不公开、不商用。
