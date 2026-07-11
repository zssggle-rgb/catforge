# V5-G08 进度

- Goal：不可变 RC、本地门禁、205 默认关闭部署、真数双跑、跨载体、V2/V4、回滚；
- active timer：`catforge-v5-g08-10`；
- 最终 RC：`sellpoint-value-pm-v5-rc7-9a5a147`；
- RC package：`ad1aceb49bd46c6031b936b91c6e15075786e7387b335597017e7f2752276ee7`；
- 本地：V5 73 passed、related 137 passed、analyst CLI 88 passed、coverage 93%、ruff/compileall passed；
- 205：18/18 SKU 双跑一致、P95 1.19s、tracemalloc 75.429MB、query 30、DB writes 0；
- 表面：65E7Q 5 行价值账、13 战场完整判断、0 未命名、双链接、飞书 user readback passed；
- 回归：V2 passed、V4 hash unchanged；
- 回滚：passed，最终恢复 RC7 default-off；
- 复核：method P0=0/P1=0；engineering P0=0/P1=0；PM P0=0/P1=0；
- 当前状态：待提交 G08 文档、artifact manifest/closure、删除定时器并关闭 Goal。
