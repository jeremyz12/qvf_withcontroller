# Label Studio 人工评测:使用说明(2026-08-25 搭建)

## 现状
- 服务已在本机运行:http://localhost:8080
- 项目「WikiState 金答案人工核对」已建,60 题已导入(界面:题型+问题+金答案
  高亮+状态链表格+约定,快捷键 1=一致 2=不一致 3=不确定,备注栏)
- 管理员账号在 `labelstudio_admin.txt`(未入 git)

## 组员怎么参与
1. 同一网络下访问 http://192.168.50.216:8080(首次外部访问 Windows 会弹
   防火墙允许,点允许);
2. 邀请方式:你登录后 → 右上角 Organization → 复制邀请链接发组员,
   组员自行注册账号 → 进项目点 Label All Tasks 开标;
3. **多人标注设置(重要)**:项目 Settings → Annotation →
   "Annotations per task (minimum)" 设为 3(或组员人数)——否则一人标过的题
   不会再分给别人,算不了一致性。

## 标完之后
项目页 → Export → JSON,把文件给 Claude:自动计算总体/分题型一致率、
Fleiss' κ(≥3 人)、被质疑题清单与备注汇总,并与 artifact 评分页结果合并对照。

## 服务管理
- 服务随本机会话运行;重启电脑后重新启动:
  label-studio.exe 位于 Store Python Scripts 目录,命令:
  `$env:LABEL_STUDIO_BASE_DATA_DIR="D:\ZZL_cluade\labelstudio_data2"; & <label-studio.exe> start --port 8080 --no-browser`
- 数据都在 D:\ZZL_cluade\labelstudio_data2(SQLite),备份拷目录即可。

## 论文里怎么写
"60 项分层抽样,N 名标注者每题独立核对(Label Studio),标注指南含四条
判分约定与两条争议约定专问;报告一致率与 Fleiss' κ;不一致项经作者裁决并
在数据集 v2 中修正(见 dataset audit)。"

---

# 公网部署版(2026-08-26,Vultr Sydney)

- **正式地址:https://rate.wikistate.org**(2026-08-26 起,Cloudflare 代理 + Caddy 自动 HTTPS;旧 IP http://149.28.167.100 仍可达,经 Caddy 反代)
- 2026-08-26 增强 v2:链条改为**真 HTML 表格**(HyperText 渲染),每题下方常显
  "RAW MEMORY" 滚动盒 = 该角色**全部会话的全部用户消息逐字全文**(33-35 会话,
  锚点句黄色高亮、所在会话带 anchor #k 徽章;助手回复省略——状态宣告只出现在
  用户消息)。重建脚本 `scripts/build_labelstudio_html.py`
  - 技术要点:HyperText 在 iframe 里渲染,config 的 Style 进不去 → `<style>`
    必须嵌在任务数据 HTML 里;LS 按 iframe 文档 scrollHeight 定高 → 滚动要放在
    **内层 div**(.scrollbox max-height:440px),放 body 上会把 iframe 撑到全文高;
    LS 的 Collapse 面板里放 HyperText 会在隐藏时量高(150px 固定)→ 弃用 Collapse
  - 推送模式:delete_tasks → PATCH config → import(有标注自动中止)

## 三人定稿分配(2026-08-28,launch 配置)

