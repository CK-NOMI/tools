# Reference Repair Studio v2 — object editor MVP

专门针对 PNG 原始设计图 + 已生成 PPTX 的本地人工快捷修复工具。无模型 API 调用。Python 3.10+、LibreOffice/soffice、Poppler/pdftoppm；浏览器使用现代 Chromium 或 Safari。仅监听 127.0.0.1:8765，不要部署到公网（未实现认证和上传安全加固）。

## 安装（macOS）

```bash
brew install --cask libreoffice
brew install poppler
export PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH"
cd reference-repair
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python repair.py
```

访问 http://127.0.0.1:8765 。Ubuntu: `sudo apt install libreoffice poppler-utils`。Windows 需自行将 soffice 与 pdftoppm 加入 PATH。

## 默认城市测试样例

将本地样例包解压到 `reference-repair/`，确保 `samples/city.pptx` 与 `samples/city.png` 存在。启动服务、打开网页时会自动加载这份尚未修复的 PPTX 与原图；可点击「载入城市测试样例」恢复初始状态。缺少样例时仍可手动上传。样例目录被 Git 忽略，避免把原始素材公开提交。重新载入时若有修复记录会提示确认。

## 使用

上传 PPTX 与该页对应的原图，点击载入 PPTX。切换页时重新上传对应 PNG。用矩形、圆角矩形、圆、椭圆、自由套索、画笔选择区域；Shift 增选，Alt/Option 减选。Q 临时查看原图，透镜跟随鼠标。差异是简单 RGB 阈值显示，并非语义诊断。选区可按现有文字框边界清除、取近白背景透明的图标、作为独立图片插入（可选插在原有对象下方）。对象菜单支持删除、置顶、置底、坐标和字号调整。对象操作与插在下层的补丁请点击重新渲染核验。导出写入真正的 PPTX；撤销/重做作用于修复指令，不修改源文件。

## 已知限制

- v0.1 是人工快捷修复原型，不是完整 PPT 编辑器；自动匹配、吸附、区域替换事务、选区羽化、多边形套索、可编辑矢量重建、跨次会话项目保存尚未实现。
- 图片默认缩放为 1600px 宽的渲染画布；不保证源 PNG 每个像素不经重采样。输入须为同版式同页面，不能有截图外边框。
- 保护文字使用现有文字框矩形范围；原图中错位文字、文字溢出及隐藏在位图的重复内容无法自动识别。单张扁平 PNG 无法恢复遮挡部分的真实背景。近白去背景只适合浅色底图标，复杂背景不适用。
- 对象列表和位置来自加载时的 PPTX 快照，组内对象不递归选择，新增补丁尚不能直接选中移动。置底可能被整页背景挡住。重新渲染使用 LibreOffice，PowerPoint/WPS 渲染和字体可能有差异。
- 对象操作会延迟到重新渲染时可见；实时补丁预览为画布上层近似，层级以实际 PPTX 渲染为准。导出和预览时重放操作。

## 测试

`python test_sample.py input.pptx reference.png /tmp/repair-result`：用户城市页专用人工指定操作（依赖其 shape ID，不可用于其他页面），通过通用引擎执行；输出前后渲染、PPTX、报告。需要 numpy。实际 52→55 个对象，22 个原生文字 ID 和文本完全一致，MAE 47.53095→16.23777，生成修复指令并写入 1.15s（不包括渲染和人工决策）。

`pip install playwright` 并安装 Chromium；`python test_ui.py input.pptx reference.png /tmp/repair-ui`：Chromium 实际鼠标选区、组合、补丁、撤销重做、对象删除、重新渲染、导出。当前测试环境的浏览器禁止 localhost 导航，使用 Playwright set_content + 本地 HTTP bridge（真实 Python HTTP 后端）；不是原生浏览器网络 E2E。脚本默认 Linux `/usr/bin/chromium`。

测试输入为用户上传的文件，仓库不公开其原始素材或测试成品。


## v2 对象编辑工作台（开发版）

启动方式不变，默认 / 进入新版，/legacy 保留旧版原始设计图修复工作台及其接口。

- 逐页场景树、点击选择、拖动、八方向缩放（非旋转对象）、数字旋转/位置属性、图层、删除、文字和基础样式编辑。
- 选中图片后从对应原设计位置裁剪，确认后替换原图片并维持其 z-order；原图取件可插入独立图片，继续移动和缩放。原图宽高比校验。
- 事务撤销/重做、操作历史及交互耗时、原图叠加、真实渲染与 PPTX 导出。历史只保留当前会话，耗时不包含后台真实渲染。
- 编辑画布采用独立图片和近似 HTML 文字对象；不等同 WPS 渲染。复杂图表、组合内部、特殊形状和主题字体等预览不完整。原生 PPTX 仍由后端按事务修改；实际结果请用真实渲染检查。文字改写保留每段首 run 的样式，不保证复杂混排。
- 原图同位置裁剪并非自动分割或语义匹配；可能带入背景或重叠文字。新增取件不会自动删除旧图层。另支持框选原图替换并移动旧图片，以及固定尺度、基于像素的保守匹配归位（弱匹配或重复候选拒绝，必须确认）；跨尺度匹配、语义缺陷诊断、复杂背景分离、项目持久化尚未实现。
- 回归测试：在 reference-repair 目录安装 requirements 后运行 python -m unittest test_object_engine.py。该测试是合成对象的导出回读测试，不代表城市样例或 WPS 兼容性已经验证。
