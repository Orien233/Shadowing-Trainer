# 0.4.2 视觉实现验收

**Findings**

- 未发现仍需处理的 P0、P1 或 P2 问题。最终桌面稿与参考设计保持相同的信息层级和主任务路径：顶部导航、12 句进度、单句正文与译文、词级诊断、真实音频波形、三段式练习操作、历史评分及针对性重练入口均可见且可用。

**Comparison Target**

- Source visual truth path: `C:\Users\31557\.codex\generated_images\01a01944-5433-7f41-b3c5-d7ba723415cd\exec-bc3a09c7-8daf-4bcb-b46d-27988dcefb90.png`
- Implementation URL: `http://127.0.0.1:5173/`
- Final desktop screenshot: `E:\Zdragon\shadowing\Shadowing_v0_4\.codex-run\design-qa\implementation-desktop-pass7.png`
- Final tablet screenshot: `E:\Zdragon\shadowing\Shadowing_v0_4\.codex-run\design-qa\implementation-tablet.png`
- Final mobile screenshot: `E:\Zdragon\shadowing\Shadowing_v0_4\.codex-run\design-qa\implementation-mobile-390.png`
- Browser report: `E:\Zdragon\shadowing\Shadowing_v0_4\.codex-run\design-qa\playwright-report.json`
- Desktop viewport and pixels: source `1440 × 1024`; implementation CSS viewport `1440 × 1024`, screenshot `1440 × 1024`, `deviceScaleFactor = 1`, `devicePixelRatio = 1`.
- Additional viewports: tablet `1024 × 768`; mobile `390 × 844`; both at 1× density.
- Density normalization: none required; source and final desktop implementation were compared at equal pixel dimensions and 1× density.
- State: Chinese interface; material `高效能人士的七个习惯`; sentence `4 / 12`; text `Small habits compound into remarkable results.`; translation `小习惯会累积成非凡的结果。`; restored evaluation score `86`; historical recording ready.

**Full-view Comparison Evidence**

- The source and final desktop screenshot were opened together in one original-resolution comparison input after pass 7. The final page preserves the reference composition: compact product header, long sentence rail, centered single-sentence canvas, waveform/player, three primary practice actions, score band, issue rows, and persistent sentence navigation.
- Desktop geometry is exact to the target viewport: document `scrollWidth = 1440`, `scrollHeight = 1024`, body width `1440`; the footer occupies the final `64 px` without clipping or extra vertical scroll.
- The implementation intentionally uses real product data instead of fabricated visual data. The waveform is decoded from the material audio and normalized only against its own 95th-percentile peak, so quiet files remain legible while their relative audio shape is preserved.
- The tablet and mobile captures were inspected at original resolution. Tablet content remains readable and scrollable. Mobile has no horizontal overflow (`scrollWidth = bodyScrollWidth = 390`), the material rail does not overlap the practice dock, the fixed footer does not overlap the practice dock, and previous/next controls remain visible.

**Focused Region Comparison Evidence**

- Header/navigation: icon family, active tab, material title, language control, help and settings alignment were inspected at original resolution. Primary tab keyboard navigation and popover focus return were also exercised.
- Sentence/practice region: display typography, translation hierarchy, token status colors, waveform clarity, audio duration, control grouping, recorded-state copy, and keyboard hints were inspected. The source and implementation were large enough at 1440 × 1024 that separate raster crops were unnecessary.
- Evaluation/footer region: score hierarchy, green metric bars, word-level issue rows, replay/retry affordances, detail disclosure, shortcut legend, and sentence navigation were inspected at original resolution.
- Responsive focus: tablet and 390 px mobile screenshots were opened separately to inspect wrapping, tap targets, fixed navigation, and overlap boundaries.

**Required Fidelity Surfaces**

