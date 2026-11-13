## 写稿
- A/report.md：每条结论带 n、百分比、置信区间
- A/quotes.csv：quotable=true 的原话，按点赞排序，已用 user_code 匿名
> 引用时写"有网友评论"，不要出现 user_id 或主页链接

## 可视化
- A/agg_long.csv：列是 dimension, group, category, n, denom, pct, pct_lo, pct_hi
- A/labeled.csv：自己切维度时用
- 三条口径必须口头+书面都交代：
    1. 态度表的分母是 relevant=true 且 object 为 self/relation/cp 的评论， 不是原始条数，也不是全部相关评论（聊剪辑、聊网友、磕 CP 的不算）
    2. reason/value 是多选题，占比之和 > 100%
    3. 不同平台不要混算，group 列已经分好了
