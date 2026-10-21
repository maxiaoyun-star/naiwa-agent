# CAS 接入说明（长春理工大学）

## 1. 已核实的登录流程

对着线上页面逐字段核对过，`naiwa/campus/cas.py` 按这个流程实现：

| 步骤 | 请求 | 关键点 |
|---|---|---|
| 1 | `GET https://mysso.cust.edu.cn/cas/login?service=https://portal.cust.edu.cn/custp/shiro-cas` | 返回 HTML 表单，隐藏字段 `execution`；下发 `JSESSIONID`、`PAC4JDELSESSION` |
| 2 | `GET https://mysso.cust.edu.cn/cas/captcha?ts=<毫秒>` | 返回 PNG，**必须与步骤 1 同一会话**，否则验证码永远不对 |
| 3 | `POST https://mysso.cust.edu.cn/cas/login?service=...` | 表单字段：`username`（一卡通号）、`password`、`captcha`、`execution`、`_eventId=submit`、`geolocation`、`submit=LOGIN` |
| 4 | 302 → `https://portal.cust.edu.cn/custp/shiro-cas?ticket=ST-xxx` | **登录成功靠 302 + ticket 判定**，不看页面文案 |
| 5 | `GET` 上面这个地址 | 门户校验票据并下发自己的会话 Cookie |

失败时 CAS 会重新渲染登录页（HTTP 200）并在页面里给出错误文案，
客户端按 `用户名或密码错误 / 验证码错误` 等关键词识别。

### 验证码是必填的

页面里虽然有 `captcha` 输入框，但**不能跳过**。本项目采取人工看图输入：
不写 OCR，也不尝试绕过——自动化识别既不可靠，也容易被风控判定为异常行为。

## 2. 还没拿到的：教务数据接口

门户里的「课表」「考试」是登录后由前端 JS 调用的 XHR 接口，没有公开文档。
所以 App 把它们做成**可配置**的，需要你用自己的账号抓一次包。

### 抓包步骤（电脑上做，5 分钟）

1. Chrome 打开 `https://portal.cust.edu.cn`，用一卡通号登录。
2. 按 `F12` → 切到 **Network** 面板 → 勾上 **Fetch/XHR** 过滤。
3. 在门户里点开「我的课表」，等页面加载完。
4. 在 Network 列表里找**返回 JSON 的那一条**（Response 里能看到 `kcmc` / `课程名称` 之类的字段）。
   - 右键 → Copy → Copy link address，得到完整 URL。
   - 如果 URL 里带 `?week=1` 之类的参数，只保留到 `?` 之前的部分即可（App 会自己拼参数）。
5. 对「考试安排」重复 3–4 步。
6. 打开 App → 设置 → **教务接口**，把两个地址填进去，保存。

### 字段格式要求

App 的解析层是宽容的，只要返回体是 JSON 数组，或者下面是数组的常见包装
（`data` / `rows` / `list` / `items` / `data.rows` / `kbList`），就能吃下：

课表字段（任一别名即可）：

| 含义 | 可用字段名 |
|---|---|
| 课程名 | `kcmc` `courseName` `name` `课程名称` |
| 教师 | `jsxm` `teacher` `xm` `任课教师` |
| 教室 | `cdmc` `room` `classroom` `上课地点` |
| 星期 | `xqj` `weekday` `dayOfWeek` `星期` |
| 节次 | `jcs` `sections` `节次` |
| 周次 | `zcd` `weeks` `周次` |

考试字段：`kcmc` / `ksrq`（日期）/ `kssj`（时间）/ `kscdmc`（考场）/ `zwh`（座位）。

如果字段名不在上面，改 `naiwa/campus/portal.py` 顶部的 `COURSE_KEYS` / `EXAM_KEYS` 即可，
不用动解析逻辑。

### 用脚本批量试

登录态复杂时，用命令行探测更省事（需要 `requests` 之外零依赖）：

```bash
python scripts/probe_portal.py \
  --user 2021xxxx --path /custp/api/kbcx --path /custp/api/kscx
```

脚本会：拉验证码 → 存 `captcha.png` 并自动打开 → 你输入图片里的字符 → 登录
→ 逐条请求候选路径 → 打印状态码、Content-Type 和前 200 字。
哪条返回 JSON，就把那条填进 App。

## 3. 安全与合规

- 只保存**会话 Cookie**，默认不保存密码；密码只在用户明确打开「记住密码」时加密存储。
- 所有请求只打学校域名（`mysso.cust.edu.cn` / `portal.cust.edu.cn`），不经过任何第三方服务器。
- 不在仓库、日志、崩溃信息里输出学号与密码；`Body` 里的提示也不会回显密码。
- 本项目不绕过任何权限控制：能用什么数据，取决于登录账号本身的权限。

## 4. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 一直提示「验证码错误」 | 取图和提交用了两个会话 | 本项目已保证同会话；若二次开发改动过 `CampusService.begin_login`，检查是否复用了同一个 `CasClient` |
| 登录成功但查课表 401 | 门户会话 Cookie 未带走 | 检查 `CookieJar.header_for()` 是否匹配到 `portal.cust.edu.cn` 域 |
| 接口返回 HTML | 抓错请求（抓到页面而不是 XHR） | 只选 Response 是 JSON 的那条 |
| 提示「登录已过期」 | Cookie 有有效期 | 重新登录 |
| 首次进入很慢 | 学校服务器在校外访问慢 | 换校园网 / VPN |