- Fonts and typography: the implementation uses the product's existing system-font stack, with source-aligned dark navy display text, strong sentence weight, restrained body copy, stable line height, and no desktop truncation. Mobile wraps the English sentence into two balanced lines without clipping.
- Spacing and layout rhythm: desktop sections fill exactly one 1440 × 1024 viewport; spacing between sentence, diagnostics, player, action dock, score band, and footer is consistent. Tablet and mobile preserve hierarchy without horizontal overflow or persistent-control collisions.
- Colors and visual tokens: the implementation maps the reference navy, primary blue, success green, warning amber, light borders, and white surfaces through shared CSS tokens. Active, success, review, disabled, and focus states remain semantically distinct.
- Image quality and asset fidelity: the target contains no photographic or illustrative assets. Icons come from the project's Phosphor icon library; no emoji, handcrafted SVG, CSS illustration, placeholder image, or fake waveform is used.
- Copy and content: labels are localized, standalone, and product-specific. Evaluation text and issue rows are derived from saved results and alignment data. The implementation does not invent IPA or dictionary definitions that are absent from the product data model.
- Accessibility and interaction: semantic tabs/buttons/dialogs, labels, keyboard arrow navigation, Escape handling, focus return, reduced-motion handling, accessible waveform range input, and practical mobile tap targets were checked.

**Primary Interactions Tested**

- Primary tab ArrowRight navigation: passed.
- AI text workspace navigation and return to practice: passed.
- Material drawer open, Escape close, and focus return: passed.
- Language popover initial focus, Escape close, and focus return: passed.
- Help dialog focus, Escape close, and focus return: passed.
- Evaluation details disclosure open/close: passed.
- Historical recording playback: advanced to `0.51 s`, remained playing, `readyState = 4`, no media error.
- Reference segment playback: advanced to `13.51 s`, remained playing, `readyState = 4`, no media error, waveform range advanced.
- Real audio responses returned `200`/`206` with `audio/wav`. Console errors, page errors, failed requests, and HTTP errors were all zero for desktop, tablet, and mobile. Media requests reported as `ERR_ABORTED` occurred only during expected element replacement/context teardown after successful audio responses.

**Open Questions**

- None blocking acceptance.

**Implementation Checklist**

- [x] Match the 1440 × 1024 reference state and content.
- [x] Restore scored recording playback and actionable word-level feedback.
- [x] Render actual decoded segment waveforms with an accessible seek control.
- [x] Keep the desktop footer inside the viewport.
- [x] Keep mobile material, recording, and sentence-navigation controls reachable and non-overlapping.
- [x] Verify core navigation, popovers, playback, responsive layouts, console, requests, and media responses in the user-approved Chrome/Playwright run.

**Comparison History**

- Pass 0 — blocked: the native in-app browser failed before capture with a trusted-path runtime error. After the user explicitly authorized Playwright, QA resumed with Google Chrome through Playwright Core.
- Pass 1 — blocked: the desktop footer was clipped, favicon returned 404, the saved evaluation did not restore its recording-ready state, and the player lacked a real waveform. Fixes: viewport/footer sizing, empty favicon, and initial scored-state work.
- Pass 2 — blocked: footer and console errors were fixed, but the reference state still lacked real recording playback, decoded waveform peaks, and actionable diagnostics. Fixes: recording audio endpoint, restored duration/playback, waveform component, and alignment-driven diagnostics.
- Pass 3 — blocked: real state and interactions were present, but the document height was `1078 px`, so the score area/footer exceeded the target viewport. Fix: compact feedback into a localized details disclosure and remove the redundant native audio control.
- Pass 4 — blocked: height fell to `1030 px`; mobile intermittently fell back from the waveform because Chrome reused an opaque media range-cache entry. Fixes: reduce stage bottom padding by `6 px` and fetch decoded audio with `cache: no-store`.
- Pass 5 — blocked: desktop reached exactly `1024 px`, all viewports decoded the waveform, and browser errors were zero; same-input comparison showed the real waveform was visually too quiet. Fix: normalize bars against the segment's real 95th-percentile peak while preserving relative shape.
- Pass 6 — blocked: waveform fidelity and both playback checks passed; mobile inspection found the fixed footer touching the practice dock by about `4 px`. Fix: reduce the mobile recorder top margin and add an explicit footer/dock overlap assertion.
- Pass 7 — passed: source and implementation were compared together again. Desktop remains exactly `1440 × 1024`; all three waveform states are `ready`; browser error arrays are empty; historical/reference playback advances; mobile material/dock and footer/dock overlap checks are both `false`.

**Follow-up Polish**

- [P3] The concept image includes IPA and an expanded dictionary card. The current product has no authoritative IPA/dictionary source for this state, so the implementation deliberately presents only real alignment status and collection behavior. Add these surfaces later only when backed by a real pronunciation/dictionary data source.
- [P3] Material numbering and some secondary copy follow the isolated real fixture rather than the concept image's illustrative values; this does not change hierarchy or task completion.

final result: passed
