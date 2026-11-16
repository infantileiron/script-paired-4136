# 清音 · 话术切换配对评估

为客户成功团队核对同一顾问更换续约话术前后的抽检得分，将样本完整性、统计证据和业务采纳分开记录。

## 场景与模块

清音客户成功有两组共40位顾问。当前组长导出 `清音_续约抽检_20261115.xlsx`，人工匹配两周得分，分析师计算差值后把结论贴到周会纪要。痛点是漏配对被补零、均值改善被误当因果、采纳意见缺乏证据版本。上游是沟通质量抽检；本项目替代配对核对、统计和采纳留痕；下游是组长制定下一周话术试点范围。

四个业务模块：配对样本（录入/修订）、排除核对、效应评估（后台任务/冻结结果）、采纳意见（起草/签核）。三类业务实体是 Pair、Evaluation、Adoption；另有用户和审计记录。已有报告不会随原始样本修订而改变。

第五个模块是**差分隐私匿名发布（AnonRelease）**：对外分享时不导出顾问编号、原始得分与内部原报告，只发布“固定评估名单”内完整配对差值的**裁剪均值 + 拉普拉斯噪声**及机制参数。内部冻结原报告仍保留在效应评估中，匿名产物不引用任何个体。

|角色|页面与权限|典型动作|
|---|---|---|
|admin|全部，独占审计和签核|签核采纳意见|
|analyst|业务读写、计算、导出|补录缺失后新建评估|
|viewer|全部业务只读、导出|下载冻结结果；后端拒绝写操作|

## 启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18214](http://localhost:18214)，后端 [localhost:19214/docs](http://localhost:19214/docs)，PostgreSQL映射17714。种子账号为 `admin@demo.local` / `analyst@demo.local` / `viewer@demo.local`，密码均 `Demo123!`。启动 `SEED_DEMO=true` 自动执行一次种子；再次执行不增加相同顾问或覆盖人工修订。演示包括40顾问、2个业务组、2个不完整配对。

## 一天的操作剧本

1. 08:50 viewer 查看QY-001至QY-040的前后测。
2. 09:00 analyst 进入排除核对，检查QY-039缺前测和QY-040缺后测。
3. 09:10 在配对样本补录 `QY-041`、企业一组、前测70、后测77。
4. 09:20 修订时填写记录ID和完整字段，并说明两次抽检都用7日窗口。
5. 09:30 创建“11月续约话术配对复核”，选择全部或一个业务组。
6. 09:40 worker完成计算，点击刷新，核对差值、95%CI与两种p值。
7. 10:00 analyst 在采纳意见选择该评估，写明客户结构和限制，起草“继续试点”。
8. 10:10 admin登录并签核；10:20 viewer 下载 `script-paired-<id>.json`。

## 计算口径

输入是同一顾问的前后抽检平均分（0–100），一位顾问只允许一个唯一编号。缺任一侧时整对排除，不补零。至少3个完整配对，差值标准差必须大于零。令 d=后测−前测，t=mean(d)/(sd(d)/sqrt(n))，自由度n−1，双侧p与95%t区间；Cohen dz=mean(d)/sd(d)。配对t假定顾问之间独立，差值近似正态。

符号翻转以abs(mean(d))为统计量，≤16对穷举2^n种符号，取不小于观察统计量的占比；更大样本固定numpy seed=1115、10000次抽样，p=(extreme+1)/(10000+1)，比较时用1e−12容差。零假设下需差值符号可交换。前后观测可能受客户结构/季节影响；统计结果不会直接触发话术发布。

提交任务时冻结全部输入，worker保存完整配对、排除原因、checksum、seed和计算次数。无效输入返回422；重复编号409；样本不足/零方差的任务置failed，提示修复后重新提交；队列故障返回503。单worker启动时恢复queued/running任务。

## 匿名发布与差分隐私口径