- **author** 149 题全量(角色=第一遍全检+分歧裁决,**不计入独立评审**);
- **senior1/senior2** 各 85/84 题 = 各自半区 + **20 条重叠集**(两位独立评审共同题,
  产出不含作者的 Cohen's κ);催化剂 5 道:author 全见,两位 senior 各遇 3 道;
- 论文口径:"every chain verified by the first author and ≥1 annotator independent
  of the authors; independent-annotator agreement measured on a 20-item overlap";
- 生成器 rateapp/gen_assignments_3p.py(复用 admin token 与题集,seed=20260828);
  数据集发放前全检:144 链 542 行锚点逐字/日期格式/非降序 全过(2026-08-28)。

## 自建核验站(2026-08-27 最终版:弃用 Label Studio)

- **动因**:LS 社区版无法隐藏他人标注(用户实测+源码核查),三组并行也只是缓解;
  用户裁定自建。
- **实现**:`rateapp/app.py`(Flask+SQLite,单文件)部署于 VPS
  `/opt/rateapp`(systemd 服务 rateapp,Caddy 反代 rate.wikistate.org → 127.0.0.1:8081);
  LS 容器已停用(数据留存 /opt/labelstudio/data,restart=no)。
- **机制**:专属链接制(无注册无密码,capability URL)——`/r/<token>` 每人固定分配
  ~56 题(149 题 × 每题恰 3 个不同的人 = 447 份,gen_assignments.py 确定性生成+断言校验);
  页面复用 LS 版的 chain_html/raw_html 渲染;1/2/3 快捷键;选 2/3 强制留言;
  **答案不可改**(首次提交为准);逐题计时;随时断点续做。
  **独立性物理隔离:评审只能看到自己的题,他人答案在系统里无入口。**
- **admin 面板**:`/admin/<token>`(只读)——每人完成数/用时中位/最后活跃 + 全局覆盖
  (几题已收满3份);60 秒自动刷新。
- **链接清单**:rateapp/rater_links.txt(gitignored;含 admin、user1-8、TEST 试用链接);
  人数变更:重跑 `python rateapp/gen_assignments.py --raters N` → scp appdata.json →
  服务器删 rate.db → systemctl restart rateapp。
- **收数**:ssh 取 /opt/rateapp/rate.db(answers 表:rater/item/verdict/note/ms/ts),
  按 item 跨评审合并算 κ;催化剂钥匙仍在 data/labelstudio_chainproj_map.json。

## 旧·三组并行设计(2026-08-27,已被自建站取代;LS 三项目已随停用废弃)

- **动因**:社区版无角色权限,任何成员可在数据表格中查看他人标注(用户实测证实;
  源码核查确认无"隐藏他人标注"开关,那是企业版功能)——单项目每题收 3 份的设计下,
  评审可能看到同题他人选项,独立性被破坏;
- **解法**:三个内容相同的项目 Group A(id5)/ B(id6)/ C(id7),各含同样 149 题,
  **每题只收 1 份**(maximum_annotations=1)——组内做题流永远只发零标注的空白题,
  "看见别人选项"在正常路径上不存在;每题在三组各收 1 份 = 恰好 3 份、必来自 3 人;
- **评审分组**:每人只做自己组的项目(邀请消息里指定 Group);8 人时 3/3/2,
  每人约 50-75 题;残余风险 = 跨组窥视(需刻意打开别组项目),纪律条款覆盖;
- **统计**:按 item_id 跨三项目合并;Fleiss' κ(每题恰 3 人)照常;
- 原单项目(id3)已删除(仅含 7 份试点标注,按计划作废)。

## 旧·单项目设计(2026-08-26,已被上节取代)

- **项目 3「WikiState Chain Verification (full coverage)」**:
  144 链全覆盖 + **5 道催化剂题**(注入错误的链,类型:日期偏移/删行/值互换/
  伪造锚点/伪造加行),共 149 题,中性编号 chain-001..149;
  **每题收 3 份**(maximum_annotations=3;用户定案:每人约 60 题 ≈2h → 需 8 人,
  7 人可行;"每人 60"是说明层约定,系统无按账号限额,总量由每题 3 份锁死 447),
  随机出题(Uniform sampling),英文指南挂在项目 Instructions;
  报 Fleiss' κ(每题恰 3 人,合规)+ 原始一致率 + 催化剂通过率
- 原项目 1(60 题金答案校准轮)已从服务器删除(0 标注,无损;任务集与配置
  留档 data/labelstudio_tasks_en.json + labelstudio_config_en.xml,可随时重建)。
  题级金答案的正确性改由推导保证:链经人工验证 + 算子为代码计算 + 约定已写进
  题面(v2 考场)并经批 3/数据集审计核过
- **催化剂题答案钥匙**:data/labelstudio_chainproj_map.json(id→uid/catch/注入
  说明,仅本地,勿导入 LS);构建脚本 scripts/build_labelstudio_chains.py
- 测试账号 test01(见 labelstudio_admin.txt):试点/演示用,统计时剔除其标注
- 流程:试点(作者自测)→ 发邀请链接 → 评审先做项目 1 再做项目 3 →
  API 拉取 → 统计 → 分歧裁决 → 数据集 v2 修正
- 管理员账号同 labelstudio_admin.txt;容器 `labelstudio` 自动重启,数据持久在
  服务器 /opt/labelstudio/data(本机关机不影响收数据)
- 组员参与:发地址 → 组员 Sign Up 注册 → 进项目 Label All Tasks
- **必做设置**:项目 Settings → Annotation → Annotations per task (minimum) 设为
  组员人数(默认 1,不改算不了一致性)
- 域名/HTTPS:买好域名后加 Caddy 反代(找 Claude,10 分钟)
- 服务器运维:ssh -i ~/.ssh/wikistate_vps root@149.28.167.100;
  重启容器:docker restart labelstudio
