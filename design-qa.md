# 0.4.2 视觉实现验收

**Findings**

- [P1] 浏览器渲染证据缺失，无法完成设计稿与实现的同屏对照
  - Location: 沉浸式单句练习画布，桌面主状态。
  - Evidence: 设计稿已成功打开；本地前后端也已在隔离数据目录中启动并通过 HTTP/接口检查，但应用内浏览器在建立截图连接时持续返回 `Trusted RPC dependency must resolve within a configured trusted code path`，因此没有生成实现截图。只读排查确认插件文件、配置中的受信路径和服务映射均存在，故障位于当前 Codex/Browser runtime 的信任环境或 Windows 路径规范化层。
  - Impact: 无法基于实际像素验证字体、间距、颜色、图标、折行、可见状态及 1440 × 1024 视口中的区域比例。按照 Product Design QA 规则，这会阻止视觉验收通过。
  - Fix: 完全重启 Codex 后重试应用内浏览器，并在同一 1440 × 1024 视口打开第 4 句截图；若仍失败，则由用户明确允许使用 Playwright，再执行同状态截图、同屏比较和必要的修正循环。

**Comparison Target**

- Source visual truth path: `C:\Users\31557\.codex\generated_images\01a01944-5433-7f41-b3c5-d7ba723415cd\exec-bc3a09c7-8daf-4bcb-b46d-27988dcefb90.png`
- Implementation URL: `http://127.0.0.1:5174/`
- Implementation screenshot path: unavailable; no screenshot file was created because the selected browser connection failed before capture.
- Viewport: target CSS viewport `1440 × 1024`; implementation viewport could not be programmatically confirmed.
- Source pixels: `1440 × 1024`.
- Implementation pixels: unavailable.
- Density normalization: source is treated as 1×; implementation `deviceScaleFactor` is unavailable, so density normalization was not performed.
- State: Chinese interface; material `高效能人士的七个习惯`; sentence `4 / 12`; source text `Small habits compound into remarkable results.`; translation `小习惯会累积成非凡的结果。`; prior evaluation overall score `86`.

**Full-view Comparison Evidence**

- Source full view was opened and inspected at 1440 × 1024.
- The implementation was served from a fresh 0.4.2 baseline database and the matching state was verified through real APIs: Chinese preferences, 12 sentences, sentence 4 content, and the saved score/alignment record are present.
- No browser-rendered implementation image is available. Code structure, API responses, unit tests, and build output are not substitutes for visual comparison, so no fidelity judgment is claimed.

**Focused Region Comparison Evidence**

- Not performed. The required full implementation capture is missing, so focused comparisons of header/navigation, sentence typography, timeline/recording dock, and evaluation panel would create false precision.

**Required Fidelity Surfaces**

- Fonts and typography: blocked pending rendered comparison.
- Spacing and layout rhythm: blocked pending rendered comparison.
- Colors and visual tokens: blocked pending rendered comparison.
- Image quality and asset fidelity: the target contains no photographic/illustrative assets; rendered icon alignment and sharpness still require a screenshot.
- Copy and content: realistic matching content is present in the isolated baseline data, but wrapping and optical balance remain unverified.
- Responsiveness and accessibility: automated semantic tests cover tab navigation state, drawer focus return/Escape, sentence progress state, language preferences, word collection, alignment and evaluation localization. Desktop/tablet/mobile rendered layouts and visible focus/contrast remain unverified.

**Primary Interactions Tested**

- Automated frontend suite: 13 test files, 40 tests passed.
- Covered behaviors include application panel state, material-load failure recovery, AI-text draft retention, provider refresh, header-popover focus/Escape, modal drawer focus trap/return, sentence selection/progress, word collection removal, multilingual alignment, localized evaluation, language preference hydration, and timeline logic.
- Browser interactions, responsive viewport checks, and browser console inspection: blocked by the selected browser connection failure.

**Open Questions**

- May the final screenshot pass use Playwright if the application-internal browser remains unavailable?

**Implementation Checklist**

1. Restart Codex and retry the application-internal browser connection, or receive explicit approval for Playwright.
2. Capture the implementation at 1440 × 1024, 1× density, sentence 4 / 12, Chinese UI.
3. Put the source and implementation captures into the same comparison input.
4. Check full view plus focused header, practice controls, and score panel regions.
5. Fix every actionable P0/P1/P2 issue and repeat the same-state capture.
6. Check desktop, tablet, and mobile interaction states plus console errors.

**Comparison History**

- Pass 0: source visual opened; implementation API state and local URL verified; capture failed before any visual comparison. No visual fixes were made because visible implementation evidence was unavailable.

**Follow-up Polish**

- None classified until a rendered comparison is available.

final result: blocked