- **固定评估名单**：只能对 `state=done` 的评估发起；名单取评估冻结快照中前后测均非空的顾问编号，提交即写入 `anon_releases.roster` 并排序冻结，重试不再重新选样，因此后续样本修订不影响已提交发布。
- **裁剪与聚合**：对名单内每位顾问的差值 d=后测−前测，先逐一裁剪到可设的 `[lower, upper]`（`upper>lower`，无效返回422），再求算术均值。名单为空或评估未完成返回409。
- **替换一位顾问的敏感度**：发布量仅一个标量（裁剪均值）。名单长度 n、裁剪宽度 w=upper−lower 时，替换一位顾问至多使均值改变 `w/n`，即全局敏感度 Δ=w/n（纯 ε-DP，δ=0）。
- **拉普拉斯机制**：噪声尺度 `b=Δ/ε`，加噪均值=裁剪均值+Laplace(b)。噪声由申请 ID 与机制参数经 SHA-256 反采样**确定性生成**，不依赖 NumPy 随机态：同一申请重试复用同一噪声。
- **累计隐私预算账**：每位顾问一个 `privacy_budgets` 账户，共享总额 `TOTAL_EPSILON=4.0`；**跨组、跨评估、跨所有发布**统一在该顾问账户上累计扣账，每次发布对名单内每人扣本次 ε。任一顾问会超额则**整次拒绝、整笔回滚、不产生流水与产物**；恰好等于上限允许（402 为入队前预检，worker 事务内再以锁+行锁终判）。
- **并发不透支**：worker 处理发布前先取分布式预算锁（Redis `SET NX PX`，无 Redis 时退化为进程内锁），PostgreSQL 再叠加事务级咨询锁与预算行 `SELECT … FOR UPDATE`（按编号固定顺序），并以预算流水 `(release_id, consultant_code)` 唯一约束兜底。
- **状态机与重试**：`pending → downloadable | failed`。重试同一申请复用原噪声且**不重扣**（流水幂等）；队列重复投递到已 downloadable 的申请直接跳过。
- **崩溃可恢复 / 下载可见即已扣账**：预算扣账与 downloadable 状态在**同一事务先提交**，随后才写临时文件并 `os.replace` 原子替换。worker 启动 `recover_pending`：downloadable 但文件丢失则据 DB 结果重建（不重扣）；pending/failed 清理 `.tmp` 后重新入队。下载接口以 DB 的 downloadable 为准，故“可下载”恒等价于“已扣账”。
- **对外产物** `anon-release-<id>.json` 仅含机制名、adjacency、n、裁剪界、敏感度、ε、δ、噪声尺度 b 与加噪均值，**不含**顾问编号、原始/裁剪后差值、内部未加噪均值；内部原报告仍可在效应评估页导出。页面“匿名发布”可查每位顾问预算总额/已用/剩余与全部发布状态。

数据实体新增 `anon_releases`、`privacy_budgets`、`privacy_ledger` 三表（见 migrations DDL，ORM 首次建表）。

## 工程与本地开发

Python3.11/FastAPI/SQLAlchemy/SciPy/NumPy/PyJWT、原生ES modules/CSS、Nginx、PostgreSQL16、Redis7。五个服务均有健康检查；backend等待数据库/Redis，worker还等backend，frontend等backend。数据库、Redis、产物用命名卷。Nginx的 `/api/` 转发到后端根路由。只有数据库、后端和前端映射宿主端口。worker心跳位于容器 `/tmp/heartbeat`，结果共享卷 `/artifacts`。`docker compose down -v --remove-orphans` 清理本项目测试数据。

本地开发可启动db/redis后，在backend安装 requirements，设置 DATABASE_URL/REDIS_URL/JWT_SECRET，`uvicorn src.main:app --reload`；前端建议仍用Nginx代理，也可设置本地同源代理。`backend/src`按routes/controllers/services/models/schemas/middlewares/config/utils分工；`frontend/src`按api/stores/pages/components/hooks/utils/constants/types/router分工。ORM首次建表，`backend/migrations/001_initial.sql`保留对应DDL；不包含在线版本迁移框架。

环境变量详见 `.env.example`：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET。显式子网10.253.115.0/24用于规避当前机器默认池耗尽，可迁移时调整。生产使用需替换演示凭据与JWT密钥。

共享枚举：角色ROLES、任务状态STATES、业务组TEAMS、决定DECISIONS、发布状态RELEASE_STATES；后端 `src/constants/enums.py`、schemas/business.py 与前端 `src/constants/enums.js`，持久化列见models/entities.py。共用表格、表单字段、状态标签组件；表单hooks与HTML转义工具；请求ID、安全响应头两个中间件，业务写入审计。

## 测试

后端测试不依赖 Docker/Redis/PostgreSQL：用 SQLite（WAL + busy_timeout）与进程内 broker 即可运行，覆盖隐私机制（敏感度/裁剪/确定性噪声/相邻口径）、固定与重叠名单、并发争抢不透支、重试复用噪声不重扣、写文件中断恢复、API 权限与对外产物脱敏。

```sh
cd backend
python -m virtualenv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
JWT_SECRET=unit-test-secret-32bytes-minimum-0001 \
DATABASE_URL=sqlite:////tmp/anon-test.db REDIS_URL= ARTIFACT_DIR=/tmp/anon-art \
python -m pytest tests/ -q
```

`REDIS_URL` 留空时 `src/services/broker.py` 自动回退进程内 FIFO 队列与线程锁；生产配置 Redis 后使用 `SET NX PX` 分布式锁与持久化队列，业务代码不变。

范围：逐条表单/API录入，无Excel导入、删除、多人并发任务调度或外部话术发布；采纳在站内签核。使用单worker；时间/窗口由业务填入说明，不自动验证客户结构。Google Fonts不可用时回退serif/sans-serif。测试、截图和已知差异在 `../../test-artifacts/gb-3115/TESTING.md`，源码不放证据。许可证 MIT，见 LICENSE。
