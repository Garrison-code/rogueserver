<!--
SPDX-FileCopyrightText: 2026 Garrison-code

SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->

# Branch 與 CI 遷移 Roadmap（rogueserver）

這份文件只定義**目標與驗收條件**，詳細的實作步驟由負責實作的 agent 另外規劃。
pokerogue 有一份對應的文件：`pokerogue/docs/branch-migration-roadmap.md`，兩邊要一起進行。

## 背景

- 這個 repo fork 自 `pagefaultgames/rogueserver`。上游只有 `master` 一條 branch。
- 上游的 `ghcr.yml` 在 push 到 `master` 時，會建 `prod` 和 `beta` 兩種 image。這裡的 `beta` 是 Go 的 build tag，不是 branch。上游的 workflow 都有加 `github.repository == 'pagefaultgames/rogueserver'` 的條件，在 fork 裡不會執行。
- fork 時另外加了 `develop` branch，並在 `ci.yml`、`ghcr.yml`、`filter-changes.yml` 加了 develop 專用的 job。
- 原本部署用的 VPS 已經退掉，`notify-develop` 已經在 `develop` 上刪除（commit `ba616f99`）。
- 新的部署目標：Oracle Cloud Always Free 的 **ARM（arm64）** VM，用 docker compose 跑 rogueserver、MariaDB 和 pokerogue 前端，前面套 Cloudflare 免費方案。部署本身是第 4 階段，不在這份文件的範圍內。

## 目標狀態

| Branch | 角色 | 推送後的 CI 行為 |
|---|---|---|
| `master` | 唯一的主線，也是正式版 | 跑 Go 測試和建置，並建正式 image 推到 GHCR |
| `develop` | 廢除 | — |

- 正式 image 要同時支援 `linux/amd64` 和 `linux/arm64`。
- 開發時用 feature branch 開 PR 到 `master`，跟上游一樣。

## 第 1 階段：在 `develop` 上整理 GitHub Actions

先在 `develop` 上改好，第 2 階段合進 `master` 時才會照新規則觸發。

### 目標

1. **`ghcr.yml`**
   - 觸發 branch 從 `[master, develop]` 改成只有 `master`。
   - Tag 對應改成 `master` → `latest`，不再產生 `develop` tag。
   - 刪除只為 `develop` 服務的部分：`quality` 的 develop 判斷、「Confirm develop is still current」，以及只驗證 develop image 的 `registry-ready`。如果 `registry-ready` 對 `master` 也有用，就保留並拿掉 develop 判斷。
   - Build 平台從 `linux/amd64` 改成 `linux/amd64,linux/arm64`。Dockerfile 裡的 Go 交叉編譯要確認能正確產出 arm64 的 binary。
2. **`ci.yml`**：刪除 develop 專用的 `develop-linux` 和 `deployment-tooling` 兩個 job。上游原有的 `build` matrix 盡量回到跟上游一致，但要保留 fork 讓 CI 能在自己 repo 執行的必要修改，例如 repository 條件。
3. **`filter-changes.yml`**：拿掉只為 develop 或部署工具服務的路徑過濾，保留 `ci` 和 `ghcr` 兩個 output。
4. **`.github/scripts/`**：刪除 `publish_notify.py` 和 `test_publish.py`（舊 VPS 通知用）。如果刪完目錄變空，就把整個目錄刪掉。

### 驗收條件

- 沒有任何 workflow 會被 `develop` 觸發，也沒有任何 workflow 參照 `develop`。
- `ghcr.yml` 在 `master` push 時會建出 amd64 加 arm64 的 multi-arch image，tag 是 `latest`。
- 沒有任何 workflow 參照已刪除的腳本、`DEV_AUTO_DEPLOY_ENABLED`、`PROD_AUTO_DEPLOY_ENABLED` 或 pokerogue 部署協調相關的 secrets。
- `go test ./...` 和 `go build` 通過，`-tags=beta` 也要通過。

## 第 2 階段：把 `develop` 合進 `master`

### 目標

- 把 `develop` 的所有 commit（包含第 1 階段的改動）合進 `master`。
- `master` 上有 develop 沒有的 commit：`487a8d8c`（#3，內容跟 develop 的 #2 重複）和 `d0d2537a`（#4，正式部署自動化）。合併時以第 1 階段的結果為準：#4 加的正式部署流程要跟著第 1 階段一起移除，不能被合併帶回來。
- `master` 受 ruleset「Require PRs on beta/main/develop/master (Garrison-code bypass)」保護，`Garrison-code` 有 bypass。建議還是開 PR（`develop` → `master`），讓 CI 先跑一遍。

### 驗收條件

- `git log master..develop` 是空的，也就是 `develop` 的所有 commit 都已經在 `master` 上。
- `master` 上的 `.github/workflows/` 符合第 1 階段的驗收條件。
- 合併後 push 到 `master`，CI 通過，並成功發佈 multi-arch 的 `latest` image。

## 第 3 階段：同步上游 `master`

### 目標

- 把 `pagefaultgames/rogueserver` 的 `master` 合進 fork 的 `master`。
- 調查時（2026-11-01），fork 沒有落後上游任何 commit。這個階段只要確認，有新 commit 才合併。
- 建議在本機加一個 `upstream` remote 指向 `https://github.com/pagefaultgames/rogueserver.git`。
- 用 merge 同步，不要 rebase。

### 驗收條件

- `git log master..upstream/master` 是空的。
- `go test ./...` 通過，fork 新增的功能（import history、build info API）行為不變。

## 不在這份文件範圍內的事

- **第 0 階段**：Oracle Cloud、Cloudflare、Hostinger nameserver 的設定，由使用者自己處理。
- **第 4 階段**：VM 上的 docker compose（rogueserver、MariaDB、前端）、Cloudflare DNS、自動更新。
- **第 5 階段**：第一次正式發版並驗證。
- **第 6 階段**：
  - 刪除 `develop` branch。
  - 把 `develop` 從 ruleset 拿掉。
  - 更新 `docs/develop-deployment.md`、`docs/container-images.md` 等文件。
  - 清掉 repo 變數和 secrets。
  - 設定 MariaDB 備份。

## 待決定事項

1. **要不要另外發佈 `beta` build tag 的 image**（對應上游的 `beta` variant），給 pokerogue 的測試站用。
2. **arm64 的建置方式**：用 QEMU 模擬，或用 GitHub 的 `ubuntu-24.04-arm` 原生 runner。Go 也可以直接交叉編譯，在 Dockerfile 用 `GOARCH` 搭配 `--platform=$BUILDPLATFORM`，通常最快。
