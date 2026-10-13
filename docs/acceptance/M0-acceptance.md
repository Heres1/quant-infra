# M0 验收记录（T0.6）

> 验收日期：2026-10-13 · 验收人：AI（记录）/ 用户（答辩待完成）· PR-05 演示留档

## CONSTRAINTS §6 T1 基础设施逐项核对

| 项 | 状态 | 证据 |
|---|---|---|
| cargo fmt --check | ✅ CI 绿 | run #2 job `fmt` |
| clippy -D warnings（含 unwrap_used 等禁用 lint） | ✅ CI 绿 | run #2 job `clippy` |
| cargo test --workspace（32 用例：TC-C1~C7、TC-T） | ✅ CI 绿 | run #2 job `test` |
| llvm-cov 覆盖率门槛（核心 ≥90%/全局 ≥70%，无代码自动跳过） | ✅ CI 绿 | run #2 job `coverage`（门槛脚本在 CI 实测工作） |
| cargo-deny（advisories/bans/licenses/sources） | ✅ CI 绿（首跑 licenses 失败已修复：workspace crate 补 license 字段） | run #2 job `deny` |
| gitleaks 全历史扫描 | ✅ CI 绿（首跑失败为根提交扫描区间问题，非泄密；本地全历史复扫 0 泄漏） | run #2 job `gitleaks` |
| 约束扫描器（AC-01/02/08、PR-04） | ✅ CI 绿 + 本地红测通过（注入违规全部抓出） | run #2 job `constraints` |
| #![forbid(unsafe_code)]（EN-02） | ✅ workspace lints 全 crate 生效 | 根 Cargo.toml |
| main 分支保护（EN-01/PR-08） | ✅ require PR + 7 个必过 check + require up-to-date + 禁 force push/delete + 取消 approvals（单人补偿，§4） | GitHub Settings → Branches |
| 仓库公开 + 工具链锁定 1.90.0 | ✅ | github.com/Heres1/quant-infra · rust-toolchain.toml |

CI 证据：`https://github.com/Heres1/quant-infra/actions/runs/38353247313`（7/7 绿）

## 本轮修复记录（S3 级，测试设施）

1. **deny 失败**：workspace crate 无 `license` 字段 → cargo-deny licenses 检查 error。修复：`license = "MIT"`（workspace.package + 两 crate）。
2. **gitleaks 失败**：首推时扫描区间 `根提交^..HEAD` 中 `^` 不存在 → git fatal。非泄密（本地全历史扫描 0 泄漏）。后续 push 自愈。
3. **本地环境**：全局 git 代理指向 127.0.0.1:7890（代理未运行）导致 rustup/git 超时；llvm-tools-preview 组件经 rsproxy.cn 镜像补装完成。

## 出口结论

M0 出口准则满足（CONSTRAINTS §6 全项绿 + 本记录留档）。答辩环节按用户 2026-10-13 指示免除（PR-03 二次修订），**M0 正式关闭**。详细测试数据见 `M0-TEST-REPORT.md`。
