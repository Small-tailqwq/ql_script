任务目标：
编写一个适用于青龙面板的脚本，用于完成 blabla link 的每日任务。

相关任务网页：
https://www.blablalink.com/mission

网页所有的cookie：
（最好是找到完成任务所需的最小token，如果实在没有的话，可以在脚本中添加token持久化，环境变量用于记录账号密码）
（账号密码登录相关内容可在 `"C:\Users\Ko_teiru\Documents\code\Nikke-CDK-Tool\cloudflare-worker\Nikke-CDK-Combined_Dev.js"` 中找到，该 worker 部署 url 为：`
https://nikke-cdk-test.hayasa.org/`
```
__ss_storage_cookie_cache_game_id__	29080	.www.blablalink.com	/	2027-05-30T07:11:31.000Z	40						Medium
__ss_storage_cookie_cache_lang__	zh-TW	.www.blablalink.com	/	2027-05-30T07:11:55.000Z	37						Medium
game_adult_status	1	.blablalink.com	/	2026-06-29T07:11:31.234Z	18	✓	✓	None			Medium
game_channelid	131	.blablalink.com	/	2026-06-29T07:11:31.234Z	17	✓	✓	None			Medium
game_gameid	29080	.blablalink.com	/	2026-06-29T07:11:31.234Z	16	✓	✓	None			Medium
game_login_game	0	.blablalink.com	/	2026-06-29T07:11:31.234Z	16	✓	✓	None			Medium
game_openid	13161285947484504729	.blablalink.com	/	2026-06-29T07:11:31.233Z	31	✓	✓	None			Medium
game_token	32fe717858e36b1fc7e7875e5ae5de5f0183c342	.blablalink.com	/	2026-06-29T07:11:31.234Z	50	✓	✓	None			Medium
game_uid	3447419455688161	.blablalink.com	/	2026-06-29T07:11:31.234Z	24	✓	✓	None			Medium
game_user_name	Ko_teiru	.blablalink.com	/	2026-06-29T07:11:31.234Z	22	✓	✓	None			Medium

```

可用 MCP：
chrome-devtools
js-reverse