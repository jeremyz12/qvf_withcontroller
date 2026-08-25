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
