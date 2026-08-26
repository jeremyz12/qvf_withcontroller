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

- **地址:http://149.28.167.100**(60 题项目已导入,与本地版同源同序)
- 2026-08-26 增强 v2:链条改为**真 HTML 表格**(HyperText 渲染),每题下方常显
  "RAW MEMORY" 滚动盒 = 该角色**全部会话的全部用户消息逐字全文**(33-35 会话,
  锚点句黄色高亮、所在会话带 anchor #k 徽章;助手回复省略——状态宣告只出现在
  用户消息)。重建脚本 `scripts/build_labelstudio_html.py`
  - 技术要点:HyperText 在 iframe 里渲染,config 的 Style 进不去 → `<style>`
    必须嵌在任务数据 HTML 里;LS 按 iframe 文档 scrollHeight 定高 → 滚动要放在
    **内层 div**(.scrollbox max-height:440px),放 body 上会把 iframe 撑到全文高;
    LS 的 Collapse 面板里放 HyperText 会在隐藏时量高(150px 固定)→ 弃用 Collapse
  - 推送模式:delete_tasks → PATCH config → import(有标注自动中止)
- 管理员账号同 labelstudio_admin.txt;容器 `labelstudio` 自动重启,数据持久在
  服务器 /opt/labelstudio/data(本机关机不影响收数据)
- 组员参与:发地址 → 组员 Sign Up 注册 → 进项目 Label All Tasks
- **必做设置**:项目 Settings → Annotation → Annotations per task (minimum) 设为
  组员人数(默认 1,不改算不了一致性)
- 域名/HTTPS:买好域名后加 Caddy 反代(找 Claude,10 分钟)
- 服务器运维:ssh -i ~/.ssh/wikistate_vps root@149.28.167.100;
  重启容器:docker restart labelstudio
