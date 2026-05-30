# Blabla Link 每日签到

青龙面板脚本，自动完成 Blabla Link（NIKKE 社区）每日任务，支持积分兑换。

## 环境变量

### 方式一：直接提供 Cookie（推荐）

```
BLA_COOKIE=game_token=xxx; game_openid=xxx; game_uid=xxx; ...
```

多账号用 `&`、`,` 或换行分隔，可用 `#` 添加备注：

```
BLA_COOKIE="token1 # 小号\ntoken2 # 大号"
```

### 方式二：通过 Worker 登录（自动获取 Cookie）

```
BLA_ACCOUNT="邮箱#密码#备注"
```

多账号：

```
BLA_ACCOUNT="邮箱1#密码1#备注1\n邮箱2#密码2#备注2"

*：青龙面板直接在环境变量回车代替`\n`就行
```

脚本会调用 `https://nikke-cdk-test.hayasa.org/api/login` 获取 Cookie，并自动缓存到 `.blabla_cache/` 目录。下次运行优先使用缓存，失效后自动重新登录。

## 积分兑换

```
BLA_EXCHANGE="[Global] 珠寶 ×320,[Global] 珠寶 ×30,[Global] 指揮官見面禮：芯塵 ×30"
```

可同时兑换多个商品，逗号分隔。脚本会：

1. 检查本地缓存是否本月已兑换 → 跳过
2. 检查积分是否足够 → 不够则跳过
3. 调 API 兑换 → 成功或已达上限均记录缓存

### 性价比参考

| 商品 | 积分 | 珠宝/积分 |
|------|------|-----------|
| 珠寶 ×320（折扣） | 4999 | **0.0640** |
| 珠寶 ×30（折扣） | 499 | **0.0601** |
| 珠寶 ×60 | 999 | 0.0601 |
| 珠寶 ×120 | 1999 | 0.0600 |
| 芯塵 ×30 | 1 | 约等于白送 |

## 每日任务

脚本自动完成以下任务：

- 每日签到（+100pts）
- 瀏覽5個貼文（+70pts）
- 按讚5個貼文（+30pts）
- 遊玩遊戲（需游戏内完成，检测已完成后领奖）

## 验证码处理

部分账号登录时可能触发腾讯滑块验证码。由于青龙面板无法弹出验证码界面，当触发验证码时，脚本会输出提示并跳过自动登录。

### 手动缓存 Cookie

同时设置 `BLA_COOKIE` 和 `BLA_ACCOUNT`，且 Cookie 有效时，脚本会自动将 Cookie 缓存到邮箱名下，后续运行直接走缓存、不再请求登录：

```
BLA_COOKIE="game_token=xxx; ..."
BLA_ACCOUNT="邮箱#密码"
```

BLA_COOKIE 和 BLA_ACCOUNT 按顺序一一对应（第1条 Cookie ↔ 第1个邮箱，第2条 ↔ 第2个，以此类推）。

**BLA_COOKIE 支持两种格式：**

1. 纯 Cookie：`game_token=xxx; game_openid=yyy`（记得 URL 编码 `&` → `%26`）
2. `邮箱#Cookie`：自动识别 `@` 前邮箱、`=` 后 Cookie 并交换

**手动补救流程：**

Worker 端点为纯 API，不支持浏览器直接访问。触发验证码时，需通过其他方式获取有效 Cookie 后设到 `BLA_COOKIE`，脚本会自动缓存到对应邮箱名下。或者直接使用 [Nikke-CDK-Tool](https://github.com/Small-tailqwq/Nikke-CDK-Tool) 来完成你的任务

## 缓存目录

`blabla/.blabla_cache/`，包含：

- `{邮箱hash}` — Cookie 缓存
- `exchange_{cookie_hash}.json` — 兑换月记录

可用 `BLA_CACHE_DIR` 环境变量自定义路径。

## 青龙面板配置

1. 创建定时任务，执行频率推荐 `30 8 * * *`
2. 添加环境变量 `BLA_ACCOUNT` 或 `BLA_COOKIE`
3. 可选：添加 `BLA_EXCHANGE` 启用自动兑换
