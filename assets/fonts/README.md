# 字体

Kivy 自带字体没有中文字形，界面会变成方块。请把**任意一个中文字体**放到这个目录，
文件名必须是下面之一（`naiwa/ui/theme.py` 会按顺序找）：

```
NotoSansSC-Regular.ttf
NotoSansSC.ttf
SourceHanSansSC-Regular.otf
```

推荐 Noto Sans SC（SIL OFL 协议，可随 App 分发，约 10 MB）：

```bash
# 任选一个源
curl -L -o NotoSansSC-Regular.otf \
  "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Regular.otf"
```

放到 `assets/fonts/` 后重新构建即可；license 允许商业与非商业使用，但请保留字体许可说明。

## 没有放字体也行

`theme.register_fonts()` 会退回到 Android 系统字体
（`/system/fonts/NotoSansCJK-Regular.ttc`、`DroidSansFallback.ttf` 等）。
大多数国产 ROM 上能正常显示中文；实在没有就会显示方块 —— 那种情况才必须补字体文件。
